# Nexus OpenImpact API 契约

## 调用覆盖的兼容追加

函数签名分析增加类方法和嵌套函数中的明确模块级函数引用；Inspect 的可选函数仍为原模块级目标。调用方标识可包含 `Class.method` 或 `outer.<locals>.inner`，必须按报告原值显示，不能据此推断对象分派。旧路径、请求、schema_version、指纹与 Evidence 顺序不变。

partial 时 Inspect / Validate / 函数 Analyze 的 `coverage` 可追加 `details`：`python_files`、`parsed_python_files`、`named_caller_count`、`excluded_call_count`；Analyze 另有 `resolved_call_count` 和 `unresolved_call_count`。均为非负整数。文件数为 Scanner 范围内的 Python 源码；调用数为静态记录，不能转换为本次变更的准确率或漏检数。缺省时沿用旧提示，complete 响应不增加这些字段。Module / Symbol 报告保持原契约。详见 [调用覆盖](call-coverage.md)。

## 解释文字的兼容增强

报告版本、公开字段和 Evidence 保持不变。解释层读取既有路径上下文，生成按真实位置排序的检查建议；上下文不作为新的公开字段。`why_affected` 和 `suggested_check` 允许换行，前端应安全按文本呈现，不能解析文字决定影响。证据不可用时解释为 `null`。详见 [检查建议](explanation-check-guidance.md)。

## 普通包支持的兼容追加

三个业务接口追加可选单一 multipart 文本字段 `analysis_root`，缺省 `.`，例如 `src`。三个阶段须重复传入同一选择，不放入 `change` JSON。非默认时追加 `analysis_layout`；默认旧响应不增加此字段。目录校验、422 / 400、排除调用作用域诊断详见 [普通包契约](package-imports.md)。`source_root` 仍表示 ZIP 外包装。原三领域八种操作、schema_version=1、fingerprint 算法、Evidence 顺序及旧 JSON 字段含义保持。

Phase 2.1 提供仓库内置 `examples/signature_change/` 的分析。Phase 2.2 增加上传 Python 项目 ZIP 的语法检查。Phase 2.3 增加简化配置生成与校验 ChangeSpec。Phase 2.4 增加上传项目的完整影响分析，调用现有 `analyze_project()` 和 `build_report()`。

## 前后端冻结范围

| HTTP Method | Path | Content-Type | 用途 | 成功状态 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/projects` | `multipart/form-data` | 上传 ZIP，完成 Inspect，并保存项目/快照记录 | 200 |
| GET | `/api/v1/projects` | 无 | 分页读取已保存项目摘要，可用 `q` 筛选元数据 | 200 |
| GET | `/api/v1/projects/{project_id}` | 无 | 读取单个已保存项目及最新快照摘要 | 200 |
| DELETE | `/api/v1/projects/{project_id}` | 无 | 删除一个本机项目及其快照记录 | 200 |
| GET | `/api/v1/projects/{project_id}/snapshots` | 无 | 分页读取项目快照摘要 | 200 |
| DELETE | `/api/v1/projects/{project_id}/snapshots/{snapshot_id}` | 无 | 删除一个本机项目快照 | 200 |
| POST | `/api/v1/projects/inspect` | `multipart/form-data` | 检查上传 ZIP 的模块、Symbol 与覆盖情况 | 200 |
| POST | `/api/v1/changes/validate` | `multipart/form-data` | 从上传源码构建并校验 ChangeSpec | 200 |
| POST | `/api/v1/projects/analyze` | `multipart/form-data` | 在本次上传项目上生成完整影响报告 | 200 |
| POST | `/api/v1/reports` | `multipart/form-data` | 生成影响报告并保存到本地 SQLite 历史记录 | 200 |
| GET | `/api/v1/reports` | 无 | 分页读取已保存报告摘要，可用 `q` 筛选元数据 | 200 |
| GET | `/api/v1/reports/{report_id}` | 无 | 读取单条已保存报告及完整 report JSON | 200 |
| DELETE | `/api/v1/reports/{report_id}` | 无 | 删除一条本机已保存报告 | 200 |
| POST | `/api/v1/analysis-tasks` | `multipart/form-data` | 基于已保存快照创建本地分析任务 | 202 |
| GET | `/api/v1/analysis-tasks` | 无 | 分页读取本地分析任务状态 | 200 |
| GET | `/api/v1/analysis-tasks/{task_id}` | 无 | 读取单个本地分析任务状态和结果引用 | 200 |
| POST | `/api/v1/analysis-tasks/{task_id}/retry` | 无 | 基于失败任务的原快照和变更创建一项新任务 | 202 |

三个核心业务接口仍需要重新上传 ZIP：`/api/v1/projects/inspect`、`/api/v1/changes/validate` 和 `/api/v1/projects/analyze` 每次请求在独立临时目录完成并清理。`expected_fingerprint` 是 ZIP 原始字节的 SHA-256 校验值，不是这些核心接口的服务端项目查找键。同一源码重新打包也可能产生不同指纹；修改或重新打包后应重新 inspect。文件名只用于展示项目名称的回退值，不参与指纹计算。不接受服务器本地路径、查询参数或额外表单字段。

项目库接口是新增的本机持久化能力：`POST /api/v1/projects` 接受同一套 ZIP 安全限制，完成 Inspect 后创建项目记录和快照记录，并把 ZIP 快照保存到 `.openimpact/snapshots/`，可用 `OPENIMPACT_SNAPSHOT_DIR` 覆盖。同名项目会追加新的快照版本，无法识别项目名时仍创建独立项目。该接口返回 `project`、`snapshot` 和本次 `inspect`。前端支持从项目库选择快照直接分析，也支持删除本机项目或快照；删除只影响本机 SQLite 记录和未被其他项目引用的 ZIP 快照文件。现阶段不提供用户归属、权限、团队共享或账号级项目管理。

报告历史接口只保存分析报告 JSON 和摘要元数据，不保存上传 ZIP 或源码压缩包。默认 SQLite 路径为 `.openimpact/openimpact.sqlite3`，可用 `OPENIMPACT_DB_PATH` 覆盖；该目录不应提交到版本库。`GET /api/v1/reports` 支持可选查询参数 `q`，仅筛选项目名、上传文件名、变更领域、变更类型、目标 ID 和覆盖状态等元数据，最长 80 个字符；响应包含 `items`、`limit`、`offset`、`query` 和 `has_more`，前端用 `has_more` 决定是否继续加载下一页。删除历史报告只移除本地保存的报告记录，不修改源码或上传 ZIP。原 `/api/v1/projects/analyze` 保持无持久化行为，避免破坏冻结契约。

分析任务接口是本地任务基础能力：`POST /api/v1/analysis-tasks` 基于已保存快照创建任务，只返回 `queued`。独立的本机 `python -m openimpact.worker` 以 SQLite 租约领取任务、执行分析并把成功结果保存为历史报告；API 与 Worker 必须指向相同的本地数据库和快照目录。标准前端在项目库快照或直接上传 ZIP 的“开始分析”中都会创建或复用任务并轮询结果；直接上传 ZIP 会先调用项目库保存接口生成快照。旧的即时上传 Analyze 接口仍保留以兼容冻结契约。任务接口不接收 ZIP 文件，不是生产级队列；当前没有用户归属或自动重试。失败任务支持手动创建一项新的重试任务，旧任务保留不变。

三个接口的 `file` 均为 multipart 文件字段，建议浏览器以 `application/zip` 上传；服务以 ZIP 内容及安全规则判断，不依赖客户端声明的 MIME。每个请求的 multipart 总量最多 5 MiB + 64 KiB，其中 ZIP 文件最多 5 MiB。其余 ZIP 条目和解压限额见下文。前端交接示例见 [frontend-handoff.md](frontend-handoff.md)，真实响应见 [api-samples](api-samples)。

## 本地启动

Phase 4.1 核查：当前后端没有配置 CORS，保持跨域关闭。React 开发服务器实际 Origin 尚未确认，后续经负责人确认后使用环境配置加载明确白名单；本轮不设置通配 Origin 或假设部署地址。独立前端直接访问后端时，浏览器尚无法读取跨域响应；同源或实际配置的开发代理可使用相对 `/api` 路径。启动、接入条件及报告状态说明见 [frontend-handoff.md](frontend-handoff.md)。

在仓库根目录安装项目后运行：

```powershell
pip install -e .
python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

