# 显式演示样例

fixtures/inspect.json、validate.json、analyze.json 来自前端分支审核期间对 main `f2c737bb81801c4823ae73efd040cfdedf9a9fe5` 的真实本地 HTTP 响应，使用 rule 模式。未调用外部模型。

请求上传文件为本目录工程 public/samples/signature_change.zip（原 frontend 样例），SHA-256：

`db0a82348a94853526f7d79a2f58926994596a3ab1b7c639e6474673d32be1b3`

三个接口依次为 `/api/v1/projects/inspect`、`/api/v1/changes/validate`、`/api/v1/projects/analyze`。后两个请求配置：

```json
{"target_symbol_id":"utils.format_date","added_parameter":{"name":"timezone","kind":"positional_or_keyword"}}
```

页面只在用户点击“打开演示项目”后读取这些保存响应，始终显示演示标识。校验和报告只允许以上固定配置；换目标、参数名、类型或 insert_before 会清空结果并明确拒绝样例替代。用户选择其他 ZIP 后清空演示状态。

演示模式不发送上述业务 HTTP 请求；样例 ZIP 从当前前端服务器读取并核对指纹。Step 2 的实际项目模式已接入后端，使用用户选择的原始 File 和 Inspect 实际返回的指纹，两个模式保持隔离。响应内路径均为项目相对路径，未保存密钥。
