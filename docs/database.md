# 本地数据库说明

当前数据库提供两类本地持久化：项目/快照记录，以及报告历史。它不保存账号、密码或会话。

## 存储方式

- 数据库：SQLite。
- 默认路径：`.openimpact/openimpact.sqlite3`。
- 可用环境变量 `OPENIMPACT_DB_PATH` 指定其他路径。
- 上传 ZIP 快照默认保存到 `.openimpact/snapshots/`。
- 可用环境变量 `OPENIMPACT_SNAPSHOT_DIR` 指定其他快照目录。
- `.openimpact/` 已加入 `.gitignore`，本地数据库文件不应提交到仓库。

## 表结构

当前版本自动创建 `projects`、`project_snapshots` 和 `analysis_reports` 表。

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

## API

新增接口：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/v1/projects` | 上传 ZIP，完成 Inspect，并创建项目/快照记录 |
| GET | `/api/v1/projects` | 分页读取本机项目列表，可用 `q` 筛选元数据，并返回 `has_more` |
| GET | `/api/v1/projects/{project_id}` | 读取单个项目及最新快照摘要 |
| GET | `/api/v1/projects/{project_id}/snapshots` | 分页读取项目快照列表 |
| POST | `/api/v1/reports` | 使用与 Analyze 相同的 multipart 输入生成报告，并保存到 SQLite |
| GET | `/api/v1/reports` | 分页读取历史报告摘要，可用 `q` 筛选元数据，并返回 `has_more` |
| GET | `/api/v1/reports/{report_id}` | 读取单条历史报告和完整 report JSON |
| DELETE | `/api/v1/reports/{report_id}` | 删除一条本机历史报告记录 |

原有 `/api/v1/projects/inspect`、`/api/v1/changes/validate` 和 `/api/v1/projects/analyze` 保持原有即时上传工作流。已保存项目使用新增的 `POST /api/v1/snapshots/{snapshot_id}/{operation}` 接口，支持读取、校验、分析、保存报告、源码阅读和追问。详见 [快照分析流程](snapshot-workflow.md)。

快照每次使用前校验普通文件、配置目录边界、5 MiB 大小上限和 SHA-256。文件缺失、损坏或不在配置目录内时停止处理；不会用演示数据代替。新保存记录使用绝对存储路径，旧相对路径记录在原仓库工作目录下仍可读取。修改 `OPENIMPACT_SNAPSHOT_DIR` 不会自动搬迁旧文件。

从快照生成并保存的完整 report JSON 包含 `project_id` 和 `project_snapshot_id`，可追溯来源；数据库 schema 仍为 2，未新增关联列、按项目筛选报告或删除级联行为。

## 当前边界

- 还没有用户表、登录会话、权限或团队空间。
- 还没有后台任务队列；保存报告仍是同步请求。
- 前端已有基础历史报告页面，可保存当前报告、分页读取本机已保存记录、删除单条历史报告，并通过后端 `q` 参数和前端输入框筛选元数据。
- 前端支持显式保存 ZIP、查看项目、选择快照并直接分析；刷新页面后可从项目库重新打开。
- 还没有用户隔离或团队共享；当前项目库和历史报告仍是单机本地能力。
- 指纹用于核对同一次 ZIP 字节，不是服务器端项目 ID。
