# 本地数据库说明

当前数据库只做报告历史的最小持久化，不保存上传 ZIP、源码压缩包、账号、密码或会话。

## 存储方式

- 数据库：SQLite。
- 默认路径：`.openimpact/openimpact.sqlite3`。
- 可用环境变量 `OPENIMPACT_DB_PATH` 指定其他路径。
- `.openimpact/` 已加入 `.gitignore`，本地数据库文件不应提交到仓库。

## 表结构

当前版本自动创建 `analysis_reports` 表，保存：

- 报告 ID、创建时间。
- 项目名、ZIP 指纹、上传文件名、源码根目录。
- 变更领域、变更类型、目标 ID。
- 覆盖状态、summary JSON、完整 report JSON。

## API

新增接口：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/v1/reports` | 使用与 Analyze 相同的 multipart 输入生成报告，并保存到 SQLite |
| GET | `/api/v1/reports` | 分页读取历史报告摘要，可用 `q` 筛选元数据，并返回 `has_more` |
| GET | `/api/v1/reports/{report_id}` | 读取单条历史报告和完整 report JSON |
| DELETE | `/api/v1/reports/{report_id}` | 删除一条本机历史报告记录 |

原有 `/api/v1/projects/analyze` 保持无持久化行为，避免破坏冻结契约。

## 当前边界

- 还没有用户表、登录会话、权限或团队空间。
- 还没有后台任务队列；保存报告仍是同步请求。
- 前端已有基础历史报告页面，可保存当前报告、分页读取本机已保存记录、删除单条历史报告，并通过后端 `q` 参数和前端输入框筛选元数据。
- 还没有用户隔离或团队共享；当前历史报告仍是单机本地能力。
- 指纹用于核对同一次 ZIP 字节，不是服务器端项目 ID。
