# 本地数据库说明

当前数据库提供三类本地持久化：项目/快照记录、分析任务记录，以及报告历史。它不保存账号、密码或会话。

## 存储方式

- 数据库：SQLite。
- 默认路径：`.openimpact/openimpact.sqlite3`。
- 可用环境变量 `OPENIMPACT_DB_PATH` 指定其他路径。
- 上传 ZIP 快照默认保存到 `.openimpact/snapshots/`。
- 可用环境变量 `OPENIMPACT_SNAPSHOT_DIR` 指定其他快照目录。
- `.openimpact/` 已加入 `.gitignore`，本地数据库文件不应提交到仓库。

## 表结构

当前版本自动创建 `projects`、`project_snapshots`、`analysis_tasks` 和 `analysis_reports` 表。

`projects` 保存：

- 项目 ID、创建时间、更新时间。
- 项目展示名称。

`project_snapshots` 保存：

- 快照 ID、所属项目 ID、创建时间。
- ZIP 原始字节指纹、上传文件名、源码根目录。
- 受控 ZIP 快照的服务端存储路径。
- Python 文件数、函数数量、覆盖状态和摘要 JSON。

`analysis_reports` 保存：

- 报告 ID、创建时间。
- 项目名、ZIP 指纹、上传文件名、源码根目录。
- 变更领域、变更类型、目标 ID。
- 覆盖状态、summary JSON、完整 report JSON。

`analysis_tasks` 保存：

- 任务 ID、创建时间、更新时间。
- 使用的 `project_snapshot_id`。
- 任务状态：`queued`、`running`、`succeeded` 或 `failed`。
- 本次变更配置 JSON。
- 成功后的 `result_report_id`。
- 失败时的安全错误码和用户可见错误信息。

## API

新增接口：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/v1/projects` | 上传 ZIP，完成 Inspect，并创建项目/快照记录 |
| GET | `/api/v1/projects` | 分页读取本机项目列表，可用 `q` 筛选元数据，并返回 `has_more` |
| GET | `/api/v1/projects/{project_id}` | 读取单个项目及最新快照摘要 |
| GET | `/api/v1/projects/{project_id}/snapshots` | 分页读取项目快照列表 |
| DELETE | `/api/v1/projects/{project_id}` | 删除一个本机项目及其快照记录 |
| DELETE | `/api/v1/projects/{project_id}/snapshots/{snapshot_id}` | 删除一个本机项目快照 |
| POST | `/api/v1/reports` | 使用与 Analyze 相同的 multipart 输入生成报告，并保存到 SQLite |
| GET | `/api/v1/reports` | 分页读取历史报告摘要，可用 `q` 筛选元数据，并返回 `has_more` |
| GET | `/api/v1/reports/{report_id}` | 读取单条历史报告和完整 report JSON |
| DELETE | `/api/v1/reports/{report_id}` | 删除一条本机历史报告记录 |
| POST | `/api/v1/analysis-tasks` | 基于已保存快照创建本地分析任务 |
| GET | `/api/v1/analysis-tasks` | 分页读取本地分析任务列表 |
| GET | `/api/v1/analysis-tasks/{task_id}` | 读取单个分析任务状态和结果引用 |

原有 `/api/v1/projects/inspect`、`/api/v1/changes/validate` 和 `/api/v1/projects/analyze` 保持原有即时上传工作流。已保存项目使用新增的 `POST /api/v1/snapshots/{snapshot_id}/{operation}` 接口，支持读取、校验、分析、保存报告、源码阅读和追问。详见 [快照分析流程](snapshot-workflow.md)。

快照每次使用前校验普通文件、配置目录边界、5 MiB 大小上限和 SHA-256。文件缺失、损坏或不在配置目录内时停止处理；不会用演示数据代替。同名项目重复保存会追加新的快照版本，并把项目 `updated_at` 与 `latest_snapshot` 指向最近一次保存；项目名无法识别时仍创建独立项目，避免混淆。新保存记录使用绝对存储路径，旧相对路径记录在原仓库工作目录下仍可读取。修改 `OPENIMPACT_SNAPSHOT_DIR` 不会自动搬迁旧文件。

从快照生成并保存的完整 report JSON 包含 `project_id` 和 `project_snapshot_id`，可追溯来源；数据库 schema 为 3，新增 `analysis_tasks` 表，但未给报告表新增关联列、按项目筛选报告或报告删除级联行为。删除项目或快照不删除历史报告。

## 当前边界

- 还没有用户表、登录会话、权限或团队空间。
- 已有本地分析任务表、任务 API 基础和前端只读任务状态页；主分析流程仍是即时分析，尚未实现“开始分析”任务轮询、自动重试或独立 worker。
- 前端已有基础历史报告页面，可保存当前报告、分页读取本机已保存记录、删除单条历史报告，并通过后端 `q` 参数和前端输入框筛选元数据。
- 历史报告若包含一致的来源快照信息，可点击“打开来源项目”；缺少关联的旧报告仍可阅读和下载完整 JSON，不会猜测对应项目。删除后重新加载第一页，避免偏移分页漏项。
- 前端支持显式保存 ZIP、查看项目、选择快照版本并直接分析；刷新页面后可从项目库重新打开，也可删除本机项目或快照。
- 还没有用户隔离或团队共享；当前项目库和历史报告仍是单机本地能力。
- 指纹用于核对同一次 ZIP 字节，不是服务器端项目 ID。
