# OpenImpact 前端交接：后端接口冻结范围

截至 2026-10-01，三个正式业务接口为 `POST /api/v1/projects/inspect`、`POST /api/v1/changes/validate`、`POST /api/v1/projects/analyze`。字段、状态码与大小限制以 [API 契约](api-contract.md) 为准。后端 Core 报告版本为 `schema_version=1`；本轮没有重命名公开 JSON 字段。

## 页面工作流

1. 用户选一个 Python 项目 ZIP。前端保存当前 `File` 对象，调用 inspect，从 `symbols[]` 展示可选目标。每个目标使用完整 `symbol_id`，例如 `utils.format_date`；不要只传函数短名。
2. 用户填写新增必填参数的 `name` 与 `kind`。前端把简化配置序列化成 JSON 字符串，连同**同一 ZIP 文件**和 inspect 返回的 `project_fingerprint` 调用 validate。有效时可展示 `change_spec.before`、`after` 及 `validation.valid=true`。
3. 用户确认配置后，重复上传同一 ZIP 与同一配置到 analyze，并传相同的 `expected_fingerprint`。展示 `summary`、Direct 调用点、1-hop / 2-hop 上游路径、人工检查项及诊断。

V1 不保存上传项目，不返回项目 ID。刷新页面或更换 ZIP 后，需要重新 inspect；前端应清除旧指纹、Symbol 选择和 ChangeSpec。指纹来自 ZIP **原始字节**，同样的源码重新打包也可能得到新指纹。三步上传均使用 `multipart/form-data`；让浏览器为 `FormData` 自动设置带 boundary 的 `Content-Type`，不要手动设置该请求头。

```ts
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

const inspected = await fetch("/api/v1/projects/inspect", {
  method: "POST", body: formFor(file),
});
const inspectBody = await inspected.json();
const fingerprint = inspectBody.project_fingerprint;

const validated = await fetch("/api/v1/changes/validate", {
  method: "POST", body: formFor(file, change, fingerprint),
});
const validateBody = await validated.json();

const analyzed = await fetch("/api/v1/projects/analyze", {
  method: "POST", body: formFor(file, change, fingerprint),
});
const report = await analyzed.json();
```

实际页面应在每步检查 `response.ok` 与响应形状后再进入下一步。validate 的 `validation.valid=false`、`fingerprint_mismatch`、ZIP 错误及框架缺字段错误分别处理。

## 展示语义

| 字段 | 前端呈现建议 |
| --- | --- |
| `coverage.status` | `partial` 时显著显示 `coverage.message`（analyze）及诊断；零个 Finding 不能表述为全项目无影响 |
| `direct_impacts[]` | 展示相对 `file`、行/列、caller、target、规则与原因；代表本次 Change 确定造成调用不兼容 |
| `indirect_impacts[]` | 展示 `impacted_symbol_id`、距离、`sources[].propagation_path`；语义为上游路径需要检查 |
| `evidences[]` | 按 `evidence_reference` 关联 Direct 证据；显示项目相对位置、源码片段、完整文件 SHA-256 与 Indirect 传播路径。`status=unavailable` 时显示该项 `diagnostics[]`，保留原影响结论 |
| `explanations[]` | 与 `evidences[]` 同序；显示 `explanation` 中的中文说明。若为 `null`，显示该项 `diagnostics[]`，继续展示 Evidence 与原影响结论 |
| `manual_reviews[]` | 独立于确定 Direct 计数展示 |
| `pre_existing_problems[]` | 标记为修改前已有问题 |
| `diagnostics` | 解析错误、未解析 import / 调用独立展示；文件路径已是项目相对路径 |

`added_parameter.kind` 当前只接受 `positional_only`、`positional_or_keyword`、`keyword_only`。默认插在同类型参数组末尾。必要时传 `insert_before`，值必须是目标函数已有参数名；最终合法性以 Core Validator 的 `validation.diagnostics` 为准。前端无需自行拼装完整 ChangeSpec，也无需执行 Python 参数规则。

## 错误处理

- `409 fingerprint_mismatch`：当前 ZIP 与 inspect 时不同；提示用户重新 inspect。
- `422` 且有 `validation.valid=false`：显示 `validation.diagnostics[]`。此时 analyze 未执行影响分析。
- `400/413/415/422` 且有 `error`：显示 `error.message`；常见原因是 ZIP 损坏、不安全条目、超限或没有可分析 `.py`。
- 框架级 `400/422` 且有 `detail`：检查 multipart 字段缺失或格式错误。
- `500 analysis_failed` 或 `503 inspection_unavailable`：显示可重试提示；响应不包含内部堆栈或临时路径。

## 实际响应样例

以下文件由 FastAPI HTTP 测试客户端的实际响应生成，使用仓库公开的 `examples/signature_change/` 构造固定内容 ZIP。样例已省去 HTTP 头，JSON 字段保持接口原样；上传项目报告中的 `project_path` 为相对根目录 `.`，不含服务器临时路径。

| 操作 | 响应样例 |
| --- | --- |
| Inspect，HTTP 200 | [inspect-response.json](api-samples/inspect-response.json) |
| Validate，HTTP 200 | [validate-response.json](api-samples/validate-response.json) |
| Analyze，HTTP 200 | [analyze-response.json](api-samples/analyze-response.json) |
| 修改 ZIP 后沿用旧指纹，HTTP 409 | [error-response.json](api-samples/error-response.json) |

本样例 ZIP 的 SHA-256 为 `9ab9885be3f7e7f5285a6e976ed02dc57e25bac055d0ecaa8701fca94f276d9e`。它只用于核对这四份响应，前端运行时应使用当前 inspect 的实际指纹。