需要处理任务时，在另一个终端运行：

```powershell
python -m openimpact.worker
```

运行自动化测试时可安装 `pip install -e ".[test]"`；`httpx` 和 `pytest` 位于该可选依赖中。服务入口为 `openimpact.api:app`。目前 Demo 从当前源码仓库读取，运行服务时需保留 `examples/signature_change/`。

## `GET /api/v1/health`

无需请求体。成功响应为 HTTP 200：

```json
{"status": "ok", "version": "0.1.0"}
```

## 项目库接口

`POST /api/v1/projects` 请求体为 `multipart/form-data`，字段与 Inspect 相同：恰好一个 `file` ZIP 文件，可选 `analysis_root`。它会执行同一套 ZIP 安全校验和 Inspect，然后保存项目记录、快照记录和原始 ZIP 快照。若 `inspect.project_name` 与已有项目一致，保存会复用该项目并追加一个快照；响应的 `project.latest_snapshot` 指向刚保存的快照。

成功响应为 HTTP 200：

```json
{
  "project": {
    "id": "<32位hex>",
    "created_at": "2026-10-13T00:00:00.000000+00:00",
    "updated_at": "2026-10-13T00:00:00.000000+00:00",
    "name": "signature_change",
    "latest_snapshot": {"id": "<32位hex>", "project_id": "<32位hex>"}
  },
  "snapshot": {
    "id": "<32位hex>",
    "project_id": "<32位hex>",
    "project_fingerprint": "<ZIP SHA-256>",
    "source_filename": "signature_change.zip",
    "analysis_root": ".",
    "python_file_count": 4,
    "function_count": 4,
    "coverage_status": "complete",
    "summary": {"source_root": "signature_change"}
  },
  "inspect": {"project_name": "signature_change", "symbols": []}
}
```

`project` 与 `snapshot` 响应不暴露服务端 `storage_path`。ZIP 快照路径只保存在本地 SQLite 中；快照接口按 ID 读取它，不接受客户端文件路径。上方 JSON 为字段节选，真实 Inspect 仍包含完整函数列表，两个位置的 snapshot 内容一致。

`GET /api/v1/projects` 支持 `limit`、`offset` 和可选 `q`，规则与报告历史一致：`limit` 为 1 到 50，`offset` 不能为负数，`q` 最多 80 字符。响应包含 `items`、`limit`、`offset`、`query` 和 `has_more`。`q` 仅筛选项目名、上传文件名、指纹和覆盖状态。

`GET /api/v1/projects/{project_id}` 读取单个项目及最新快照摘要。`GET /api/v1/projects/{project_id}/snapshots` 分页读取该项目的快照摘要。非法或不存在的项目 ID 返回 404 `project_not_found`。

`DELETE /api/v1/projects/{project_id}` 删除一个本机项目及其快照记录。`DELETE /api/v1/projects/{project_id}/snapshots/{snapshot_id}` 删除单个快照；如果这是项目最后一个快照，项目记录也会被删除，响应中的 `project_deleted` 为 `true`。ZIP 快照文件只有在没有其他快照记录引用同一 SHA-256 指纹时才会删除，避免同一文件被多个项目复用时误删。删除接口不修改用户源码仓库，不删除历史报告。

### 复用快照

新增 `POST /api/v1/snapshots/{snapshot_id}/{operation}`，`operation` 支持：

| operation | 必填业务字段 | 可选业务字段 | 返回 |
| --- | --- | --- | --- |
| `inspect` | 无 | 无 | 原 Inspect 结果及 `snapshot` 元数据 |
| `validate` | `change` | 无 | 原 Validate 结果 |
| `analyze` | `change` | 无 | 原分析报告 |
| `reports` | `change` | 无 | `{record, report}`，重建并保存服务端报告 |
| `source` | 无 | `path` | 原源码目录/文件响应 |
| `questions` | `change`, `question` | `finding_index`, `history` | 原证据追问响应 |
| `question-suggestions` | `change` | `finding_index` | 原推荐追问响应 |

