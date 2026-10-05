# OpenImpact 前端交接：后端接口冻结范围

普通包增量：上传页的“源码根目录”缺省为 `.`，src 布局填 `src`。三个业务请求在 FormData 中追加同一 `analysis_root`，并检查响应 `analysis_layout`，默认省略时视为 `.`。切换目录取消旧请求、更新 revision 并清空 Inspect / Validate / Report；更换 ZIP 重置目录，409 保留目录方便重新读取。Change JSON、fingerprint 与三个领域工作流不变。`diagnostics.unsupported_scopes` 为新的可选诊断数组，需要显示具体排除范围；详见 [普通包能力](package-imports.md)。

更新日期：2026-10-03，补充 Web MVP 三人成果整合验收方案。Backend v1 提供健康检查与三个正式业务接口，字段、状态码与大小限制以 [API 契约](api-contract.md) 为准。后端报告版本为 `schema_version=1`；公开字段和 API 路径保持不变。本轮不开发 React，使用 rule 模式联调。

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

## Phase 4.1 验收记录（历史）

新增 `tests/test_frontend_readiness.py`：6 项通过，核对 health、当前无 CORS 头/OPTIONS 不开放、multipart 三步流程、证据/解释对应规则及三类错误结构。完整 pytest 为 **241 passed、1 skipped、7 subtests passed**，另有一条现有第三方弃用警告；原有真实本地 HTTP 工作流与响应性测试继续通过。`git diff --check` 通过。

该阶段仅修改交接/API 文档和测试，没有修改后端生产代码、Core 或 React，没有真实模型请求，未自动 Git commit。跨域直连仍待成员提供实际 Origin 并由负责人确认，未用 HTTP 测试结果宣称浏览器跨域联调完成。

## Web MVP 项目负责人执行清单（2026-10-03）

本节基于上述冻结契约、`src/openimpact/api.py`、`analysis/report.py`、`reporting/evidence.py`、`explanation/provider.py` 和现有测试。目标是验收成员交付的页面与后端整合效果，不要求增加页面业务或改变 Core。当前仓库没有可核验的 React / Evaluation 交付工程，浏览器步骤均为**待现场执行**；后端测试通过不等于页面验收通过。

### A. 开始前记录环境与交付版本

| 项目 | 当前事实 / 验收配置 | 负责人需确认 |
| --- | --- | --- |
| 后端版本 | 包版本 / health 为 0.1.0，报告 schema_version 为 1 | 后端 Git 提交、是否有未提交改动、Python 和依赖环境 |
| `OPENIMPACT_LLM_PROVIDER` | 后端已有进程环境变量，本次显式设置 `rule` | 后端启动终端设置正确；不要仅修改前端环境 |
| `DEEPSEEK_API_KEY` | 后端已有变量；rule 模式不需要、不调用模型 | 不要求提供或展示 Key，不写入浏览器、验收截图、HAR 或 Git |
| 前端 API base URL | 前端具体环境变量名尚未交付，`backendBaseURL` 仅是上文示例变量 | 前端成员提供实际变量名、配置位置、值与重启方式；不能假设一定使用 Vite 或已有 `VITE_API_BASE_URL` |
| React 开发 Origin | 协议、主机、端口尚待确认 | 成员提交浏览器实际 Origin，负责人确认；不猜测端口或最终部署地址 |
| CORS 白名单环境变量 | 后端目前未实现，跨域仍关闭 | 确认走已配置代理 / 同源方式，还是后续授权明确白名单配置；本轮不新增变量或中间件 |
| 后端 host / port | 现有启动命令的 CLI 参数；本地示例 127.0.0.1:8000 | 核对实际监听地址和代理目标；它们不是项目新增的环境变量 |
| `.env` 文件 | 后端直接读取进程环境，没有自动加载 `.env` 的实现 | 不把“文件写了变量”当作后端已生效；前端加载方式由成员确认 |
| Evaluation 交付 | 本仓库未找到可核验的评测产物 | 成员提供代码版本、样本 ZIP / SHA-256、结构化变化、预期结果、指标口径与复现命令 |

