# Nexus OpenImpact 下一阶段设计文档

> 日期：2026-10-13（Asia/Shanghai）
> 当前基线：`feature/refine-project`
> 目标：把当前本地 MVP 过渡到可持续开发的项目版本，同时避免把 V1 边界外能力误写成已完成。

> 2026-10-14 增量：负责人已确认项目库参与真实分析。显式保存、同名项目追加快照、选择快照、校验/分析、源码阅读、保存报告以及本机项目/快照删除已接通，见 [项目快照分析](snapshot-workflow.md)。下文账号归属、后台任务及团队级项目策略仍是设计草案。

## 1. 当前事实

当前已经完成并验收：

- Python ZIP 上传后的 Inspect / Validate / Analyze 工作流。
- 函数签名变更配置与后端校验。
- Direct、1-hop、2-hop 影响报告。
- 文件、行号、源码片段、调用路径和中文解释。
- 本地 SQLite 历史报告：保存、读取、删除、筛选、分页加载。
- 本地 SQLite 项目库基础：上传 ZIP 后创建项目/快照记录，保存受控 ZIP 快照；同名项目重复保存会追加快照版本；当前已有后端接口、前端 API 客户端封装和基础项目库页面。
- React 前端主流程：上传项目、选择函数、配置变更、查看报告、查看历史报告。

当前明确没有完成：

- 真实登录、用户表、会话或权限。
- 账号级项目归属、团队级版本管理和自动保留策略。
- 后台任务队列。
- 账号级历史报告中心。
- 团队空间、共享和权限。
- 生产环境 `/api` 反向代理或 CORS 配置。

## 2. 下一阶段目标

下一阶段建议只解决三个平台化基础问题：

1. 用户系统：让报告和项目能归属到用户。
2. 项目页面与快照复用：让已保存 ZIP 快照进入前端项目列表和后续分析。
3. 后台任务：让分析从同步请求升级为可查询状态的任务。

不建议下一阶段直接做：

- 团队空间或复杂权限。
- GitHub OAuth 或 GitHub 仓库导入。
- 自动修改代码、自动 PR、自动 Merge。
- 多语言分析。
- 企业平台能力。

## 3. 用户系统设计

### 3.1 最小目标

支持注册、登录、退出和读取当前用户。历史报告、项目和任务都能关联到用户。

### 3.2 数据表草案

`users`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | text | 用户 ID，建议 UUID/hex |
| `email` | text | 登录邮箱，唯一 |
| `password_hash` | text | 密码哈希，禁止保存明文 |
| `display_name` | text | 展示名称 |
| `created_at` | text | 创建时间 |

`sessions`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | text | 会话 ID |
| `user_id` | text | 关联 users.id |
| `token_hash` | text | token 哈希，禁止保存明文 token |
| `expires_at` | text | 过期时间 |
| `created_at` | text | 创建时间 |

### 3.3 API 草案

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | 注册用户 |
| POST | `/api/v1/auth/login` | 登录并创建会话 |
| POST | `/api/v1/auth/logout` | 注销当前会话 |
| GET | `/api/v1/auth/me` | 读取当前用户 |

### 3.4 边界

- 不保存明文密码。
- 不把当前演示登录当作真实认证。
- 不做第三方登录。
- 不做管理员后台。
- 不做团队权限。

## 4. 项目源码持久化设计

### 4.1 最小目标

用户上传 ZIP 后，后端创建项目记录和快照记录。后续分析可以基于 `project_snapshot_id` 复用同一份源码快照，而不是每次都重新上传 ZIP。

### 4.2 数据表草案

`projects`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | text | 项目 ID |
| `user_id` | text | 所属用户 |
| `name` | text | 项目名 |
| `created_at` | text | 创建时间 |
| `updated_at` | text | 更新时间 |

`project_snapshots`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | text | 快照 ID |
| `project_id` | text | 关联 projects.id |
| `fingerprint` | text | ZIP 原始字节 SHA-256 |
| `source_filename` | text | 上传文件名 |
| `analysis_root` | text | 源码根目录 |
| `storage_path` | text | 服务端保存路径或对象键 |
| `python_file_count` | integer | Python 文件数 |
| `function_count` | integer | 函数数量 |
| `coverage_status` | text | 覆盖状态 |
| `created_at` | text | 创建时间 |

