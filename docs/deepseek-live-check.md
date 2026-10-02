# DeepSeek 真实 API 联调

## 本轮结果（2026-10-02，Asia/Shanghai）

当前进程与 Windows 用户环境都存在 `DEEPSEEK_API_KEY`，二者一致。真实请求发送到 `https://api.deepseek.com/chat/completions`，请求模型为 `deepseek-flash`。服务端返回 HTTP 401，未通过认证；实际执行的模型版本和真实模型 ExplanationResult 均未获得。本轮不能宣称真实模型联调或解释质量通过。

先执行了一次短 Direct Evidence 请求，确认 401；随后在同一固定 Demo ZIP 上，通过真实回环 HTTP 完成两种模式的 inspect → validate → analyze。

| 项目 | rule 模式 | deepseek 模式 |
| --- | --- | --- |
| 三个业务 HTTP 请求 | 均为 200 | 均为 200 |
| Direct / 1-hop / 2-hop | 1 / 1 / 1 | 1 / 1 / 1 |
| Coverage | complete | complete |
| Explanation 来源 | 规则模板 | 三次外部请求均为 HTTP 401，随后规则回退 |
| 临时目录 | 请求后清理 | 请求后清理 |

Direct、Indirect、Evidence、Coverage、非模型 Diagnostics、Summary、ChangeSpec 和 Validation 均完全相同。DeepSeek 模式最终返回 200 说明分析与回退可用，不能证明模型成功。认证失败原因由当前服务端响应确定为 401；Key 是否失效、填错或用于其他服务，需在本机和 DeepSeek 控制台核对。

## 可重复执行

脚本仅使用公开的 `examples/signature_change/*.py`，最多调用 DeepSeek 三次，对应 Direct、1-hop、2-hop Evidence；不重试。它启动仅绑定 `127.0.0.1` 的临时 Uvicorn 服务，通过真实 HTTP 上传同一 ZIP，使用实际现有 API 完成两种模式的完整链路。DeepSeek 请求未被 Mock。

在仓库目录已安装 `pip install -e ".[test]"` 的虚拟环境中：

```powershell
.\.venv\Scripts\python.exe scripts/deepseek_live_check.py
```

需要替换当前未通过认证的 Key 时，在本地终端使用隐藏输入，不在命令参数、源码或聊天中填写 Key：

```powershell
.\.venv\Scripts\python.exe scripts/deepseek_live_check.py --prompt-key
```

Key 只保存在该进程的环境变量中，脚本不保存它。结果默认写入 Git 忽略的 `.local/deepseek-live-check/result.json`，仅包含公开 Demo 报告、经过校验的 ExplanationResult 和安全调用诊断。写入前还会替换意外出现的 Key 字符串；不保存原始错误体或认证请求头。

退出码 `0` 表示三次模型输出均通过结构校验、静态结果一致、目录清理成功且自动筛查未发现问题，**仍需人工阅读中文解释**。退出码 `1` 表示模型回退或结果存在待核查项；退出码 `2` 表示联调脚本未完成。没有 Key 时仍可验证全链路及 `missing_key` 回退，不能当作真实模型成功。

## 调用成功与回退的区分

`DeepSeekProvider.last_call` 为本地诊断信息，未加入 API JSON 字段。每次调用重置，记录：

- `status=model_success`：返回内容为合法 JSON，字段完整，通过 ExplanationResult 校验，风险等级符合证据限制。
- `status=fallback`：`reason_code` 给出安全原因，例如 `missing_key`、`http_401`、`request_timeout`、`invalid_json`、`invalid_output_fields`、`unsupported_risk_level`、`incomplete_response`。
- 请求模型、服务端返回模型、HTTP 状态和可用 Token 计数。诊断不包含 Key、原始异常文本或服务器堆栈。

官方当前列出 `deepseek-flash`，支持 JSON Output；请求显式关闭思考模式，限制输出为 1024 Token，默认请求超时 20 秒。参考：[模型说明](https://api-docs.deepseek.com/quick_start/pricing/)、[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)、[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 解释质量审核

只有 `model_success` 项才用于评审真实模型解释。逐项对照输入 Evidence 和规则模板：

1. 文件、行号、函数名和调用路径均能在对应 Evidence 中找到。
2. Direct 说明已有规则确定的兼容性变化；Indirect 只建议检查上游路径。
3. `risk_level` 保持 `unknown`，`confidence` 表示解释对证据的忠实程度。
4. `suggested_check` 只提出检查事项，不编写补丁或给出无证据支持的具体修改方案。
5. 中文表述清楚，引用已有规则和原因，不编造运行结果或测试结果。

脚本会对明显的未知文件、行号、函数引用、风险升级、具体修改措辞及 Indirect 确定失败表述产生 `quality_flags`。这是针对固定 Demo 的辅助筛查，无法证明自然语言语义完全忠实，也可能产生误报。当前所有外部请求认证失败，因此真实模型质量、Token 用量和延迟尚未验收。