- [ ] 记录三人的提交版本或交付包版本，确认负责人验收的是同一组成果。
- [ ] 按上文启动 rule 后端；在浏览器 Network 中确认 health 返回 200、status=ok、version=0.1.0。
- [ ] 前端成员确认 `/api` 代理或浏览器可读取的实际后端地址。当前 CORS 关闭时，直接跨域失败应记录“接入条件待处理”，不能勾选浏览器验收通过。
- [ ] 打开浏览器 Console / Network，保留必要的请求和响应记录；本次不上传含真实凭据的源码。

### B. 准备标准 ZIP 与可复现异常样本

标准项目取自 `examples/signature_change/` 的四个 `.py` 文件，不修改原始目录。接口配置使用简化 JSON；仓库 `examples/signature_change/change.json` 是 **Core 完整 ChangeSpec**，不能直接当作 HTTP 的简化 `change` 表单配置。

以下命令在仓库根目录执行，仅读取公开 Demo、生成忽略目录中的验收样本，不运行目标代码，也不增加项目业务功能：

```powershell
@'
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from hashlib import sha256
import json

demo = Path("examples/signature_change")
output = Path(".local/web-mvp-acceptance")
output.mkdir(parents=True, exist_ok=True)
base = {p.name: p.read_bytes() for p in sorted(demo.glob("*.py"))}
assert set(base) == {"utils.py", "report.py", "dashboard.py", "page.py"}
cases = {
    "signature_change.zip": base,
    "partial.zip": {**base, "broken.py": b"def broken(:\n"},
    "partial_no_impact.zip": {"utils.py": base["utils.py"], "broken.py": b"def broken(:\n"},
    "changed_project.zip": {**base, "utils.py": base["utils.py"] + b"\n# acceptance revision\n"},
    "empty.zip": {},
}
for name, files in cases.items():
    destination = output / name
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for filename, content in sorted(files.items()):
            info = ZipInfo("signature_change/" + filename, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)
    print(name, sha256(destination.read_bytes()).hexdigest())
(output / "not-a-zip.txt").write_bytes(b"this is not a zip")
change = {"target_symbol_id": "utils.format_date",
          "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}}
(output / "change-config.json").write_text(json.dumps(change, indent=2) + "\n", encoding="utf-8")
'@ | .\.venv\Scripts\python.exe -
```

保存本次 `signature_change.zip` 的 SHA-256 为 F，三步使用**这同一个 ZIP File**。重新打包即使源码相同也可能改变 F；不要照搬上文 HTTP 样例的固定指纹。

### C. 浏览器逐步正常流程