使用表单文本字段，`change`、`history` 仍为 JSON 字符串。除 Inspect 可选外，每次必须发送 `expected_fingerprint`；不发送 `file` 或 `analysis_root`。后端使用保存时的源码根目录，每次核对 ZIP 字节和指纹，并复用安全解包、静态分析、临时目录清理。请求体最大 64 KiB；重复字段、额外字段、文件字段或查询参数返回 400，缺必填字段或错误指纹格式返回 422。

成功业务结果追加 `project_id`、`project_snapshot_id`、`project_fingerprint`；`reports` 中这些字段位于 `report` 内，并随完整报告保存。原报告 schema_version 和影响证据定义不变。已存在的即时上传接口没有增加必填字段或改变响应。

快照不存在/ID 非法：404 `snapshot_not_found`；文件丢失：404 `snapshot_missing`；存储字节损坏/超限：409 `snapshot_corrupted`；请求指纹不匹配：409 `fingerprint_mismatch`；路径或数据库不可用：503 `snapshot_unavailable`。错误不会返回服务器路径或用固定样例替代真实项目。详细验收见 [项目快照分析](snapshot-workflow.md)。

### 本地分析任务

`POST /api/v1/analysis-tasks` 请求体为 `multipart/form-data`，只接受：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `project_snapshot_id` | 是 | 已保存快照 ID，32 位 hex |
| `change` | 是 | JSON 对象，沿用 Analyze 的变更配置 |
| `expected_fingerprint` | 是 | 保存快照 ZIP 的 SHA-256，用于执行时核对字节 |

成功返回 HTTP 202：

```json
{"task":{"id":"<32位hex>","status":"queued","project_snapshot_id":"<32位hex>","change":{}}}
```

Worker 领取后会把任务更新为 `running`，成功后保存报告并写入 `result_report_id`，失败则写入安全的 `error_code` 和 `error_message`。租约超时的 `running` 任务可以由后续 Worker 重新领取；迟到的旧 Worker 不能覆盖新 Worker 的结果。任务执行沿用快照分析的安全读取、指纹核对、静态分析和报告保存规则；不会执行用户源码，也不会把服务器路径写入响应。

`GET /api/v1/analysis-tasks` 支持 `limit` 与 `offset`，规则为 `limit` 1 到 50，`offset` 非负；响应包含 `items`、`limit`、`offset` 和 `has_more`。`GET /api/v1/analysis-tasks/{task_id}` 返回单个任务；任务 ID 非法或不存在返回 404 `task_not_found`。

`POST /api/v1/analysis-tasks/{task_id}/retry` 不接受请求体或查询参数。它只接受状态为 `failed` 的已有任务，读取同一个项目快照和原始变更配置后创建新的 queued 任务，返回 HTTP 202 和新任务对象。旧失败任务保持原有状态和诊断，便于复核；没有重新执行或正在执行的任务返回 409 `task_not_retryable`。快照不存在、缺失或损坏时沿用快照错误码。

输入错误：未知字段、重复字段、查询参数或文件字段返回 400 `unsupported_input`；`change` 不是 JSON 对象返回 422 `invalid_change_json`；分页错误返回 422 `invalid_pagination`；快照不存在按快照接口返回 404 `snapshot_not_found`。创建成功后的指纹不匹配、快照损坏或分析错误会记录为 `failed` 任务，而不是伪造成功报告。

## `POST /api/v1/demo/analyze`

