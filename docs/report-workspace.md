# 报告追问与项目源码阅读

这两个入口帮助学生核查当前变更报告。影响判断仍由静态分析完成，回答不会增减影响记录，也不会执行或修改上传源码。

## 网页使用

1. 上传 ZIP 并完成 Inspect。右下角的「项目源码」按钮即可打开 Python 文件目录。
2. 选择文件阅读完整源码，可查找文件、查找文件内文字；长文件每段显示 200 行，避免一次渲染大量行。目录保留项目相对路径。
3. 完成 Validate / Analyze 后，在报告底部点击「生成推荐追问」，由 DeepSeek 依据当前证据提出 2～3 个问题；点击问题获得回答，也可直接输入问题。
4. 回答围绕当前选中的影响记录、原始直接影响和代表性传播路径展开。点击回答中的文件引用或 Evidence 的「打开完整源码」，可定位真实文件和行号。
5. 切换影响记录、变更配置或项目后，旧对话失效。更换 ZIP 或源码根目录后，旧源码缓存清除。

源码面板只读；能打开文件不表示该文件已被完整分析。当前只列出 Scanner 接受的 `.py` 文件，不包含被忽略的虚拟环境或其他文件类型。刷新浏览器会丢失原始 ZIP、缓存和对话，需要重新上传。

手机端按目录、文件阅读区排列。原生对话框支持 Escape 关闭、键盘焦点约束和关闭后焦点恢复；行定位高亮遵循 `prefers-reduced-motion`。Windows 系统级 `native reduced-motion verification` 仍为 pending；浏览器模拟不能替代负责人补验。

## 回答范围与来源

推荐追问由模型根据当前变更、选中证据和代表性路径生成，围绕影响原因、检查顺序与分析边界。页面不再提供固定推荐问题。生成问题和回答分别在用户点击后调用一次模型，不随页面或影响项切换自动调用；模型不可用时不显示替代推荐。自定义问题只使用本次报告已有证据，首版不支持任意全项目知识问答。单纯在源码面板打开其他文件不会自动将其加入模型上下文。

- `rule`：无需模型，按已有证据和规则解释回答。
- `deepseek`：模型请求成功且返回值通过格式、引用校验后，显示「模型辅助回答」。
- `fallback`：认证、超时、缺少 Key、非法 JSON 或不合法引用等情况下，显示「规则回答 · 模型暂不可用」。HTTP 200 不能独自证明模型成功。
- `status=limited`：证据不足、无对应记录或问题超出范围，界面明确提示回答范围有限。

`OPENIMPACT_LLM_PROVIDER` 默认 `rule`，用于离线或测试；推荐追问在此模式明确不可用。正式模型体验需在后端启动前设置 `deepseek` 并提供有效 `DEEPSEEK_API_KEY`。Key 只由服务端读取。用户主动提交追问时，最多请求模型一次；仅发送相关证据片段、变更、覆盖范围、有限代表性路径及最近对话，不发送整份 ZIP。资料中的指令不能改变系统规则。

日常仍从固定的 `Nexus-OpenImpact` 主目录启动，不需要跟随开发工作树切换。PowerShell 可在后端终端安全设置：