| 步骤 | 用户操作 | 对应 API / 数据来源 | 正常预期 | 常见失败 | 页面必须展示 |
| --- | --- | --- | --- | --- | --- |
| 1. 上传 ZIP | 选择 signature_change.zip，点击检查 / 导入 | POST `/api/v1/projects/inspect`；multipart 仅 file | 200，指纹 F，4 个模块、4 个函数，complete | invalid_zip 400、no_python_files 422、超限 413、路径不安全 400、网络/CORS 错误 | 当前文件、检查状态、coverage、解析诊断；成功后可选择函数 |
| 2. 选择函数 | 在函数列表选择 utils.format_date | 本次 inspect 的 `symbols[]`；不发新增接口请求 | 完整 Symbol ID 匹配，当前参数 date，无默认值 | 使用旧 ZIP 的 Symbol、仅用短名、失败文件没有 Symbol | 完整 Symbol ID、utils.py、定义行 1、参数列表；不把项目名称当作目标 |
| 3. 配置 Change | 填 timezone，选择 positional_or_keyword；不填 insert_before | 组装简化 change 对象，尚未调用新接口 | 只配置新增必填参数；不让前端自行构造完整 before/after | 参数名重复 / 非法、kind 不支持、插入点不存在 | 修改意图和目标；参数形式可理解；修改配置后旧校验 / 报告失效 |
| 4. Validate | 点击校验，重新提交原始 ZIP、change 字符串和 expected_fingerprint=F | POST `/api/v1/changes/validate` | 200、valid=true、指纹 F；before 为 date，after 为 date + timezone，无默认值 | 422 validation.valid=false、409 fingerprint_mismatch、缺字段 detail 错误 | 真实 before/after、校验状态、validation.diagnostics；失败时不继续 Analyze |
| 5. Analyze | 校验成功后点击分析，提交同一 ZIP、配置和 F | POST `/api/v1/projects/analyze` | 200、schema_version=1、报告 change 等于 validate.change_spec；三类影响各 1、complete | 校验失败 422、指纹不符 409、analysis_failed / internal_error 500、服务不可用 503 | 加载 / 成功 / 失败状态、统计、直接 / 间接列表、coverage 和 diagnostics |
| 6. Evidence | 点击 report、dashboard、page 的结果，查看对应证据 | 本次 analyze 的 `evidences[]`，不再请求服务器源码路径 | 3 条 available 证据；源码、行号、哈希、规则和路径与对应 Finding 一致 | 证据 unavailable、location/snippet/hash 为 null、分别排序数组造成错配 | 相对文件、行列、代码文本、规则与原因、传播路径；缺失时保留静态结果并显示诊断 |
| 7. Explanation | 查看同一结果的中文解释 | `explanations[i]` 对应 `evidences[i]` | 3 条规则解释；Direct 解释参数不兼容，Indirect 说明上游待检查；risk unknown | explanation=null、来源不可识别、把回退当模型成功、把 confidence 当失败概率 | summary、why_affected、suggested_check、risk_level；缺失诊断；通用“中文解释”标签 |

Analyze 当前**不返回 project_fingerprint**，不要要求三次响应都具有该字段。通过 inspect / validate 响应中的 F、三步上传的同一文件、validate / analyze 请求中的 expected_fingerprint，以及报告 change 与 validated change_spec 的一致性验收快照绑定。

### D. 负责人逐项核对报告

| Finding | 数量与符号 | 调用证据 | 解释语义 |
| --- | --- | --- | --- |
| Direct | 1；caller=report.report，target=utils.format_date | report.py:5，column=11，`return format_date(date)`；规则 required_parameter_added_breaks_call | before compatible → after incompatible，本次新增 timezone 使调用确定不兼容 |
| 1-hop | 1；dashboard.dashboard | dashboard.py:5，`return report("2026-10-01")`；dashboard → report → format_date | 在确定 Direct 的上游，建议检查，不声称必然运行失败 |
| 2-hop | 1；page.page | page.py:5，`return dashboard()`；page → dashboard → report → format_date | 同上，距 Direct caller 两层 |

- [ ] `summary.direct_impact_count == direct_impacts.length == 1`。
- [ ] 1-hop / 2-hop 卡片分别等于 `indirect_impacts` 中对应 impact_type 的条数，均为 1；manual_review、pre_existing_problem、unresolved_call 均为 0。
- [ ] 图 / 列表显示完整 ID，不将 utils.format_date 算作 Direct caller；三类卡片不能相加后标为“受影响文件/函数总数”。
- [ ] `evidences.length == direct_impacts.length + indirect_impacts.length == 3`，与 `explanations.length` 相同，每个 `explanations[i].evidence` 内容等于 `evidences[i]`。
- [ ] Direct Evidence 的 `propagation_path` 为空；间接路径的 `direct_evidence_reference` 对应原始 Direct Evidence 的 `evidence_reference`，末端 call_site 对应 Direct 调用位置。2-hop 完整路径为 `page.page → dashboard.dashboard → report.report → utils.format_date`。
- [ ] Evidence 的 target_symbol 为变更目标；间接受影响符号来自 Finding 的 impacted_symbol_id。证据打不开时也没有把另一个结果的源码/解释显示过来。
- [ ] source_hash 是对应完整源码文件哈希；ZIP 指纹 F 用于 ZIP 身份核对，二者不能混用；页面未显示服务器绝对路径。
- [ ] coverage=complete，诊断列表为空；不把 complete 解读为覆盖任意 Python 动态行为。
- [ ] 中文解释没有“DeepSeek 调用成功”或“模型已验证”标记，也没有将 Indirect 写成确定运行失败。本次 rule 不需要 Key；confidence=1.0 不能证明模型成功。