无需请求体或查询参数。例如：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/demo/analyze
```

成功响应为 HTTP 200，返回 Core CLI JSON 模式使用的 `build_report()` 结果；HTTP 层将 `project_path` 规范为 `.`，避免暴露服务器目录。CLI 保留本地项目路径，其他分析数据相同。顶层字段保持为：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 当前为 `1` |
| `project_path` | 相对项目根目录，固定为 `.` |
| `change` | 结构化 ChangeSpec |
| `validation` | ChangeSpec 校验结论和诊断 |
| `coverage` | 覆盖状态、模块与解析计数 |
| `summary` | Direct、1-hop、2-hop、人工检查等计数 |
| `direct_impacts` | 本次变更确定造成的直接影响 |
| `indirect_impacts` | 上游待检查符号及原始调用路径 |
| `evidences` | Direct 与 Indirect 的源码片段、哈希和传播证据；证据读取失败时附诊断 |
| `explanations` | 与 `evidences` 一一对应的中文解释或不可用诊断 |
| `manual_reviews` | 静态证据不足的调用 |
| `pre_existing_problems` | 修改前已有的不兼容调用 |
| `diagnostics` | 解析错误、未解析调用与 import |

固定 Demo 的 `summary.direct_impact_count`、`summary.indirect_1hop_count`、`summary.indirect_2hop_count` 均为 `1`，`coverage.status` 为 `complete`。Indirect 表示建议检查的上游调用路径，不承诺运行时失败。

## `POST /api/v1/projects/inspect`

请求体为 `multipart/form-data`，恰好一个名为 `file` 的 ZIP 文件字段；不接收查询参数、服务器路径或 ChangeSpec。示例：

| 请求字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | ZIP 文件（二进制 multipart part） | 是 | 本次要检查的 Python 项目 |

| 正常返回字段 | 类型 | 含义 |
| --- | --- | --- |
| `project_name` | string | 展示名称，来自剥离的外层目录或上传文件名 |
| `project_fingerprint` | string | 本次 ZIP 原始字节的 64 位小写 SHA-256 |
| `source_root` | string 或 null | 被剥离的单层外包装目录 |
| `modules` | object[] | `module`、相对 `file`、`parse_status` |
| `symbols` | object[] | `symbol_id`、模块/文件/行号、参数信息 |
| `coverage` | object | `status`、文件及索引计数 |
| `diagnostics` | object | 解析、未解析 import、歧义模块/符号 |

```powershell
curl.exe -X POST -F "file=@project.zip;type=application/zip" http://127.0.0.1:8000/api/v1/projects/inspect
```

成功响应为 HTTP 200。示例结构：

```json
{
  "project_name": "sample",
  "project_fingerprint": "<上传 ZIP 原始字节的 SHA-256 十六进制值>",
  "source_root": "sample",
  "modules": [{"module": "utils", "file": "utils.py", "parse_status": "ok"}],
  "symbols": [{"symbol_id": "utils.format_date", "module": "utils", "file": "utils.py", "name": "format_date", "line": 1, "parameters": [{"name": "date", "kind": "positional_or_keyword", "has_default": false, "default_source": null, "annotation_source": null}]}],
  "coverage": {"status": "complete", "python_files": 1, "indexed_modules": 1, "indexed_functions": 1, "files_with_parse_errors": 0},
  "diagnostics": {"parse_errors": [], "unresolved_imports": [], "ambiguous_modules": [], "ambiguous_symbols": []}
}
```

`project_name` 来自剥离的单层根目录；没有剥离时使用上传文件名的 stem。`source_root` 为被剥离的目录名，或 `null`。如果所有可分析 `.py` 文件都位于同一外层目录，且该目录没有 `__init__.py`，剥离一层以避免 `sample.utils` 之类的误标。`pkg/__init__.py` 表明该目录本身是 Python 包，因此保留 `pkg` 模块前缀。只将 Scanner 范围内的 `.py` 写入请求专用临时目录；忽略 `.git`、`.venv`、`__pycache__`、`node_modules`、`dist`、`build`。`Symbol ID` 为 `module.function`，只收录可解析文件中的模块级函数。参数保留 Core 的 `kind`、`has_default`、默认值及注解源码字段。

`coverage.status=partial` 表示有解析错误、未解析 import 或符号/模块歧义；诊断包含相对文件路径、行号及原因。此接口只做源码读取、AST 解析和 Symbol Index，不执行上传代码；返回值不包含服务器临时路径。项目内容在请求结束后清理。

上传上限为 ZIP 文件 5 MiB，整个 multipart 请求体 5 MiB + 64 KiB；最多 256 个 ZIP 条目、128 个文件；单文件声明及实际解压大小最多 1 MiB、合计最多 10 MiB、单条目声明压缩比最多 200。逐条检查原始 ZIP 路径，拒绝绝对路径、`..`、Windows 驱动器/UNC/保留名称、反斜杠、重复路径、符号链接及特殊文件。只接受未加密的 Stored / Deflated 条目；目录和非 `.py` 文件仍计入条目、文件及声明解压大小限制。无可分析 Python 文件返回 422。

## `POST /api/v1/changes/validate`

请求体为 `multipart/form-data`，需要各一个 `file`（重新上传的 Python 项目 ZIP）和 `change`（JSON 字符串）字段，可提供一个 `expected_fingerprint`（之前 inspect 返回的 SHA-256）。与 inspect 使用同一套 ZIP 安全校验、资源限额、根目录识别、Scanner、AST Parser、Symbol Index 和临时目录清理流程；不接受查询参数或其他字段。

| 请求字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | ZIP 文件（二进制 multipart part） | 是 | 本次用于读取真实函数签名的项目 |
| `change` | string（JSON 文本） | 是 | 简化变更配置；作为普通表单字段发送 |
| `expected_fingerprint` | string（64 位十六进制） | 否 | 与本次 ZIP 字节核对；可用 inspect 返回值 |

| `change` JSON 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `target_symbol_id` | string | 是 | inspect `symbols[].symbol_id` 中的模块级函数 |
| `change_type` | string 枚举 | 否 | 缺省为 `add_required_parameter`；也支持显式 `remove_parameter`、`rename_parameter`、`make_parameter_required` |
| `added_parameter.name` | string | 新增时必填 | 新增参数名；合法性由 Core Validator 判断 |
| `added_parameter.kind` | string 枚举 | 新增时必填 | `positional_only`、`positional_or_keyword` 或 `keyword_only` |
| `insert_before` | string | 否 | 仅用于新增；目标函数中已有参数名，新增参数插在其前面 |
| `parameter_name` | string | 删除、重命名或必填化时必填 | 目标现有参数名；各类型的 kind 边界见下文 |
| `new_parameter_name` | string | 重命名时必填 | 合法 Python identifier、非 keyword，与旧名不同且不与其他参数重名 |

```json
{
  "target_symbol_id": "utils.format_date",
  "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}
}
```

新增类型的 `added_parameter.kind` 仅允许 `positional_only`、`positional_or_keyword`、`keyword_only`。默认插入位置为该参数类型组的末尾、下一类型组的开头；如果这导致非法签名，返回 Core Validator 的 `invalid_after_signature`，不会自行寻找其他插入点。可选 `"insert_before": "现有参数名"` 指定插入在该参数之前，仍由 Core Validator 判断合法性。缺省请求生成 `add_required_parameter`，新增参数 `required=true` 且无默认值。

旧请求无需修改；显式传入 `"change_type": "add_required_parameter"` 与缺省请求返回相同结果。新增类型的 `change_spec` / 报告 `change` 保留原有五个字段。Phase 6.2 通过同一接口支持以下删除配置：

```json
{
  "change_type": "remove_parameter",
  "target_symbol_id": "utils.format_date",
  "parameter_name": "timezone"
}
```

删除请求只接受这三个 JSON 字段，不能混入 `added_parameter` 或 `insert_before`。服务从本次 ZIP 读取 before，移除指定参数生成 after，其余参数顺序、kind、默认值、注解和函数元信息完全保留。支持删除必填或可选的 `positional_only`、`positional_or_keyword`、`keyword_only`。参数不存在返回 HTTP 422 `parameter_not_found`；删除 `*args` 或 `**kwargs` 返回 HTTP 422 `unsupported_parameter_kind`；参数名格式非法返回 HTTP 422 `invalid_operation_payload`。上述错误均使用 `validation.diagnostics[]`，不是顶层 `error.code`，且不会执行影响分析。

删除结果中 `change_type="remove_parameter"`，`added_parameter=null`，并保留 `operation={"change_type":"remove_parameter","parameter_name":"timezone"}`。validate 的 `change_spec` 与 analyze 的 `change` 使用相同结构。`schema_version` 仍为 `1`，原路径、multipart 字段、指纹算法、ZIP 限额和清理机制不变。未知 / 非字符串类型继续返回 HTTP 422 `invalid_change_config`。HTTP 输入采用下列简化配置；内部 Operation 通过响应表达，不作为新的 multipart 字段。设计、CLI 示例与当前限制见 [Change Type 架构](change-types.md)。

Phase 6.3 通过同一 validate / analyze 接口支持重命名：

```json
{
  "change_type": "rename_parameter",
  "target_symbol_id": "utils.f",
  "parameter_name": "timeout",
  "new_parameter_name": "delay"
}
```

重命名 JSON 必须且仅包含这四个字段，不接受 added_parameter 或 insert_before。服务从本次项目快照读取 before，只改变指定参数的 name，其余顺序、kind、默认值、注解和函数元信息保持不变；after 仍交给共享 Core Validator。支持 `positional_or_keyword` 与 `keyword_only`，拒绝 `positional_only`、`var_positional`、`var_keyword`。这些拒绝形式涉及函数体引用或更复杂语义，当前调用兼容性模型不覆盖。

旧名和新名按照 Python 的 NFKC 标识符规则归一化；冲突、相同名称及关键字检查使用归一化后的名字，响应 operation 也返回该规范名字。例如全角 `ａ` 与 `a` 会视为同名，不能绕过冲突检查。

| 重命名错误 | HTTP 状态 | `validation.diagnostics[].code` |
| --- | --- | --- |
| 旧名不存在 | 422 | `parameter_not_found` |
| 新名不是合法 identifier 或为 keyword | 422 | `invalid_parameter_name` |
| 新名等于旧名 | 422 | `parameter_name_unchanged` |
| 新名与其他参数冲突 | 422 | `parameter_name_conflict` |
| 不支持的旧参数 kind | 422 | `unsupported_parameter_kind` |
| 目标 Symbol 不存在 | 422 | `target_not_found` |
| 缺字段、混入其他类型字段 | 422 | `invalid_change_config` |
| 旧名格式非法 | 422 | `invalid_operation_payload` |

指纹不一致仍为 HTTP 409、顶层 `error.code="fingerprint_mismatch"`，在解压与分析前拒绝。上述 422 返回 `change_spec=null` 与原有 validation / diagnostics 结构，未进入影响分析；请求结束仍清理快照。

重命名返回 `change_type="rename_parameter"`、`added_parameter=null`，统一 `operation={"change_type":"rename_parameter","parameter_name":"timeout","new_parameter_name":"delay"}`；validate 的 change_spec 与 analyze 的 change 保持一致。schema_version=1。纯位置调用通常仍兼容，旧 keyword 调用是否不兼容以 before / after 绑定为准（例如 **kwargs 定义可能接收旧 keyword）。展开实参继续 manual_review，不作为确定传播种子。

重命名 Evidence 的 rule 为 `parameter_renamed_breaks_keyword_call`，reason 说明旧名 → 新名及实际绑定失败，代码片段、源码哈希和路径仍来自真实项目。Explanation 仅解释证据。当前不检查函数体内部旧参数名引用、positional-only 内部引用风险、reflection / inspect.signature、docstring、type comment 或 external string references，也不修改用户源码。

Phase 6.4 通过同一 validate / analyze 接口支持移除已有参数默认值：

```json
{
  "change_type": "make_parameter_required",
  "target_symbol_id": "utils.connect",
  "parameter_name": "timeout"
}
```

该 JSON 必须且仅包含这三个字段，不接受 added_parameter、new_parameter_name、insert_before 或 default。服务从本次快照读取 before，确认目标参数有默认值且属于 `positional_only` / `positional_or_keyword` / `keyword_only`，只清除其默认值；参数名、顺序、kind、注解、其他参数和函数元信息保持不变。参数名与 Python AST 一致按 NFKC 规范化。

当前无默认值表示为 `has_default=false, default_source=null`。源码 `timeout=None` 的 before 为 `has_default=true, default_source="None"`，仍然是可选参数；False、0、空字符串同样不能按真假值误认为没有默认值。默认值只读取语法文本，不执行表达式。

构造 after 时复用共享签名合法性检查，再由现有 ChangeSpec Validator 检查源码一致性和唯一差异。`f(a=1, b=2)` 只移除 b 默认值会返回 invalid_after_signature，不调整 a、不重排；keyword-only 参数不受位置参数默认顺序约束。

| 移除默认值错误 | HTTP 状态 | `validation.diagnostics[].code` |
| --- | --- | --- |
| 参数不存在 | 422 | `parameter_not_found` |
| 参数当前没有默认值，已为必填 | 422 | `parameter_already_required` |
| *args / **kwargs 不支持 | 422 | `unsupported_parameter_kind` |
| after 参数顺序等语法非法 | 422 | `invalid_after_signature` |
| 目标 Symbol 不存在 | 422 | `target_not_found` |
| 缺字段或混入其他类型字段 | 422 | `invalid_change_config` |
| 参数名格式非法 | 422 | `invalid_operation_payload` |

上述 422 仍返回 change_spec=null、validation.valid=false 和明确 diagnostics，未进入影响分析，临时目录仍清理。指纹不一致仍在解压与分析前返回 HTTP 409 `error.code="fingerprint_mismatch"`。原 ZIP 限制、multipart 字段、路径和上传生命周期均不变。

成功返回 `change_type="make_parameter_required"`、`added_parameter=null`、`operation={"change_type":"make_parameter_required","parameter_name":"timeout"}`，validate 的 change_spec 与 analyze 的 change 保持一致；schema_version=1。缺省 change_type 继续为 add_required_parameter，旧 add/remove/rename 请求及响应保持原行为。

只有 before compatible → after incompatible 才产生 Direct；显式提供值的调用通常仍兼容，展开实参保持 manual_review。确定 Direct 使用 `parameter_became_required_breaks_call`，Evidence reason 说明已有默认值被移除、当前调用缺少必填参数以及 before/after 状态；源码位置、哈希和传播路径继续来自真实项目。Explanation 只解释证据，不能决定影响。

本阶段不分析函数体业务逻辑、默认值本身变化的行为差异、reflection / inspect.signature、docstring 或 external configuration，不实现 make_parameter_optional。

PowerShell 示例（先准备好 `project.zip` 和仅含上述 JSON 的 `change.json`）：

```powershell
curl.exe -X POST -F "file=@project.zip;type=application/zip" -F "change=<change.json" -F "expected_fingerprint=<此前 inspect 返回的 64 位指纹>" http://127.0.0.1:8000/api/v1/changes/validate
```

成功返回 HTTP 200：

```json
{
  "project_name": "project",
  "project_fingerprint": "<本次 ZIP 的 SHA-256>",
  "coverage": {"status": "complete", "python_files": 1, "indexed_modules": 1, "indexed_functions": 1, "files_with_parse_errors": 0},
  "change_spec": {
    "change_type": "add_required_parameter",
    "target_symbol_id": "utils.format_date",
    "before": {"name": "format_date", "parameters": [{"name": "date", "kind": "positional_or_keyword", "has_default": false, "default_source": null, "annotation_source": null}], "is_async": false, "return_annotation_source": null},
    "after": {"name": "format_date", "parameters": [{"name": "date", "kind": "positional_or_keyword", "has_default": false, "default_source": null, "annotation_source": null}, {"name": "timezone", "kind": "positional_or_keyword", "has_default": false, "default_source": null, "annotation_source": null}], "is_async": false, "return_annotation_source": null},
    "added_parameter": {"name": "timezone", "kind": "positional_or_keyword", "required": true, "annotation_source": null}
  },
  "validation": {"valid": true, "diagnostics": []},
  "diagnostics": {"parse_errors": [], "unresolved_imports": [], "ambiguous_modules": [], "ambiguous_symbols": []}
}
```

`before` 完整取自本次上传源码的模块级函数签名，包括参数默认值、注解、异步标记和返回注解；`after` 根据 operation 增加一个必填参数或删除一个指定普通参数。`validation.diagnostics` 保存变更配置及 Core Validator 的错误；顶层 `diagnostics` 保存项目解析与 import 诊断。目标不存在或签名无效时返回 HTTP 422，结构仍与上例相同，`validation.valid=false`；无法构建 ChangeSpec 时 `change_spec=null`。指纹不一致返回 HTTP 409 `fingerprint_mismatch`，不会用另一份源码继续校验。返回结果不包含服务器临时路径，用户源码保持原样。

正常返回的顶层字段为 `project_name: string`、`project_fingerprint: string`、`coverage: object`、`change_spec: object`、`validation: object`、`diagnostics: object`。校验失败但 ZIP 可读取时仍返回这些字段，`change_spec` 允许为 `null`，`validation.valid=false`，原因位于 `validation.diagnostics[]` 的 `code` 与 `message`。

## `POST /api/v1/projects/analyze`

请求字段与 `POST /api/v1/changes/validate` 相同：`multipart/form-data` 中各一个 `file`（Python 项目 ZIP）和 `change`（上一节的简化 JSON 字符串），可选一个 `expected_fingerprint`。请求体与 ZIP 继续使用 Phase 2.2 的全部安全和大小限制。指纹不符时停止；指纹通过后，在同一请求的同一临时项目目录内构建并校验 ChangeSpec，校验有效才调用现有 `analyze_project()` 和 `build_report()`。不接受服务器路径、查询参数或额外表单字段。

| 请求字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | ZIP 文件（二进制 multipart part） | 是 | 本次实际分析的项目 |
| `change` | string（JSON 文本） | 是 | 与 validate 相同的简化配置 |
| `expected_fingerprint` | string（64 位十六进制） | 否 | 与本次 ZIP 字节核对 |

| 正常返回字段 | 类型 | 含义 |
| --- | --- | --- |
| `schema_version` | integer | Core JSON Report 版本，当前为 `1` |
| `project_path` | string | 上传项目相对根目录，固定为 `.` |
| `change`、`validation` | object | 实际分析的结构化 ChangeSpec 及校验结果 |
| `coverage`、`summary` | object | 覆盖范围及 Direct/Indirect 等计数 |
| `direct_impacts`、`indirect_impacts` | object[] | 证据位置、原因与上游路径 |
| `evidences` | object[] | 每条确定 Direct 和 Indirect 影响对应的源码证据 |
| `explanations` | object[] | 与 `evidences` 等长、同序的解释记录 |
| `manual_reviews`、`pre_existing_problems` | object[] | 静态证据不足和变更前已有问题 |
| `diagnostics` | object | 解析错误、未解析调用及 import |

```powershell
curl.exe -X POST -F "file=@project.zip;type=application/zip" -F "change=<change.json" -F "expected_fingerprint=<此前 inspect 返回的 64 位指纹>" http://127.0.0.1:8000/api/v1/projects/analyze
```

成功返回 HTTP 200，主体为 Core JSON Report。其 `schema_version`、`change`、`validation`、`coverage`、`summary`、`direct_impacts`、`indirect_impacts`、`evidences`、`explanations`、`manual_reviews`、`pre_existing_problems` 和 `diagnostics` 字段及影响语义与 CLI JSON 格式一致。HTTP 响应把 `project_path` 规范为项目相对根目录 `"."`；调用点、证据路径和诊断中的文件路径也均相对于项目根目录，不能显示服务器临时绝对路径。上传目录在成功或失败后均清理。固定 signature_change Demo 打成 ZIP 后，预期 `summary` 中 Direct、1-hop、2-hop 各为 `1`，`coverage.status="complete"`。

`evidences[]` 是新增的顶层数组，顺序为确定 Direct、1-hop / 2-hop Indirect Finding 的现有顺序。每项包含 `impact_type`、`target_symbol`、`location`（项目相对 `file`、1 起始的 `line`、0 起始的 `column`、可空 `end_line`）、`source_snippet`、`source_hash`（完整源文件原始字节的 SHA-256）、`rule`、`reason`、`propagation_path`。另外提供 `call_expression`、`evidence_reference`、`status` 与 `diagnostics[]`。Direct 的 `propagation_path` 为空；Indirect 的每条路径包含 `symbols[]`、`call_sites[]` 和 `direct_evidence_reference`，可追溯到原始 Direct 调用。`status=unavailable` 时片段或哈希可为 `null`，`diagnostics[]` 给出原因；影响结论和原有计数仍保留。`manual_reviews` 与既有问题目前不生成 `evidences[]` 条目。原有字段名称与 `schema_version=1` 保持不变。

`explanations[]` 与 `evidences[]` 一一对应，每项为 `{ "evidence": <原 evidence 对象>, "explanation": <ExplanationResult 或 null>, "diagnostics": [] }`。`explanation` 包含 `summary`、`why_affected`、`risk_level`、`suggested_check`、`confidence`。源码证据不可用时，`explanation=null` 且该项 `diagnostics[]` 含 `evidence_unavailable`；Provider 失败时优先返回规则解释，静态影响及 Evidence 保持不变。默认 `OPENIMPACT_LLM_PROVIDER=rule`，不调用外部模型。配置为 `deepseek` 且存在 `DEEPSEEK_API_KEY` 时，解释阶段向 DeepSeek 发送 `ExplanationInput` 中的变更描述、源码片段、位置、规则、原因和调用路径；不发送整个 ZIP。模型不可用或输出无效时自动使用规则解释。

若 `coverage.status="partial"`，`coverage.message` 明确提示结果仅覆盖已解析代码，零条影响不表示全项目确定无影响；解析错误及未解析调用仍在 `diagnostics`。ChangeSpec 配置或校验失败返回 HTTP 422，使用上一节的 `change_spec`、`validation`、`diagnostics` 结构，不产生影响报告。ZIP 或指纹错误延续相同的 `error.code` 格式；内部分析异常返回 HTTP 500 `analysis_failed`，不回传临时路径或异常详情。

`coverage.status` 为 `complete` 或 `partial`。inspect / validate 在解析错误、未解析 import 或模块/符号歧义时标记 partial；analyze 还将未解析调用计入 partial。`diagnostics.parse_errors[].file`、`diagnostics.unresolved_imports[].file`、`diagnostics.unresolved_calls[].file` 使用项目相对路径。解析失败的文件不会生成虚构的 Symbol 或调用证据。Direct 表示本次 Change 确定造成调用不兼容；1-hop / 2-hop 表示位于 Direct 上游的待检查调用路径。`manual_reviews` 不计为确定 Direct，`pre_existing_problems` 不归因于本次 Change。

## 错误响应

本阶段由服务显式处理的错误使用以下 JSON 形状：

```json
{"error": {"code": "unsupported_input", "message": "Demo 接口不接受项目路径、查询参数或请求体。"}}
```

| HTTP 状态 | `error.code` | 场景 |
| --- | --- | --- |
| 400 | `unsupported_input` | Demo 请求包含查询参数或非空请求体 |
| 503 | `demo_unavailable` | 内置 Demo 文件缺失或无法读取 |
| 503 | `demo_invalid` | 内置 ChangeSpec 与项目源码校验失败 |
| 400 | `unsafe_zip_entry` | ZIP 路径、链接、特殊文件、重复路径等不安全条目 |
| 400 | `invalid_zip` | 非 ZIP、损坏的 ZIP 或解压校验失败 |
| 400 | `unsupported_input` | inspect / validate / analyze 包含查询参数或额外表单字段 |
| 413 | `zip_limit_exceeded` | 上传、条目数、文件数、解压大小或压缩比超限 |
| 415 | `unsupported_zip_entry` | 加密或不支持的压缩方法 |
| 422 | `no_python_files` | ZIP 内没有可分析的 `.py` 文件 |
| 503 | `inspection_unavailable` | ZIP 请求的服务端临时目录或源码读取失败 |
| 409 | `fingerprint_mismatch` | validate / analyze 本次 ZIP 与预期 SHA-256 不一致 |
| 422 | `invalid_fingerprint` | `expected_fingerprint` 不是 64 位十六进制值 |
| 422 | `validation.valid=false` | ChangeSpec 配置、目标或 Core 签名校验失败；详见 `validation.diagnostics` 的 `code`、`message` |
| 500 | `analysis_failed` | 上传项目通过 ZIP 与 ChangeSpec 校验后，内部影响分析失败 |
| 503 | `database_unavailable` | 项目库或报告历史数据库无法写入或读取 |
| 404 | `project_not_found` | 项目 ID 不存在 |
| 404 | `report_not_found` | 历史报告 ID 不存在 |
| 422 | `invalid_pagination` | 项目库或历史报告分页参数不合法 |
| 500 | `internal_error` | 未被既有错误分支处理的后端异常（例如建立上传项目索引失败）；仅返回固定安全消息 |

缺少必填字段或 multipart 格式错误时，FastAPI 返回标准 `detail` 格式的 422 / 400；未知路径或 HTTP 方法返回标准 404 / 405。当前接口无认证、Worker 或任意服务器路径输入能力；项目库只保存本机项目/快照摘要和受控 ZIP 快照，报告历史只保存 report JSON 和摘要元数据。

普通 ZIP/输入错误和 HTTP 500 使用 `{"error":{"code":"...","message":"..."}}`；ChangeSpec 配置或校验错误使用 422 的 `validation.valid=false` 与 `validation.diagnostics[]`；FastAPI 对缺字段等框架级错误使用 `{"detail": ...}`。前端需按响应形状和状态码分支处理，不能假设所有非 200 响应都有相同结构。

Phase 3.4 稳定性验收记录见 [backend-stability-audit.md](backend-stability-audit.md)。公开路径与 JSON 字段名保持不变；异常响应不会拼接内部异常文本或堆栈。


## V1.1 模块领域追加契约

原 Function 请求与报告保持 v1。Inspect 追加 module_inventory / module_coverage / module_diagnostics；显式 module 请求沿用当前三个业务端点，输出独立 Module Report v1。详见 [模块变更契约](module-changes.md)。

## V1.2 符号领域追加契约

Inspect 再追加 `symbol_inventory`、`symbol_coverage`、`symbol_diagnostics`，原十个字段保持。Validate / Analyze 继续使用相同 multipart 字段、ZIP 和 fingerprint 规则；显式 `change_domain="symbol"` 接受 `rename_module_symbol` 或 `remove_module_symbol`。目标是当前 Inspect 返回的公开模块级变量/常量 ID。重命名另需 `new_symbol_name`，删除不接收该字段。

Symbol 报告采用独立 `(symbol, symbol_impact, schema_version=1)`，Direct 是真实符号引用断裂，Indirect 是上游模块待检查关系；不能按 Function 报告的参数兼容性字段解析。名称、目标和不支持定义错误返回422的既有 validation 结构，指纹错误409，内部异常安全500。完整字段、覆盖范围、计数单位、Evidence 对应及实际样例见 [符号变更契约](symbol-changes.md)。原两领域请求、报告与公开路径没有不兼容修改。

## 只读源码与报告追问（追加入口）

原 Inspect / Validate / Analyze 路径、报告字段及 schema_version 均保持。下面两个 POST 使用 `multipart/form-data`，复用原 ZIP 大小、解压、防路径逃逸与清理规则。禁止 URL 查询字段、未知或重复表单字段。

### POST /api/v1/projects/source

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| file | ZIP 文件 | 是 | 当前原始项目 ZIP |
| expected_fingerprint | 64 位十六进制字符串 | 是 | Inspect 返回的 ZIP SHA-256 |
| analysis_root | 字符串 | 否 | 与 Inspect 一致，默认 `.` |
| path | 字符串 | 否 | Scanner 文件列表内的 POSIX 相对 `.py` 路径；省略时只列目录 |

200 返回 `project_name`、`project_fingerprint`、`read_only=true`、`message`、`files` 和 `file`。`files[]` 为 `{path,size_bytes,source_hash}`；`file` 为 null 或 `{path,content,encoding,source_hash,line_count}`。哈希使用原始文件字节，编码遵循 Python 源码声明；内容以纯文本读取，包括存在 SyntaxError 的文件。读取范围与分析覆盖范围分别成立。

### POST /api/v1/reports/questions

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| file / expected_fingerprint / analysis_root | 同上 | 前两者是 | 同一份 ZIP 与源码根目录 |
| change | JSON 字符串 | 是 | 原 Validate / Analyze 简化配置，支持三个领域 |
| question | 字符串 | 是 | 非空，最多 1000 字符 |
| finding_index | 非负整数的十进制字符串 | 否 | 对应当前报告 `evidences[]` 序号；零记录时省略 |
| history | JSON 数组字符串 | 否 | 默认 `[]`；最多六条 `{role,content}`，role 仅 user/assistant，content 最多 800 字符，总 JSON 最多 6000 字符 |

200 返回 `answer`、`status`（answered / limited）、`provider`（rule / deepseek / fallback）、`fallback_reason`（安全原因码或 null）、`citations[]`（`id,file,line,column`）、`project_fingerprint`、`finding_index`（整数或 null）、`change_domain`、`coverage` 与 `scope=current_change_report`。

引用来自后端重建的真实报告。每次最多十二个位置、三条代表性传播路径、4000 字符源码片段；模型上下文超过 24000 字符时回退。模型必须返回 `answer,status,citation_ids` 并只引用给定 ID，否则回退。此处明确返回调用来源，原有 Explanation 字段保持不变。追问无法改变静态结论；模型失败保持 HTTP 200 并明确 `provider=fallback`。

### POST /api/v1/reports/question-suggestions

追加的推荐追问入口采用 multipart/form-data。必填 `file`、`change`、`expected_fingerprint`；可选 `finding_index`、`analysis_root`，含义和上面的追问接口一致。不接受 `question`、`history` 或客户端报告。复用同一 ZIP 安全限制、线程池、真实报告重建和临时清理；旧接口与 Report schema 保持原样。

200 返回 `questions[]`、`status`（available / unavailable）、`provider`（deepseek / rule / fallback）、`fallback_reason`、中文 `message`，以及上面相同的指纹、索引、领域、覆盖范围和 scope 字段。

- 模型成功：`questions[]` 为 2～3 项 `{question,citations}`；中文问题最多 160 字符，不重复，引用只能来自当前证据。每个 citation 仍为 `{id,file,line,column}`。无对应证据时仅推荐范围问题，引用可为空。
- 离线 `rule` 模式：`status=unavailable, provider=rule, questions=[]`，不请求模型，也不以固定问题替代模型推荐。
- 无 Key、认证/网络失败、非法 JSON、重复或越界问题、伪造引用：`status=unavailable, provider=fallback, questions=[]`，附安全原因码，最多请求一次，不自动重试。

每次由用户主动生成，避免页面切换时自动消耗 Token；点击推荐问题后，原追问接口再独立生成回答。格式和引用校验不能保证问题的全部自然语言假设正确，模型输出仍需核查。错误 HTTP 状态沿用下表。

### 错误响应

沿用既有安全错误结构 `{"error":{"code":"...","message":"..."}}`，不暴露服务器路径、堆栈或 Key。ZIP 原错误状态和 Change 校验的既有 `validation` 错误结构继续适用。

| HTTP | 典型情况 |
| --- | --- |
| 400 | 无效/危险 ZIP、未知/重复/查询输入 `unsupported_input` |
| 404 | `source_not_found` |
| 409 | `fingerprint_mismatch` |
| 413 | 上传或解压限制，沿用 ZIP 错误码 |
| 422 | 缺少必填字段、`invalid_fingerprint`、`invalid_source_path`、`source_encoding_error`、`invalid_question`、`invalid_question_context`，或原 Change 校验错误 |
| 500 | `workspace_failed`，安全通用消息 |
| 503 | `source_unavailable`，临时源码无法读取 |

请求成功或失败均清理临时目录，不保留上传项目。客户端需在项目/变更/影响记录改变时取消并丢弃旧回答；参考 [使用与边界](report-workspace.md)。

## 函数报告的可选相关测试定位

`POST /api/v1/projects/analyze` 的请求和原响应字段不变。函数签名报告在项目含 pytest 默认命名测试文件时，可追加 `related_tests`，schema_version 仍为 1；没有测试文件的旧样例不新增字段。模块、符号报告保持原样。旧消费者可忽略该可选字段，新消费者必须支持缺省、空候选和 unavailable。

候选仅来自已有确定影响与两层上游路径，提供实际测试函数、源码位置和检查理由。服务未实际收集或运行测试；manual_review / unresolved 不作为确定关联来源，partial 时不能将空候选解释为无需回归。具体字段和限制见 [相关测试定位契约](related-tests.md)。