```powershell
$env:OPENIMPACT_LLM_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new("", (Read-Host "输入 DeepSeek Key（隐藏输入）" -AsSecureString)).Password
.\.local\python-env\Scripts\python.exe -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

变量只属于这个终端及其子进程，不要把 Key 填入聊天、源码或前端环境。已运行的后端需要停止后重新启动才能读取新配置。前端继续在主目录的 `frontend` 中执行 `npm run dev`。

模型输出校验能拒绝不存在的引用编号，不能证明自然语言的所有推理均正确。涉及参数值来源、业务职责和修改方案仍需人工判断。Indirect 表示上游需要检查，不证明必然运行失败；partial 下零结果不证明项目没有其他影响。

## 请求生命周期

每次请求重新提交浏览器保存的同一原始 ZIP 和 Inspect 指纹，后端复用现有安全导入与临时目录清理流程。追问在该请求快照上重建可信报告，不接受客户端提交的分析结论。完整报告生成使用规则解释，避免为每个 Finding 额外调用模型。

客户端按项目与配置身份取消旧请求、丢弃迟到响应。取消浏览器请求不保证已开始的服务端模型计算也会停止；因此按钮在请求中禁用，历史和输入有长度限制。没有服务端项目持久化、对话数据库或流式输出。

重新上传、扫描会产生额外开销，模型还会增加延迟与费用；V1 沿用有界上传和线程池，不引入后台 Worker。多用户公开部署仍需要容量与访问控制评估。

## 本轮验收记录

基线为 `460dc94`，本轮使用独立开发工作树的 rule 后端与 Vite 代理验收。

| 检查 | 实际结果 |
| --- | --- |
| 新入口专项测试 | 32 passed：安全 ZIP、路径、编码、指纹、错误、临时清理、并发、健康响应性、模型输出校验与回退 |
| 完整 Backend | 916 passed、2 skipped、7 subtests passed；已有 Starlette TestClient 弃用警告 1 条 |
| Frontend | 205 passed；生产 Build 成功 |
| 既有 CLI Demo | 15 份 JSON 报告含解释字段均与基线逐字段相同 |
| 函数真实浏览器 | format_date + timezone = 1/1/1 complete；page + zone = 0/0/0 complete；切换后无旧答案与证据 |
| 模块 / 符号真实浏览器 | rename_module 与 rename_module_symbol 均 1/1/1 complete；追问分别引用 report.py:1 与 client.py:3 |
| 源码阅读 | 嵌套目录、完整文件、第 5 行定位、300 行文件跨段查找第 270 行、SyntaxError 文件、Escape 关闭和焦点恢复通过 |
| 响应式 | 1440 / 768 / 390px 未见页面横向溢出；手机保留 partial 提示 |
| 实际模型请求 | 仅发送一次，当前进程认证返回 HTTP 401，provider=fallback、fallback_reason=http_401；未宣称模型成功，也未继续重试 |

独立 Benchmark 与系统级 reduced-motion 补验继续 pending。本轮功能测试不代表准确率评价；模型认证由有效本地配置处理，不要求在聊天中提供 Key。

## 模型推荐追问验收（2026-10-05）

- 追加推荐入口复用可信报告、ZIP 防护、指纹和线程池；没有修改静态影响算法、Workflow reducer、Evidence 匹配或既有报告字段。
- 专项 53 passed；完整后端 937 passed、2 skipped、7 subtests passed。Windows 运行完整套件时设置 `PYTHONUTF8=1`，避免旧 CLI 子进程的 UTF-8 输出由父进程按 GBK 解码；未修改旧断言。
- 前端 207 passed，生产构建成功。
- 真实本地浏览器完成同一 ZIP 的新增参数 1/1/1 complete、page + zone 0/0/0 complete；改配置、选中影响项或换 ZIP 后旧推荐与回答清除。手机端 390px 无横向溢出，partial 提示保留，未发现控制台错误。
- 生成问题、点击回答、引用定位和 401 降级使用真实 HTTP 与受控模型传输验证；测试替身仅在忽略的本地辅助文件中，不属于正式应用。未把此结果描述为真实 DeepSeek 调用成功。本轮未调用外部模型或重新认证。
- 非法 JSON、数量、长度、重复问题、伪造引用、无 Key、离线模式、422/409、ZIP 限制、内部异常和临时清理均有专项测试。模型推荐失败返回空列表，不填充固定问题。

模型只能解释和提出检查问题。引用和格式验证不能保证自然语言推理正确，问题本身也不构成新的静态判定。native reduced-motion verification 与 independent Benchmark 继续 pending。