### E. 异常、状态与恢复清单

| 用例 | 如何执行 | API 预期 | 前端验收点 |
| --- | --- | --- | --- |
| 非 ZIP / 空 ZIP | 选择 not-a-zip.txt 或 empty.zip；若文件选择器拦截 txt，由成员在浏览器测试请求中提交该内容 | 400 invalid_zip / 422 no_python_files | 显示可理解错误，不沿用之前函数与分析报告，不进入分析流程 |
| 参数重复 | 正常 Demo 选择新增 name=date 后 Validate | 422、validation.valid=false、invalid_after_signature | 显示 validation.diagnostics；能改回 timezone 重新校验成功 |
| 类型 / 插入点非法 | 在成员受控请求回放中使用 bad kind 或不存在的 insert_before | 422 unsupported_parameter_kind / insert_before_not_found | 不只读取 error.message；不存在的 UI 选项不要求新增控件 |
| Partial | 上传 partial.zip，按同一目标和配置走三步 | 200、partial；broken.py 存在 syntax_error；三类影响仍各 1 | 明显标记覆盖不完整、显示 broken.py 和原因，保留有效结果 |
| Partial 且零影响 | 上传 partial_no_impact.zip | 200、partial；Direct / 1-hop / 2-hop 均为 0 | 明确“仅覆盖已解析代码”，不能显示“项目安全 / 确定没有影响” |
| 指纹不一致 | 先 inspect 标准 ZIP 得 F，在浏览器受控请求中改为 changed_project.zip，仍传旧 F | validate / analyze 为 409 fingerprint_mismatch | 提示重新 inspect；不自动省略 fingerprint 绕过错误；更换文件时主动清除旧状态 |
| 正常更换项目 | 页面切换为 changed_project.zip 并重新 inspect | 新指纹 F2；重新 validate / analyze 后三类影响仍各 1 | 不串用旧 F、Symbol、校验结果；F2 与 F 不同 |
| Evidence / Explanation unavailable | 成员使用后端受控故障注入测试生成的响应，回放到页面测试状态 | 静态结果仍有效；证据 unavailable 或解释 null 并附诊断 | 不空白、不崩溃，不把缺失证据当作零影响；保持对应关系 |
| Provider 异常回退 | 执行已有 Provider 故障注入测试，前端检查默认规则页面与可回放响应 | HTTP 200、规则回退，影响和证据不变 | 来源不确定时显示“中文解释”，不能因 200 / confidence / 非空解释写成 DeepSeek 成功 |
| 重复提交 / 返回顺序 | 正常流程重复，或延迟旧请求后更换 ZIP / 参数再提交 | 同输入报告一致；独立输入结果各自对应 | 加载状态可恢复；旧请求晚返时不覆盖当前所选项目和参数的结果 |
| 服务或网络失败 | 成员受控测试响应 500/503，或临时停止本地后端再操作 | 安全 error JSON；网络失败无可读 JSON | 显示重试 / 服务不可用；不伪造空报告、成功状态或 DeepSeek 状态 |
| 未捕获异常后的恢复 | 受控注入内部异常后，重新发起 health 和正常请求；分别记录原连接与新连接结果 | 500 internal_error；新连接 health 应为 200；原连接可能被关闭 | 区分业务错误响应与连接中断，恢复按钮可用；不能将连接中断当作零影响，也不自动把失败分析标成成功 |

证据不可用和 Provider 回退没有通过公共请求参数触发的开关。不能靠一个 ZIP 保证触发，也不能新增测试 API；在受控故障注入或页面响应回放中验证，并将记录明确标为“故障注入 / 回放”。这些通过记录不能替代正常流程的真实浏览器 HTTP 验收，也不能当作真实 DeepSeek 调用。

浏览器指纹故障请求可由前端成员利用已确认的 base URL / 代理和测试 File，通过上文 formFor / postForm 的同样形式回放：File=changed_project.zip，expected_fingerprint=F。正常页面主动清除旧状态属于正确行为，不要求负责人为了看到 409 修改生产 UI。

