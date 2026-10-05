# V1.2 Symbol & Structure 开发日志

## 2026-10-05 继续开发授权与本次复验

负责人明确批准在 `native reduced-motion verification = pending` 下继续Phase8，作为非阻塞视觉尾项保留。下方暂停记录是上一轮授权状态，现已由本次明确授权解除；没有将自动化模拟记为系统级PASS。

首先核对全部七个工作树：Phase8已经从完整V1.1 `bc19b6c`建立，HEAD与V1.1完全相同，旧成果未遗漏；无需同步或新建分支。原main及其余五个功能/集成工作树干净，完整Phase6.6三份文档和Phase7审计文档均在基线中；Phase8未提交成果完整保留，没有reset/clean或覆盖重做。

本次源码复审发现Symbol确定性边界遗漏，先建立失败回归再局部修复：定义时default/decorator中的NamedExpr、类作用域global写入、match mapping的rest绑定、Name/Attribute注解读取，以及明确builtins反射别名、不支持作用域属性写入和模块__dict__逃逸。只修改Symbol事实采集与三个Symbol测试文件，不改原Function/Module/CallGraph/Direct/Indirect算法。

首次新增10项边界测试中10项失败，修复后追加namespace写入4项；最终Symbol/AST专项111 passed。完整Backend793 passed、1 skipped、1 warning、7 subtests passed，44.77s；Frontend182 passed、Production Build通过。

重新启动当前工作树rule Backend8013与Vite5179。14个真实ZIP三步HTTP均200，旧十个CLI报告同V1.1逐字段相同；坏ZIP400、指纹409、目标422及跨文件动态写入降级通过，新残留解压目录0。真实浏览器重跑六个Function、两Module、Symbol Rename/Remove/零影响/partial，正例1/1/1、阴性0/0/0；422改正后恢复，409清除旧结果而保留原ZIP，Evidence读取OSError仍保留影响并降级证据/解释。快速三领域切换目标清空、配置按钮禁用，console errors=[]。1440/768/390无横向溢出；390完成完整Symbol工作流。

当前Phase8.0～8.6完成，可交负责人统一审核；所有V1.2业务保持未提交、暂存为空。系统级reduced-motion仍pending，由负责人最终补验。

## 负责人补充授权后的门槛记录

2026-10-05：负责人正式通过Phase7功能审核并补充Phase8启动条件。实际Phase7已有本地Checkpoint bc19b6c（相对a5bfb29的22修改/51新增文件），本次核对提交与Phase7完整清单完全一致，工作区干净；没有重复Commit或改写其历史。原提交标题为 `feat(core): add module change domain and web workflow`，保留实际记录。

`native reduced-motion verification = pending`。自动化/CSS检查不能替代Windows系统级实测。Phase8既有实现来自此前连续任务，独立工作树中未提交成果全部保留；本次不新增业务实现，不再启动后续开发、提交或整合。须收到负责人Windows补验PASS，或负责人明确批准带该非阻塞待办继续；补验失败时先针对修复与回归，再推进后续工作。

## 基线与保护

V1.1 完整业务 Checkpoint `bc19b6c`，独立 `feature/symbol-structure-changes` / `Nexus-OpenImpact-symbol-changes`。V1.1 原工作树干净，原 main 不变。后续 V1.2 成果不推送、不合并、不创建 PR，保留独立工作树待审核。Phase 6.6 的三份契约文档不修改，不混入实验或伪造 Ground Truth。

V1.1 功能门槛为 Backend 694 passed、1 skipped，Frontend162 passed、构建通过，六 Function 与两 Module 真实流程完成。真实 reduce 偏好切换受浏览器工具限制，保留待补验记录；不以此声称真实媒体偏好已验证。

## 8.0 源码审计 / 能力矩阵

