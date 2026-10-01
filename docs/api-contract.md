# Nexus OpenImpact API 契约

Phase 2.1 提供仓库内置 `examples/signature_change/` 的分析。Phase 2.2 增加上传 Python 项目 ZIP 的语法检查。Phase 2.3 增加简化配置生成与校验 ChangeSpec。Phase 2.4 增加上传项目的完整影响分析，调用现有 `analyze_project()` 和 `build_report()`。

## 前后端冻结范围

| HTTP Method | Path | Content-Type | 用途 | 成功状态 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/projects/inspect` | `multipart/form-data` | 检查上传 ZIP 的模块、Symbol 与覆盖情况 | 200 |
| POST | `/api/v1/changes/validate` | `multipart/form-data` | 从上传源码构建并校验 ChangeSpec | 200 |
| POST | `/api/v1/projects/analyze` | `multipart/form-data` | 在本次上传项目上生成完整影响报告 | 200 |

三个正式业务接口都需要重新上传 ZIP。V1 不保留用户项目，也不提供项目 ID；每次请求在独立临时目录完成并清理。`expected_fingerprint` 是 ZIP 原始字节的 SHA-256 校验值，不是服务端项目查找键。同一源码重新打包也可能产生不同指纹；修改或重新打包后应重新 inspect。文件名只用于展示项目名称的回退值，不参与指纹计算。不接受服务器本地路径、查询参数或额外表单字段。

三个接口的 `file` 均为 multipart 文件字段，建议浏览器以 `application/zip` 上传；服务以 ZIP 内容及安全规则判断，不依赖客户端声明的 MIME。每个请求的 multipart 总量最多 5 MiB + 64 KiB，其中 ZIP 文件最多 5 MiB。其余 ZIP 条目和解压限额见下文。前端交接示例见 [frontend-handoff.md](frontend-handoff.md)，真实响应见 [api-samples](api-samples)。

## 本地启动

在仓库根目录安装项目后运行：

```powershell
pip install -e .
python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

运行自动化测试时可安装 `pip install -e ".[test]"`；`httpx` 和 `pytest` 位于该可选依赖中。服务入口为 `openimpact.api:app`。目前 Demo 从当前源码仓库读取，运行服务时需保留 `examples/signature_change/`。

## `GET /api/v1/health`

无需请求体。成功响应为 HTTP 200：

```json
{"status": "ok", "version": "0.1.0"}
```

## `POST /api/v1/demo/analyze`

无需请求体或查询参数。例如：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/demo/analyze
```

成功响应为 HTTP 200，直接返回 Core CLI JSON 模式使用的 `build_report()` 结果。顶层字段保持为：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 当前为 `1` |
| `project_path` | 内置 Demo 的本地目录 |
| `change` | 结构化 ChangeSpec |
| `validation` | ChangeSpec 校验结论和诊断 |
| `coverage` | 覆盖状态、模块与解析计数 |
| `summary` | Direct、1-hop、2-hop、人工检查等计数 |
| `direct_impacts` | 本次变更确定造成的直接影响 |
| `indirect_impacts` | 上游待检查符号及原始调用路径 |
| `evidences` | Direct 与 Indirect 的源码片段、哈希和传播证据；证据读取失败时附诊断 |
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
| `added_parameter.name` | string | 是 | 新增参数名；合法性由 Core Validator 判断 |
| `added_parameter.kind` | string 枚举 | 是 | `positional_only`、`positional_or_keyword` 或 `keyword_only` |
| `insert_before` | string | 否 | 目标函数中已有参数名；新增参数插在其前面 |

```json
{
  "target_symbol_id": "utils.format_date",
  "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}
}
```

`added_parameter.kind` 仅允许 `positional_only`、`positional_or_keyword`、`keyword_only`。默认插入位置为该参数类型组的末尾、下一类型组的开头；如果这导致非法签名，返回 Core Validator 的 `invalid_after_signature`，不会自行寻找其他插入点。可选 `"insert_before": "现有参数名"` 指定插入在该参数之前，仍由 Core Validator 判断合法性。接口总是生成 `add_required_parameter`，新增参数 `required=true` 且无默认值；其他变更类型、默认值及额外字段不在本接口范围内。

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

`before` 完整取自本次上传源码的模块级函数签名，包括参数默认值、注解、异步标记和返回注解；`after` 只增加一个必填参数。`validation.diagnostics` 保存变更配置及 Core Validator 的错误；顶层 `diagnostics` 保存项目解析与 import 诊断。目标不存在或签名无效时返回 HTTP 422，结构仍与上例相同，`validation.valid=false`；无法构建 ChangeSpec 时 `change_spec=null`。指纹不一致返回 HTTP 409 `fingerprint_mismatch`，不会用另一份源码继续校验。返回结果不包含服务器临时路径，用户源码保持原样。

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
| `manual_reviews`、`pre_existing_problems` | object[] | 静态证据不足和变更前已有问题 |
| `diagnostics` | object | 解析错误、未解析调用及 import |

```powershell
curl.exe -X POST -F "file=@project.zip;type=application/zip" -F "change=<change.json" -F "expected_fingerprint=<此前 inspect 返回的 64 位指纹>" http://127.0.0.1:8000/api/v1/projects/analyze
```

成功返回 HTTP 200，主体为 Core JSON Report。其 `schema_version`、`change`、`validation`、`coverage`、`summary`、`direct_impacts`、`indirect_impacts`、`evidences`、`manual_reviews`、`pre_existing_problems` 和 `diagnostics` 字段及影响语义与 CLI JSON 格式一致。HTTP 响应把 `project_path` 规范为项目相对根目录 `"."`；调用点、证据路径和诊断中的文件路径也均相对于项目根目录，不能显示服务器临时绝对路径。上传目录在成功或失败后均清理。固定 signature_change Demo 打成 ZIP 后，预期 `summary` 中 Direct、1-hop、2-hop 各为 `1`，`coverage.status="complete"`。

`evidences[]` 是新增的顶层数组，顺序为确定 Direct、1-hop / 2-hop Indirect Finding 的现有顺序。每项包含 `impact_type`、`target_symbol`、`location`（项目相对 `file`、1 起始的 `line`、0 起始的 `column`、可空 `end_line`）、`source_snippet`、`source_hash`（完整源文件原始字节的 SHA-256）、`rule`、`reason`、`propagation_path`。另外提供 `call_expression`、`evidence_reference`、`status` 与 `diagnostics[]`。Direct 的 `propagation_path` 为空；Indirect 的每条路径包含 `symbols[]`、`call_sites[]` 和 `direct_evidence_reference`，可追溯到原始 Direct 调用。`status=unavailable` 时片段或哈希可为 `null`，`diagnostics[]` 给出原因；影响结论和原有计数仍保留。`manual_reviews` 与既有问题目前不生成 `evidences[]` 条目。原有字段名称与 `schema_version=1` 保持不变。

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

缺少必填字段或 multipart 格式错误时，FastAPI 返回标准 `detail` 格式的 422 / 400；未知路径或 HTTP 方法返回标准 404 / 405。当前接口无认证、项目持久化、Worker 或任意服务器路径输入能力。

普通 ZIP/输入错误和 HTTP 500 使用 `{"error":{"code":"...","message":"..."}}`；ChangeSpec 配置或校验错误使用 422 的 `validation.valid=false` 与 `validation.diagnostics[]`；FastAPI 对缺字段等框架级错误使用 `{"detail": ...}`。前端需按响应形状和状态码分支处理，不能假设所有非 200 响应都有相同结构。