### F. 三人整合与验收记录

| 交付人 | 验收前提供 | 负责人核对 |
| --- | --- | --- |
| 后端负责人 | 本文、冻结契约、测试结果、启动配置、标准 Demo 来源 | 版本、rule 模式、接口字段、诊断和路径安全 |
| 前端成员 | 仓库 / 分支或交付包、安装启动命令、实际 Origin、API base URL 变量名、代理配置、空值/错误/partial 状态展示说明 | 真浏览器完整链路，配置可复现，无硬编码未知部署地址 |
| Evaluation 成员 | 评测代码/版本、样本与指纹、结构化 Change、人工真值、计数单位、结果及复现命令 | 基线 Demo 一致；区分 call-site Direct 与 symbol-level Indirect；不将中文解释评分当作静态准确率 |

Evaluation 样本超出现有静态支持范围时，应记录 unsupported / unresolved / manual review，不要求本轮扩充 Core。评测产物无需新增 HTTP 入口；由成员交付并与固定版本的报告对照。不要把未收到的评测结论或前端页面写成已验收。

负责人复制并填写下表，截图 / 原始 JSON / Console 记录绑定当前运行、输入指纹和版本；只保存已确认无凭据的 Demo 验收材料。

| 用例 | 状态（待执行 / 通过 / 失败 / 阻塞） | 版本与 ZIP 指纹 | 浏览器操作及 HTTP 状态 / 可见结果 | 截图或 JSON 位置 | 问题 / 责任人 / 复验日期 |
| --- | --- | --- | --- | --- | --- |
| 接入、health、三步正常流程 | 待执行 | 待填写 | 待填写 | 待填写 | 待填写 |
| 统计、Evidence、Explanation | 待执行 | 待填写 | 待填写 | 待填写 | 待填写 |
| Partial、零影响 Partial | 待执行 | 待填写 | 待填写 | 待填写 | 待填写 |
| 指纹不符、更换文件、重复/晚返请求 | 待执行 | 待填写 | 待填写 | 待填写 | 待填写 |
| 不可用证据、Provider 回退、服务故障（注入/回放） | 待执行 | 待填写 | 待填写 | 待填写 | 待填写 |
| Evaluation 交付与基线对照 | 待执行 | 待填写 | 待填写 | 待填写 | 待填写 |

- [ ] 正常浏览器链路和关键异常项完成，失败项已经修复并复验；接入条件没有仍标为阻塞。
- [ ] 三人成果版本、实际环境、样本、JSON 和页面展示可对照，没有用旧报告证明新版本通过。
- [ ] 任一已实施页面控件不依赖后端未提供的字段；模型成功状态、项目持久化等缺失能力没有伪造展示。
- [ ] 负责人给出“通过 / 有条件通过 / 未通过”，写明延期项，故障回放的边界和未验证事项；签名、日期与三名成员复验责任明确。

### G. Web MVP 准备核查记录（历史）

上轮（2026-10-02）完整 pytest 为 241 passed、1 skipped、7 subtests passed。相关证据来自 `tests/test_frontend_readiness.py` 的请求/错误/关联检查、`tests/test_backend_contract.py` 的指纹与响应样例检查、`tests/test_backend_stability.py` 的真实 HTTP 流程、partial、清理及 Event 响应性测试。Provider 回退与 Evidence 不可用由受控测试验证，没有把 Mock 当作真实模型调用。

Web MVP 准备核查（2026-10-03）运行这三个相关测试文件，实际为 **42 passed、1 failed、1 条现有第三方弃用警告**。失败用例是 `test_real_http_unexpected_index_exception_uses_safe_json_and_cleans_up[/api/v1/projects/inspect]`：故障请求的安全 500 响应与清理断言已通过，随后立即复用同一 HTTP 客户端连接请求 health 时发生 ReadError（Windows 10053）。单独复验该用例为 **1 passed**；不能用单项复验替代整组失败记录。该次准备核查未重新运行完整 pytest；后续定位与完整回归见 I 节。