| 事实 | 当前真实实现 | V1.2 最小增量 |
| --- | --- | --- |
| Scanner / root inventory | 可扫描普通模块，保留源码 hash 与禁用原因 | 直接复用，仍限定受支持根模块 |
| `MAX_RETRIES = 3` / annotation | AST 只收集函数、import、调用及重绑定名称，没有变量定义载荷 | 在同一 AST 上追加变量定义事实 |
| from import 常量 | FunctionIndex 未注册；Module Resolver 不能证明成员，manual_review | 单独变量符号索引，不污染原 FunctionIndex |
| cfg.MAX_RETRIES | FunctionCall 仅用于 callee；普通属性读取未索引 | 追加真实 Name/Attribute Load 与作用域事实 |
| local / alias | 旧函数调用解析已有局部遮蔽；不覆盖普通变量读取 | 变量读取独立校验局部绑定、参数、alias 与全局写入 |
| repeated / conditional | 现有 module_rebindings 只记录集合，不足以证明唯一赋值 | 记录唯一简单定义与完整静态绑定名称，重复/复杂候选禁用 |
| dynamic / re-export | Module 已有部分边界诊断，无变量语义 | 反射、动态导出和不支持作用域保守诊断 |
| Module graph / Evidence | 真实静态导入边、反向关系、安全源码快照读取可复用 | Symbol Direct 是独立引用，使用既有图的反向模块边，证据保留终端引用 |
| Domain/API/React | Function/Module 显式分发，原 File/revision/abort/fingerprint | 增量第三域，旧两域载荷/报告保持 |

计划支持唯一公开模块级简单 Assign/带值 AnnAssign；字面量值不执行。常量和普通变量使用同一模型。from import、alias、两段模块属性、目标模块自身读取可确定绑定；函数局部遮蔽不计。复杂赋值/重复、条件、反射、class/nested/comprehension 等保留边界诊断。Direct 仅 before 项目符号可确定、after 因虚拟定义变化断裂；不推断运行一定失败。

## 阶段门槛

| 阶段 | 状态 | 验证 |
| --- | --- | --- |
| 8.0 | 完成 | 上述矩阵来自 Scanner/Parser/Index/Import/API/React 源码 |
| 8.1 | 完成 | 模型/AST45项通过；模型/引用/AST64项通过 |
| 8.2 | 完成 | 首次完整742 passed、1 skipped；旧694项保持 |
| 8.3 | 完成 | 初始模型/引用/影响64项通过，真实引用与独立终端路径 |
| 8.4 | 完成 | API及旧契约修订后完整767 passed、1 skipped；追加字段实测样例 |
| 8.5 | 完成 | 前端182 passed，三领域隔离、精确对应、生产构建通过 |
| 8.6 | 完成，真实reduce偏好待补验 | 最终793 passed、1 skipped、7 subtests；真实HTTP/浏览器，限制未隐去 |

## 8.1：不可变定义和虚拟操作

新增 `symbol_syntax.py`、`variable_symbols.py`、`symbol_change.py`，在现有 models/AST 单次解析追加默认字段；新增 test_symbol_change。保留原函数 SymbolIndex 和所有既有 AST 输出。根模块、单次公开简单字面量定义、带值 AnnAssign 及冲突命名空间；before 快照精确核对，after 只虚拟定义，不写文件。

## 8.2：静态引用

新增 `symbol_references.py`、test_symbol_references。支持 from import、alias、模块属性与模块自身读取，局部/参数遮蔽、同名模块隔离；引用 ID 来自相对位置和语法事实。重绑定、global 写入、未知属性、复杂作用域保守处理。完整742项通过后继续8.3。

## 8.3：影响与证据

新增 `symbol_impact.py`、`symbol_report.py`、test_symbol_impact。仅 before 已绑定目标、after 因投影缺失旧符号成为 Direct；使用真实 Module Dependency Graph，最多两层、循环/多来源去重。独立 symbol Report v1，路径末端符号引用不伪造模块边。安全源码读取、哈希、unavailable 与规则说明不依赖 LLM。

