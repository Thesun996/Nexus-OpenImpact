# Phase 3.4 后端稳定性验收

日期：2026-10-02（Asia/Shanghai）。本轮统一使用 `OPENIMPACT_LLM_PROVIDER=rule`，没有发送真实 DeepSeek 请求，也没有修改 Core 分析算法。

## 验收方式

`tests/test_backend_stability.py` 启动仅监听 `127.0.0.1` 的临时 Uvicorn 服务，使用 `httpx.Client` 通过 TCP 提交 multipart 请求。业务流程没有使用 FastAPI TestClient。故障场景仅注入本地异常，外部模型请求被禁止并检查调用次数为零。测试退出后关闭服务、检查线程退出及所有上传临时目录清理。

复现命令（已安装测试依赖的项目虚拟环境）：

```powershell
$env:OPENIMPACT_LLM_PROVIDER = "rule"
.\.venv\Scripts\python.exe -m pytest tests/test_backend_stability.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

初次验收结果：新增真实 HTTP 稳定性测试 **27 passed**；完整回归 **229 passed、1 skipped、7 subtests passed**，耗时 17.78 秒。后续事件循环隔离修订见下文。另有一条现有 Starlette TestClient / httpx 弃用警告。未自动 Git commit。

## 完整 HTTP 流程

使用公开 `examples/signature_change/*.py` 构造同一份 ZIP，依次执行：

| 操作 | 结果 |
| --- | --- |
| Inspect | HTTP 200；返回 `utils.format_date`；指纹与 ZIP 的 SHA-256 一致 |
| Validate | HTTP 200；自动读取源码签名，校验成功，指纹与 inspect 一致 |
| Analyze | HTTP 200；ChangeSpec 与 validate 完全相同 |
| 影响结果 | Direct = 1、1-hop = 1、2-hop = 1、coverage = complete |
| Evidence | 3 项；实际源码片段、完整文件 SHA-256、调用位置和传播路径正确 |
| Explanation | 3 项规则解释；与 Evidence 同序、一一对应，风险等级为 unknown |
| 重复提交 | 完整三步工作流执行 3 次，响应完全一致，9 个独立临时目录均清理 |

路径证据为 `page.page → dashboard.dashboard → report.report → utils.format_date`，末端位置及引用关联原始 Direct Evidence。HTTP 上传报告与 Demo 报告的 `project_path` 均为 `.`；CLI 继续保留本地路径。

## 异常与恢复

| 场景 | 实际 HTTP 结果与处理 |
| --- | --- |
| 非 ZIP 内容 | 三个业务接口均为 400 / invalid_zip；不创建解压目录 |
| 空 ZIP | 三个接口均为 422 / no_python_files；不创建解压目录 |
| 额外文件 SyntaxError | 三个接口均为 200、partial；保留相对路径诊断；analyze 明确说明覆盖不完整 |
| Change JSON 损坏 | validate / analyze 为 422、validation.valid=false |
| 目标不存在、参数重名、参数类型错误 | validate / analyze 为 422，提供对应诊断 |
| 默认参数后新增必填位置参数导致非法签名 | validate / analyze 为 422 / invalid_after_signature |
| 修改 ZIP 后使用旧指纹 | validate / analyze 为 409 / fingerprint_mismatch；拒绝后不创建解压目录 |
| 缺少必填表单字段 | 保留框架 422 / detail 响应 |
| Direct EvidenceBuilder 异常 | HTTP 200；该证据 unavailable、解释 null；其他证据、解释及静态结论保留；后续正常请求恢复 |
| Explanation Provider 异常 | HTTP 200，规则回退；响应与默认规则报告一致，后续请求不受影响 |
| 解压阶段 OSError | 三个接口均为 503 / inspection_unavailable；临时目录清理，后续请求恢复 |
| 索引阶段未预期异常 | 三个接口均为安全 JSON 500 / internal_error；临时目录清理，健康接口及后续正常请求可用 |
| 影响分析内部异常 | 500 / analysis_failed；临时目录清理，后续正常请求恢复 |

异常消息注入了测试用敏感标记、服务器路径及堆栈标记，验证这些内容没有进入客户端响应。报告的文件位置均为项目相对路径，失败不会向客户端返回异常原文。

## 并发与状态检查

- 六个客户端通过 Barrier 同时开始，各自提交不同 ZIP 的完整三步流程。各项目使用相同 Symbol ID，但原始参数名和调用源码不同，验证六个指纹、before 签名、源码片段、哈希及中文解释分别匹配各自项目。
- 18 次上传分别使用 18 个不同临时目录，全部清理；解释阶段创建 18 个独立 RuleBasedProvider 实例，没有复用带状态的 Provider。
- 另有四个客户端同时提交成功分析、无效 ZIP、指纹不符、无效 Change JSON，分别得到 200、400、409、422，随后正常分析响应保持一致。
- Core 的 SymbolIndex、CallGraph、兼容性评估和传播结果均在请求内新建；没有发现存储用户项目结果的模块级可变缓存。rule Provider 无可变请求状态。DeepSeek 状态字段属于实例，本轮不评估其真实服务行为。

本轮未发现项目数据或 Provider 状态串线。

## 必要修复与契约

首次真实 HTTP 验收发现两项问题并复现失败测试：索引阶段未预期异常返回纯文本 500；固定 Demo 报告暴露服务器绝对项目路径。

最小修复仅位于 HTTP 层：增加通用安全 JSON 异常处理，使用 `error.code=internal_error` 和固定消息；将 Demo 的 `project_path` 规范为 `.`。既有 API 路径、字段名、schema_version 和分析结论均保留。原有专用错误码、422 validation 与框架 detail 结构继续保留。详见 [API 契约](api-contract.md)。

## 当前限制

- 这次验证覆盖有限数量的并发客户端，不能代替压力测试、长期运行或多进程部署验收。
- 四个业务接口的同步工作已移入 Starlette 的受限线程池；线程池与同步依赖、文件上传及同步 health 路由共享容量，全部槽位忙碌时仍可能排队。线程隔离不能保证 CPU 密集工作吞吐，也不能消除 GIL 与资源竞争；本轮不作压力测试。
- ZIP 有上传、文件数和解压限额；当前没有单次 AST/分析 CPU 时间预算、进程隔离或总体并发内存预算。没有在本轮引入 Worker 或架构重构。
- Evidence 不可用时不会改变静态 coverage；应同时查看 `evidences[].status/diagnostics` 与 `explanations[].diagnostics`。
- 上传目录只在请求内保留。无法将 fingerprint 当作持久项目 ID，也不保证从客户端断连开始立即取消同步分析。
- DeepSeek 真实认证仍因 HTTP 401 阻塞；本轮使用规则解释，不能推断外部模型质量已通过验收。

## 补充修订：同步分析与事件循环隔离

检查确认 inspect、validate、analyze、demo/analyze 四个 `async def` 路由原先直接调用同步扫描、解析、索引、分析与报告。修复前的真实 HTTP 测试复现：通过 `threading.Event` 暂停分析时，`GET /api/v1/health` 无法返回并超时。

最小修复保留异步表单检查和文件读取，将每个请求的同步业务段放入一个同步辅助函数，通过 `await run_in_threadpool(...)` 执行。ZIP 指纹检查、导入、ChangeSpec 校验、分析、Evidence、Explanation、JSON 序列化及临时目录清理都在同一次工作线程调用中完成。同一个 analyze 的校验与分析使用原有同一临时目录；目录在工作函数成功或异常退出后清理，UploadFile 继续由异步路由的 finally 关闭。

没有手动创建生产线程或修改线程容量。已核对本机安装的 Starlette / AnyIO 实现：`run_in_threadpool` 委托 `anyio.to_thread.run_sync`，默认共享 CapacityLimiter 为 40；等待工作线程默认不采用 abandon-on-cancel，工作函数继续负责完成目录清理。参考：[Starlette 线程池](https://starlette.dev/threadpool/)、[AnyIO 线程与取消语义](https://anyio.readthedocs.io/en/stable/threads.html)。公开 API 路径、请求/响应字段、错误码及 Core 算法保持不变。

新增六项真实本地 HTTP 测试，使用 Event 控制阻塞和释放，超时仅用于检测死锁，没有固定 sleep 的响应时间断言：

- 分别暂停四个接口的同步索引阶段，健康检查均在 release 尚未设置、原请求尚未完成时返回 200。释放后请求成功，上传临时目录清理，分析摘要保持 1 / 1 / 1、complete。
- 暂停 slow 项目的影响分析，同时完成 fast 项目的完整三步流程；两个项目使用相同 Symbol ID、不同签名及调用片段，验证指纹和响应正确隔离。slow 请求的目录在阻塞期间保留，fast 的目录在各请求完成后清理。
- 分别验证 slow 请求最终成功及抛出内部分析异常；失败时保留安全的 500 / analysis_failed 响应，所有目录最终清理。

六项新增响应性测试全部通过，真实 HTTP 稳定性测试累计 33 项。此次完整回归为 **235 passed、1 skipped、7 subtests passed**，耗时 21.23 秒，另有一条现有第三方弃用警告；`git diff --check` 通过。本轮没有调用外部模型，没有引入 Worker、CPU 时间预算或进程隔离，未自动 Git commit。
