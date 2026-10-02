# OpenImpact 前端交接：后端接口冻结范围

更新日期：2026-10-02，Phase 4.1 前端接入准备。Backend v1 提供健康检查与三个正式业务接口，字段、状态码与大小限制以 [API 契约](api-contract.md) 为准。后端报告版本为 `schema_version=1`；公开字段和 API 路径保持不变。本轮不开发 React，使用 rule 模式联调。

## 启动后端与健康检查

在仓库根目录运行，要求 Python 3.11 或更新版本；已有虚拟环境时可跳过创建步骤：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:OPENIMPACT_LLM_PROVIDER = "rule"
.\.venv\Scripts\python.exe -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

这是后端本地启动示例，端口 8000 来自现有后端使用说明；前端开发端口及最终部署地址仍待确认。无需设置 PYTHONPATH，无需模型 Key。另开终端检查：

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/health
```

预期 HTTP 200，JSON 为 `{"status":"ok","version":"0.1.0"}`。健康检查用于确认服务可达，不验证项目分析结果。后端还提供 `/docs` 供查看请求定义。

## 本地地址与 CORS 待确认项

当前 FastAPI **没有配置 CORS**，后端保持跨域关闭，没有 `allow_origins=["*"]`。负责人已确认前端实际 Origin 尚未确定，本轮不添加 CORS 中间件、不猜测前端端口，也不添加尚未实现的 CORS 环境变量。

前端成员需提供浏览器实际访问的开发服务器 **Origin：协议 + 主机 + 端口**，不含页面路径。`localhost` 与 `127.0.0.1`、不同端口和不同协议分别属于不同 Origin。需要多个地址时，逐个提供并由负责人确认。

接入方式需由成员明确选择：

| 方式 | 前端请求地址 | 当前条件 |
| --- | --- | --- |
| 开发服务器已配置 `/api` 代理或最终同源访问 | `/api/v1/...` | 相对地址指向当前页面所在服务器，必须有实际代理或同源路由；本仓库没有替成员配置代理 |
| 浏览器直接请求独立后端 | 后端 base URL + `/api/v1/...` | 当前跨域关闭，浏览器会阻止前端读取跨域响应；需先确认 Origin 再配置 |

后续确认 Origin 后，通过后端环境配置加载**明确白名单**，默认不开放跨域，变更配置后重启后端。届时只开放当前所需 GET / POST 与必要请求头，验证 OPTIONS 预检、允许和拒绝的 Origin，以及错误响应上的 CORS 头；不将本地地址硬编码为生产部署地址。当前没有登录或 Cookie 会话，联调不需要 `credentials: "include"`。

curl、PowerShell、pytest HTTP 客户端能收到响应，不能证明浏览器跨域接入已经可用。浏览器出现网络/CORS 错误时通常拿不到业务 JSON，应分别核对后端可达性、base URL、代理及 Origin，避免把它当作 ChangeSpec 校验错误。

## 请求速查

| Method / Path | 请求 | 成功结果 |
| --- | --- | --- |
| GET `/api/v1/health` | 无请求体 | `status`、`version` |
| POST `/api/v1/projects/inspect` | multipart：恰好一个 `file` 文件字段 | 模块、`symbols[]`、`project_fingerprint`、coverage、diagnostics |
| POST `/api/v1/changes/validate` | multipart：各一个 `file`、`change` 文本，可选一个 `expected_fingerprint` 文本 | `change_spec`、`validation`、项目指纹及诊断 |
| POST `/api/v1/projects/analyze` | 与 validate 相同 | 完整 Core JSON Report |

`change` 是 `JSON.stringify(...)` 后的普通表单字符串；不能以整个 JSON 请求体代替 multipart，也不能把 `change` 作为文件或 Blob 上传。当前不接受 query 参数、服务器路径、重复字段或额外表单字段。ZIP 最多 5 MiB，整个 multipart 最多 5 MiB + 64 KiB；其余文件数、解压限额见 API 契约。

## 页面工作流

1. 用户选一个 Python 项目 ZIP。前端保存当前 `File` 对象，调用 inspect，从 `symbols[]` 展示可选目标。每个目标使用完整 `symbol_id`，例如 `utils.format_date`；不要只传函数短名。
2. 用户填写新增必填参数的 `name` 与 `kind`。前端把简化配置序列化成 JSON 字符串，连同**同一 ZIP 文件**和 inspect 返回的 `project_fingerprint` 调用 validate。有效时可展示 `change_spec.before`、`after` 及 `validation.valid=true`。
3. 用户确认配置后，重复上传同一 ZIP 与同一配置到 analyze，并传相同的 `expected_fingerprint`。展示 `summary`、Direct 调用点、1-hop / 2-hop 上游路径、人工检查项及诊断。

V1 不保存上传项目，不返回项目 ID。刷新页面或更换 ZIP 后，需要重新 inspect；前端应清除旧指纹、Symbol 选择和 ChangeSpec。指纹来自 ZIP **原始字节**，同样的源码重新打包也可能得到新指纹。三步上传均使用 `multipart/form-data`；让浏览器为 `FormData` 自动设置带 boundary 的 `Content-Type`，不要手动设置该请求头。

每个请求结束后临时源码已清理，后续接口只能从再次上传的 ZIP 读取项目。`project_fingerprint` 用于检查字节是否一致，不能用来取回服务器项目。前端应在三步流程中保留原始 `File`，不要从解析结果重新打包或改写文件。用户改变参数配置后应重新 validate，并清除旧分析报告。`expected_fingerprint` 在 API 中可选，前端正常流程应始终传入 inspect 返回值。

```ts
// baseURL 由成员的环境配置提供。
// 使用已配置的 /api 代理时可传 ""；独立后端直连需先完成 CORS 白名单。
const baseURL = backendBaseURL.replace(/\/$/, "");
const change = {
  target_symbol_id: selectedSymbolId,
  added_parameter: { name: parameterName, kind: parameterKind },
  // 若需明确位置，可增加 insert_before: existingParameterName
};