### 4.3 API 草案

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/v1/projects` | 上传 ZIP 并创建项目/快照 |
| GET | `/api/v1/projects` | 读取当前用户项目列表 |
| GET | `/api/v1/projects/{project_id}` | 读取项目详情 |
| GET | `/api/v1/projects/{project_id}/snapshots` | 读取项目快照列表 |
| DELETE | `/api/v1/projects/{project_id}` | 删除项目记录和相关快照 |

### 4.4 边界

- 初期只支持 ZIP 上传。
- 不接 GitHub URL。
- 不执行上传项目代码。
- 不提供在线源码编辑。
- 删除项目是否同步删除报告，需要产品确认后再实现。

## 5. 后台任务设计

### 5.1 最小目标

用户提交分析后，后端返回 `task_id`。前端轮询任务状态，成功后读取报告。

### 5.2 数据表草案

`analysis_tasks`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | text | 任务 ID |
| `user_id` | text | 所属用户 |
| `project_snapshot_id` | text | 使用的源码快照 |
| `status` | text | queued/running/succeeded/failed |
| `change_json` | text | 本次变更配置 JSON |
| `result_report_id` | text | 成功后关联 analysis_reports.id |
| `error_code` | text | 失败错误码 |
| `error_message` | text | 用户可见错误 |
| `created_at` | text | 创建时间 |
| `updated_at` | text | 更新时间 |

### 5.3 API 草案

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/v1/analysis-tasks` | 创建分析任务 |
| GET | `/api/v1/analysis-tasks` | 读取任务列表 |
| GET | `/api/v1/analysis-tasks/{task_id}` | 读取任务状态和结果引用 |

### 5.4 边界

- 初期可以使用进程内队列或单 worker。
- 不做分布式任务。
- 不做复杂重试策略。
- 不自动运行用户项目测试。
- 不把任务排队状态伪装为已经完成的分析报告。

## 6. 报告表演进

当前 `analysis_reports` 已保存报告 JSON 与摘要元数据。下一阶段可以在不破坏现有报告读取的前提下追加字段：

| 字段 | 说明 |
| --- | --- |
| `user_id` | 报告所属用户 |
| `project_id` | 报告所属项目 |
| `project_snapshot_id` | 报告对应源码快照 |
| `task_id` | 生成该报告的分析任务 |

迁移原则：

- 旧本机报告允许 `user_id` 等字段为空。
- 新 API 默认只返回当前用户自己的报告。
- 项目删除策略需要先确认，不直接级联删除历史报告。

## 7. 前端改造范围

新增页面或状态：

- 登录状态管理。
- 项目列表页。
- 项目详情页。
- 项目快照选择。
- 任务状态展示。
- 当前用户的历史报告列表。

复用现有模块：

- 上传 ZIP 表单。
- 函数选择页。
- 变更配置页。
- 报告展示组件。
- 历史报告列表样式和筛选交互。

## 8. 开发优先级

第一阶段：项目持久化基础

1. 新增 `projects`、`project_snapshots` 表。已完成后端基础版。
2. 新增项目上传与列表 API。已完成后端基础版。
3. 前端项目列表、快照选择和快照复用分析闭环已完成，同时保留 ZIP 直接分析流程。

第二阶段：报告关联项目

1. `analysis_reports` 追加项目和快照关联字段。
2. 保存报告时写入 `project_id` / `project_snapshot_id`。
3. 历史报告支持按项目过滤。

第三阶段：用户系统

1. 新增用户和会话表。
2. 登录后报告和项目归属用户。
3. 前端从演示登录切换为真实登录。

第四阶段：后台任务

1. 新增 `analysis_tasks` 表。
2. 分析 API 改为创建任务。
3. 前端轮询任务并展示状态。

## 9. 验收标准

项目持久化完成后：

- 用户上传 ZIP 后能在项目列表看到项目。
- 项目详情能展示最新快照的文件数、函数数和覆盖状态。
- 用户可以基于已有项目重新发起分析。
- 原上传 ZIP 即时分析流程不被破坏。

用户系统完成后：

- 未登录不能读取用户项目和用户历史报告。
- 登录后只能看到自己的项目和报告。
- 密码不以明文形式保存。

后台任务完成后：

- 创建任务立即返回 `task_id`。
- 任务状态可以从 queued/running 变为 succeeded/failed。
- 成功任务能关联到报告。
- 失败任务返回安全、可展示的错误，不泄露服务器路径或堆栈。

## 10. 需要确认的问题

这些问题不能由实现默认决定：

1. 是否允许匿名用户保存项目。
2. 项目删除时是否删除历史报告。
3. 上传 ZIP 保存多久、大小上限是否沿用当前 5 MiB。
4. 用户系统是否只支持邮箱密码，是否需要学校/比赛账号。
5. 后台任务失败是否允许重试。
6. 是否需要导出报告 PDF/Markdown。
7. 是否需要部署到公网，以及生产域名和 `/api` 代理策略。

## 11. 暂不实现内容

- GitHub 仓库导入。
- GitHub OAuth。
- 团队空间与多人权限。
- 自动修改代码。
- 自动 PR / Merge。
- 多语言分析。
- 企业平台能力。
- 运行用户上传项目的测试。
