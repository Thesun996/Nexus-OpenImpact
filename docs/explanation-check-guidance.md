# 源码证据驱动的检查建议

## 目标与边界

让学生知道先打开哪个位置、随后检查哪些上游位置、哪些问题仍需结合业务确认。分析算法、八种 Change Type、三领域 API 路径、请求字段与报告版本保持不变。

解释保留 summary、why_affected、risk_level、suggested_check、confidence 五个字段。文本允许换行，不能当作稳定枚举或分析依据；Evidence 与 Explanation 仍按原契约对应。

## 函数签名解释

新增内部不可变 ExplanationContext，不加入公开报告 schema。输入来自同一次 AnalysisRun：既有 Direct 来源与一条最多三条边的代表路径，原始直接调用的 Before/After 兼容性原因和 canonical 结构化签名，完整 Symbol、相对文件、1 起始行号及 0 起始 UTF-8 列号。

使用既有安全读取器核对 AST 捕获的调用表达式与位置。仅复核成功才提供表达式和文件哈希，每个表达式向模型提供最多 800 字符。缺失或变化源码提示手动复核，不引用旧代码。多来源数量与 partial 也用于说明检查边界。无跨请求缓存。

以实际 signature_change 为例：

1. 先看 report.py:5:11 的 `format_date(date)`：修改后缺少 timezone。检查这层能否取得所需信息，还是需要由上游传入。
2. 再看 dashboard.py:5:11 的 `report("2026-10-01")`：核对这层是否需要配合调整接口或传参。
3. 再看 page.py:5:11 的 `dashboard()`：核对上游入口。
4. 人工确认现有测试覆盖这些位置后运行；当前没有测试文件或执行结果证据。

第 2、3 步是人工检查建议，没有判定上游参数不兼容。不判断 timezone 应取什么值，不从函数名猜业务职责。

四种操作的建议分别关注新增参数的信息来源、删除参数承载信息的去向、旧关键字名称与对原默认值的依赖。必填化提供已解析默认值的源码，明确未执行或求值。影响判定继续由原兼容性引擎完成。

## 模块与符号解释

使用已有 Import/Symbol Evidence、原始 Direct 来源与静态依赖路径：先核对原始断裂引用，再向上列出真实导入位置。

模块变更关注旧模块入口兼容安排与别名的现有使用点，不宣称找到全部使用点。符号变更关注原定义与读取位置的业务含义，不分析取值变化后果。上游只建议检查，不保证实际执行或运行失败。原始引用源码缺失或哈希不一致时提示手动核查。两个领域继续使用规则解释，没有增加模型调用路径。

## Provider 与降级

规则解释组织已有事实。DeepSeek 输入增加相同上下文和结构化签名，Prompt 要求事实与待确认问题分开，先直接位置后上游，不虚构参数值来源、分支、测试文件或业务严重程度。

上下文构建失败回到基本 Evidence 解释；Provider 异常或非法 JSON 继续规则回退。Evidence 不可用时对应解释为 null，保留影响结论；符号报告同样降级。

模型响应只校验结构与现有风险约束，不能保证每句自由文本都无幻觉，实际模型解释仍需人工复核。本轮使用规则真实 HTTP 与 Mock 模型测试，没有真实 DeepSeek 请求。

## 前端与验收

保留 Tracework 排版及证据优先级。ExplanationText 是纯展示组件：分段呈现换行文字，把连续编号检查步骤转为有序列表，边界提示独立成段。普通 React 文本转义，旧单段解释兼容。

依据已安装 frontend-design 指南落实具体内容优先、克制改动、可读层级；没有改写工作流、Motion、API Client、Context/reducer、ZIP、指纹或 Evidence 匹配。

专项测试覆盖四种操作、路径位置、UTF-8 列号、多行调用、多来源、partial、缺失/变化源码、上下文匹配、Provider 成功/失败及静态报告与源码不变。HTTP 样例仅更新实际接口产生的解释文字，保留完整冻结契约断言。15 个 Demo 的其余字段与改动前 main 基线逐字段比较。

没有进行学生学习收益评估或独立准确率评价。保留 native reduced-motion verification = pending、independent Benchmark = pending。

## 实际验证记录（2026-10-05）

- 解释专项：59 passed；Backend 全量：884 passed、2 skipped、7 subtests passed；有一个现存 Starlette TestClient 弃用提示。
- Frontend：201 passed，npm run check 与独立 npm run build 成功；git diff --check 通过。
- 同一工作树的 rule 后端真实 HTTP：Inspect / Validate / Analyze 均为 200，旧指纹请求返回 409；HTTP 样例的静态字段完全不变。
- 原 14 个 Demo 与 package_signature_change：15 份报告除 explanations 外逐字段与改动前 main 一致。
- 同一工作树 Vite 代理浏览器流程：format_date + timezone 为 1/1/1 complete；随后 page.page + zone 为 0/0/0 complete，旧证据和解释清空。模块重命名、符号重命名均为 1/1/1 complete，可查看原始断裂引用及上游检查顺序。
- 1280/1440 桌面与 390 手机检查：无页面横向溢出；1440 下源码区宽于解释区。控制台未出现错误。手机记录保留完整检查步骤与边界提示。
- partial、缺失/变化源码、模型失败回退通过自动化专项验证；没有将 Mock 结果称为真实 DeepSeek 质量验收。