另外执行了本节样本生成命令与真实本地 HTTP 核查，后端显式为 rule，禁止外部模型请求：

| 实测项目 | 结果 |
| --- | --- |
| 标准 ZIP 三步 | inspect / validate / analyze 均为 200；4 个 Symbol；inspect / validate 指纹一致；报告 change 与校验结果一致 |
| 标准分析 | Direct=1、1-hop=1、2-hop=1、complete；3 组 Evidence / Explanation 内容一一对应 |
| partial.zip | analyze 为 200、partial；三类影响各 1 |
| partial_no_impact.zip | analyze 为 200、partial；三类影响各 0，仍须提示范围不完整 |
| 更换 ZIP 沿用旧指纹 | validate / analyze 均为 409 fingerprint_mismatch |
| empty.zip / not-a-zip.txt | inspect 分别为 422 no_python_files / 400 invalid_zip |
| 未捕获异常注入 | 安全 500 internal_error；同一连接紧接着 health 再次出现 ReadError；新 HTTP 客户端 health 为 200 |
| 临时目录 | 本次创建的 6 个临时目录全部清理；实际 DeepSeek 请求为 0 |

当时已核对安装的 Starlette / Uvicorn 源码：全局异常处理返回响应后，异常继续抛给服务器；响应已开始时 Uvicorn 关闭连接。这与上述连接复用现象相符。该次准备核查保留问题，未修改 API 或测试；后续专项核查已确认连接生命周期并修订测试，见 I 节。

该次准备核查只补充本文，不修改 API 契约、Core、React 或测试算法，不调用外部模型。浏览器、前端配置与 Evaluation 成果仍需成员按本节执行并填入记录。

### H. 接口边界与待协调问题

| 已确认边界 / 问题 | 本次验收处理 | 协调人 |
| --- | --- | --- |
| Analyze 没有 project_fingerprint 响应字段 | 用原始 ZIP、请求 expected_fingerprint、inspect / validate 指纹和 ChangeSpec 一致性核对，不新增或猜测返回字段 | 负责人、前端成员 |
| Explanation 无 provider_used / fallback_reason 等来源字段 | 本次只验收 rule；页面显示“中文解释”，不凭配置、200 或 confidence 宣称 DeepSeek 成功；真实模型认证仍在外部服务阻塞状态 | 负责人、前端成员 |
| 三类错误响应结构 | 分别处理 error 对象、validation.valid=false 和 FastAPI detail 数组；网络失败另行展示 | 前端成员 |
| 不同阶段 coverage 范围不同 | inspect / validate 是解析和索引范围，analyze 还包含 unresolved call；不能强制三个阶段 coverage 总是相等 | 前端成员、Evaluation 成员 |
| 未捕获 500 后原连接关闭 | 专项核查已确认是当前框架行为；测试改用新连接验证恢复，原始失败记录保留。无需强行保持连接或改 API，详见 I 节 | 负责人、前端成员 |
| React / Evaluation 尚未交付可核验工程 | 提供实际版本与启动/复现方式后再执行浏览器、评测整合清单；当前待执行状态保持真实 | 两名成员、负责人 |
| 实际 React Origin 未确认，CORS 未开放 | 成员确认完整 Origin 与代理方案，后续经负责人确认才配置明确白名单；不设置通配 Origin | 前端成员、负责人 |

### I. Phase 4.1 补充核查：HTTP 500 后连接生命周期

2026-10-03 专项定位使用当前本地依赖：FastAPI 0.142.2、Starlette 1.7.0、Uvicorn 0.54.0、HTTPX 0.28.1。全局 Exception handler 返回安全 JSON 后，Starlette `ServerErrorMiddleware` 仍会抛出原异常；Uvicorn h11 的 `run_asgi()` 在响应已经开始时关闭 transport。因此连接池立即复用尚未识别为关闭的连接可能出现 ReadError，服务进程仍可正常处理新连接。未发现本次现象需要修改 OpenImpact 生产异常处理逻辑的证据。

仅修订 `tests/test_backend_stability.py`，并更新本文记录：