function formFor(file: File, change?: object, fingerprint?: string): FormData {
  const form = new FormData();
  form.append("file", file);
  if (change) form.append("change", JSON.stringify(change));
  if (fingerprint) form.append("expected_fingerprint", fingerprint);
  return form;
}

async function postForm(path: string, form: FormData) {
  const response = await fetch(baseURL + path, { method: "POST", body: form });
  const body = await response.json();
  if (!response.ok) {
    // 供调用者按下文三类错误结构展示，保留 validation / diagnostics。
    throw { status: response.status, body };
  }
  return body;
}

const inspectBody = await postForm("/api/v1/projects/inspect", formFor(file));
const fingerprint = inspectBody.project_fingerprint;
// selectedSymbolId 来自 inspectBody.symbols[].symbol_id。
const validateBody = await postForm(
  "/api/v1/changes/validate", formFor(file, change, fingerprint),
);
if (validateBody.validation.valid !== true) throw { body: validateBody };
const report = await postForm(
  "/api/v1/projects/analyze", formFor(file, change, fingerprint),
);
```

示例是接口调用片段，`file`、`selectedSymbolId`、参数配置和 `backendBaseURL` 由页面提供。调用者应捕获业务错误、网络/CORS 错误以及非 JSON 响应；任一步失败均停止后续步骤，保留当前输入让用户处理。项目显示名称不能替代 Symbol ID；同名函数必须使用完整 ID 区分。

## 展示语义

| 字段 | 前端呈现建议 |
| --- | --- |
| `summary` | 展示 `direct_impact_count`、`indirect_1hop_count`、`indirect_2hop_count`、`manual_review_count`、`pre_existing_problem_count`、`unresolved_call_count`；各项单位不同，不能相加当作受影响函数总数 |
| `coverage.status` | `partial` 时显著显示 `coverage.message`（analyze）及诊断；零个 Finding 不能表述为全项目无影响 |
| `direct_impacts[]` | 展示相对 `file`、行/列、caller、target、规则与原因；代表本次 Change 确定造成调用不兼容 |
| `indirect_impacts[]` | 展示 `impacted_symbol_id`、距离、`sources[].propagation_path`；语义为上游路径需要检查 |
| `evidences[]` | 显示项目相对位置、源码片段、完整文件 SHA-256 与 Indirect 传播路径。`status=unavailable` 时显示该项 `diagnostics[]`，保留原影响结论；关联规则见下文 |
| `explanations[]` | 与 `evidences[]` 同序；显示 `explanation` 中的中文说明。若为 `null`，显示该项 `diagnostics[]`，继续展示 Evidence 与原影响结论 |
| `manual_reviews[]` | 独立于确定 Direct 计数展示 |
| `pre_existing_problems[]` | 标记为修改前已有问题 |
| `diagnostics` | 解析错误、未解析 import / 调用独立展示；文件路径已是项目相对路径 |

`added_parameter.kind` 当前只接受 `positional_only`、`positional_or_keyword`、`keyword_only`。默认插在同类型参数组末尾。必要时传 `insert_before`，值必须是目标函数已有参数名；最终合法性以 Core Validator 的 `validation.diagnostics` 为准。前端无需自行拼装完整 ChangeSpec，也无需执行 Python 参数规则。

### Evidence 与 Explanation 的关联

- `explanations.length === evidences.length`，`explanations[i].evidence` 与 `evidences[i]` 内容一致；展示时先按同一索引关联，不分别排序两个数组。
- `evidences` 顺序为 `direct_impacts` 对应证据在前，`indirect_impacts` 对应证据随后。只包含确定 Direct 与 Indirect，不包含 manual review 和既有问题。`evidences.length === direct_impacts.length + indirect_impacts.length`，也适用于不可用证据占位项。
- Direct 可按 `impact_type`、`target_symbol` 与对应 Finding 的 `target_symbol_id`、相对文件、行列匹配。当前 `direct_impacts[]` 未返回 `evidence_reference`，不能假设该字段存在。
- Indirect 的 `target_symbol` 仍是本次变更目标；受影响的上游函数来自 `indirect_impacts[].impacted_symbol_id`，可与证据路径的首个 `symbols` 匹配。证据生成异常时路径可能为空，可按上述稳定顺序关联，不能猜测符号。
- 每条间接路径的 `direct_evidence_reference` 指向 Direct Evidence 的 `evidence_reference`。`evidence_reference` 在证据不可用或旧模型缺少元信息时可为空，应保留空值处理。
- `location` 可为 null；`source_snippet`、`source_hash` 也可为 null。行号从 1 开始，column 从 0 开始。`source_hash` 是对应完整源码文件的 SHA-256；ZIP 指纹是上传字节的 SHA-256，二者用途不同。
- 源码、诊断和解释作为文本展示；不要将上传项目中的文本直接作为 HTML 渲染。

### unavailable、fallback 与 partial

| 状态 | 含义 | 前端处理 |
| --- | --- | --- |
| Evidence `status=unavailable` | 证据片段不可用或生成失败 | 显示证据诊断，保留静态影响、计数；对应 explanation 为 null |
| `explanation=null` | 该项解释生成失败或证据不足 | 显示 `explanations[i].diagnostics`，继续展示可用 Evidence |
| Provider fallback | 模型或 Provider 失败后使用规则解释 | 当前 API 没有 `provider_used`、`fallback_reason` 或模型成功状态字段，前端无法逐项识别回退来源；统一显示“中文解释” |
| `coverage.status=partial` | 解析或符号/调用分析范围不完整 | 明确展示覆盖提示与 diagnostics；零条影响不能宣称全项目没有影响 |

本轮后端启动配置明确使用 rule，解释来自规则模板。即使以后启用模型，HTTP 200、`confidence=1.0`、解释非空或该项 diagnostics 为空均不能证明模型调用成功；模型来源诊断目前仅在后端本地联调记录中。`risk_level=unknown` 表示缺少业务风险依据；confidence 表示解释对证据的忠实程度，不能显示为运行失败概率。

`coverage=complete` 只说明当前支持范围内的解析/解析关系诊断没有触发 partial；它不保证覆盖所有 Python 动态行为。Evidence 失败不会改变静态 coverage，应同时展示证据可用性。inspect / validate 的 diagnostics 包含解析错误、未解析 import 与模块/符号歧义；analyze 另包含 unresolved_calls，歧义信息位于 coverage，结构不完全相同。analyze 的 partial 提供 `coverage.message`；inspect / validate 不保证该字段存在。

## 错误处理

错误有三种现有结构，前端按实际字段分支，不应只读取 `error.message`：

| 响应结构 | 典型状态 | 显示来源 |
| --- | --- | --- |
| `{error: {code, message}}` | ZIP / 指纹 / 服务异常 | `error.message`，按 code 提供处理动作 |
| `{validation: {valid:false, diagnostics:[...]}, ...}` | 422 配置或签名错误 | `validation.diagnostics[].code/message`；`change_spec` 可为 null，保留项目 diagnostics |
| `{detail: ...}` | 框架 400 / 422，以及 404 / 405 | multipart 字段缺失、格式或调用路径/方法错误 |

- `409 fingerprint_mismatch`：当前 ZIP 与 inspect 时不同；提示用户重新 inspect。
- `422` 且有 `validation.valid=false`：显示 `validation.diagnostics[]`。此时 analyze 未执行影响分析。
- `400/413/415/422` 且有 `error`：显示 `error.message`；常见原因是 ZIP 损坏、不安全条目、超限或没有可分析 `.py`。
- 框架级 `400/422` 且有 `detail`：检查 multipart 字段缺失或格式错误。
- `500 analysis_failed` / `internal_error` 或 `503 inspection_unavailable`：显示可重试提示；响应不包含内部堆栈或临时路径。

指纹不一致时清除旧 Symbol、验证结果和报告，用当前原始 ZIP 重新 inspect；不能为了绕过 409 自动省略 fingerprint。参数名重复、类型不支持、insert_before 不存在或签名顺序非法时，展示 validator 诊断，由用户调整输入后重新 validate。服务错误允许用户手动重试，避免无提示循环提交。

## 前端成员联调清单

1. 提供实际开发 Origin 与后端 base URL，确认使用代理还是等待明确 CORS 白名单；当前直连跨域尚未开放。
2. 启动 rule 后端，检查 health 200。
3. 上传同一 Demo ZIP，从 inspect 选择 `utils.format_date`，提交新增必填参数 `timezone`、`positional_or_keyword`，validate 应返回 valid=true。
4. analyze 应返回 Direct / 1-hop / 2-hop 各 1、complete，以及三条相对应的 Evidence / Explanation。预期路径为 `page.page → dashboard.dashboard → report.report → utils.format_date`。
5. 试用无效 ZIP、非法参数与旧指纹，确认页面按三类错误结构处理；partial / unavailable 时保留可用结果并提示限制。
6. 前端页面的实际浏览器联调由成员完成；本轮接口与 HTTP 测试通过不等于未确认的跨域配置已经可用。

## 实际响应样例

以下文件由 FastAPI HTTP 测试客户端的实际响应生成，使用仓库公开的 `examples/signature_change/` 构造固定内容 ZIP。样例已省去 HTTP 头，JSON 字段保持接口原样；上传项目报告中的 `project_path` 为相对根目录 `.`，不含服务器临时路径。

| 操作 | 响应样例 |
| --- | --- |
| Inspect，HTTP 200 | [inspect-response.json](api-samples/inspect-response.json) |
| Validate，HTTP 200 | [validate-response.json](api-samples/validate-response.json) |
| Analyze，HTTP 200 | [analyze-response.json](api-samples/analyze-response.json) |
| 修改 ZIP 后沿用旧指纹，HTTP 409 | [error-response.json](api-samples/error-response.json) |

本样例 ZIP 的 SHA-256 为 `9ab9885be3f7e7f5285a6e976ed02dc57e25bac055d0ecaa8701fca94f276d9e`。它只用于核对这四份响应，前端运行时应使用当前 inspect 的实际指纹。

## Phase 4.1 验收记录

新增 `tests/test_frontend_readiness.py`：6 项通过，核对 health、当前无 CORS 头/OPTIONS 不开放、multipart 三步流程、证据/解释对应规则及三类错误结构。完整 pytest 为 **241 passed、1 skipped、7 subtests passed**，另有一条现有第三方弃用警告；原有真实本地 HTTP 工作流与响应性测试继续通过。`git diff --check` 通过。

本轮仅修改交接/API 文档和测试，没有修改后端生产代码、Core 或 React，没有真实模型请求，未自动 Git commit。跨域直连仍待成员提供实际 Origin 并由负责人确认，未用 HTTP 测试结果宣称浏览器跨域联调完成。