## 8.4：CLI、API 与样例

修改 `change_domain.py`、`__main__.py`、api.py、zip_inspector.py，新增 CLI/API 测试和四个 Symbol examples。ZIP流程、临时目录、线程池与 fingerprint 保持。Inspect 追加三个 Symbol 字段；旧十个字段用真实接口输出逐项验证相同。只更新原严格字段集合测试，未修改旧字段值或删除安全测试。真实样例文件由接口采集。

## 8.5：React

新增 SymbolSelectView / SymbolChangeView / SymbolReportView、symbolDraft、symbolReportData，增量 Domain/目标/快照分发。保留 Context、API Client、原 File/revision/AbortController，切换清理结果、晚响应丢弃。新增14项状态/契约测试和6项展示测试：162 →182 passed。沿用 Tracework CSS，仅第三领域必要布局，未扩大 Motion。

## 8.6：最终收束与实际失败记录

- 初次API/完整测试暴露 Inspect 样例缺少追加字段，随后又暴露边界诊断新增字段；从实际 TestClient 重采样，确认旧十个字段完全不变。未以修改旧预期掩盖生产错误。
- 初次本地HTTP辅助脚本受Windows编码和外部SOCKS环境影响；设置PYTHONUTF8及本地 trust_env=false，未增加生产依赖。
- 核查发现普通 import / 导入语法边界原先没有进入 Symbol coverage。补充真实诊断与3项回归，from import 已作为引用记录，不重复计入导入诊断。
- 核查发现其他文件动态 setattr/vars/exec 可重新创建旧名，单文件保护不足。新增项目级动态写入manual_review保护和4项回归，保留确定性要求；最终专项81项通过，真实HTTP动态写入0/0/0 partial。
- 最后HTTP辅助脚本为坏ZIP同时发送旧指纹，实际按既有顺序先409；移除该坏ZIP场景的expected_fingerprint后验证400。生产指纹优先规则不变。
- 开发期间修改被引用模块触发Vite Fast Refresh失效，旧页面出现一次Context身份错误；重启开发服务/新会话完整流程无error。未修改Context；不把热更新遗留会话当生产验收。最终新Tab直连8013完整三步、1/1/1 complete、console errors=[]。
- 最终Backend：793 passed、1 skipped、1 warning、7 subtests passed，44.77s；相对V1.1净增99项。警告是现有Starlette/httpx弃用，跳过为既有平台权限用例。
- Frontend：182 passed，check/build成功；相对V1.1净增20项。
- 真实HTTP14个Demo三步200，同ZIP指纹；旧十个CLI JSON同V1.1逐字段相同，Module/Symbol CLI与HTTP主体逐字段相同。错误400/409/422后无新增临时目录残留。
- 浏览器完成旧六个Signature、两Module、Rename/Remove Symbol、无影响、partial/manual/unresolved、422/409、证据读取异常降级和快速Domain切换。1440/768/390无横向溢出、关键诊断保留；桌面与手机实拍在忽略目录。
- 未调用DeepSeek；真实reduced-motion切换工具缺口维持公开，原Motion自动化与CSS未回归。独立Benchmark未交付，新增人工标注空模板，不填答案或准确率。

## 交付索引

契约 `symbol-changes.md`，完整验收 `phase8-acceptance.md`，统一两轮报告 `v1.1-v1.2-delivery.md`。V1.1因用户明确要求连续完成两轮，建立本地Checkpoint bc19b6c后隔离V1.2；旧Phase7验收内“未提交”描述为该阶段审核时状态，以此次实际Git关系记录为准。V1.2业务成果不自动提交，暂存区为空，未Push或Merge main。

## 视觉约束

已实际读取 frontend-design SKILL.md，继续沿用 DESIGN.md Tracework Token/字体/阅读层次；第三域只加入真实符号选择和定义变化，源码证据保持主阅读区域。不另建主题或扩大 Motion。