- 原三个异常用例继续验证 500、application/json、安全错误字段、Content-Length 完整性与清理；随后显式创建新 HTTP 客户端，验证 health=200 和同一路由正常请求成功。保留测试并注释框架关闭连接的原因，不重试失败请求。
- 新增原始 TCP 用例，先在同一 socket 上完成 keep-alive health，再注入异常请求；完整读取 500 JSON 后，验证收到 EOF 或操作系统报告连接复位。超时、额外响应字节或响应体截断均会使测试失败。新连接健康检查及后续成功请求继续验证恢复与清理。
- 专项 HTTP 测试实际为 **5 passed、29 deselected**；其中包含真实三步流程。完整 pytest 为 **242 passed、1 skipped、7 subtests passed**，另有一条现有第三方弃用警告。

另在独立后端子进程完成真实 HTTP 核查：500 为 application/json，响应体完整 **87 字节**，error.code=internal_error；原 TCP 连接随后收到 **EOF**，后端进程及服务线程继续运行。新连接 health=200，Inspect → Validate → Analyze 均为 200；同一 ZIP 指纹校验正常，Direct / 1-hop / 2-hop 各为 1、coverage=complete，三组证据与解释对应；包括失败请求在内的 **4 个临时目录全部清理**。使用 rule 并阻止外部模型请求，没有真实 DeepSeek 调用。

上述关闭行为针对进入全局异常处理器的未捕获异常；路由自行捕获并返回的 analysis_failed 等 500 不必具有相同连接行为。前端应按已有契约展示错误或网络失败，允许用户重新发起操作，不依赖同一 TCP 连接永久存在，也不以无条件重试掩盖错误。本次连接生命周期问题已定位并通过回归；React Origin / 代理与成员交付版本仍待确认，实际浏览器验收继续按清单执行。


## V1.1 多领域页面接入

目标选择页支持 Function / Module。模块使用独立候选、草稿与报告，保留原 ZIP / fingerprint / revision / AbortController。Module Report 按 domain、kind、version 分发，不能按函数报告解释导入统计。详见 [模块变更契约及真实响应](module-changes.md)。

## V1.2 三领域接入

目标页增加“模块符号变更”。按实际 `module_inventory` 选择模块，再按 `symbol_inventory.symbols` 选择公开变量/常量。disabled 候选显示 reason，不隐藏支持边界。配置页支持重命名新名称，或删除分析确认；界面明确说明不修改上传文件。

Symbol 使用 `symbol_coverage` / `symbol_diagnostics`，其他领域继续使用原字段。草稿不能代替 Validate 的实际 Before / After 定义；Analyze 必须复用同一原始 ZIP、Inspect 指纹及当前已校验 payload。切换任一领域、目标、操作或字段都会取消旧请求并清除旧 Validate、Analyze、Report；旧响应按 revision 和 snapshot 丢弃。

报告根据 domain / report_kind / schema_version 分发。Symbol Direct 按真实引用位置计数，上游按模块去重；路径的终端符号引用独立于真实模块边。Evidence / Explanation 同序并核对 metadata，unavailable 明确显示，partial 提示保留。规则说明不标记为真实模型成功。详见 [Symbol 契约与响应样例](symbol-changes.md)。原始 ZIP 仍仅保留在当前会话，刷新后重新选择；本地 Vite `/api` 代理无需扩大后端 CORS。
## 报告工作台追加接入

报告底部增加推荐追问与自定义问题；右下角「项目源码」可浏览原 ZIP 内 Scanner 接受的 `.py` 文件，证据/回答引用可定位完整文件。两者共用当前原始 File、Inspect 指纹和 analysis_root，不改变既有 Workflow reducer、报告映射或 Evidence/Explanation 同序规则。

新增请求与返回见 [API 契约](api-contract.md#只读源码与报告追问追加入口)，使用边界和来源判断见 [报告工作台说明](report-workspace.md)。完整 API 地址集中在现有 Client；仍通过 Vite `/api` 代理。报告追问仅当前变更范围，模型失败明确回退；演示模式不发送真实模型请求。
