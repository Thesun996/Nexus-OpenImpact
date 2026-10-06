# 调用覆盖修订与真实项目验证

日期：2026-10-06（Asia/Shanghai）。

## 修复范围

此前类定义、嵌套函数整体排除，导致这些区域内明确指向项目模块级函数的调用也被遗漏。现在记录具名调用方，并复用既有目标解析、Before/After 兼容性、Direct、两层上游传播及 Evidence。可选择的变更目标仍只包含模块级函数。

| 源码情况 | 当前处理 |
| --- | --- |
| 普通/异步类方法中 `f(...)`，f 为明确项目模块函数 | 检查局部遮蔽后解析 |
| 嵌套函数中对模块级 f 的明确引用 | 检查外层闭包与本地绑定后解析 |
| 参数、赋值、局部 import、except / match 捕获或泛型参数遮蔽 f | 保守 unresolved，不猜测 |
| 同一限定调用方重复定义 | caller_not_indexed，不生成确定边 |
| 类属性与模块函数同名 | 方法名称查找不把类属性当作闭包；遵循 Python 词法规则 |
| 显式 `import pkg.utils` 后 `pkg.utils.f()` | 需已绑定项目模块及明确 dotted import；检查已知属性重绑定 |
| 只有 `import pkg`，目录中存在 utils.py | 文件存在不足以证明属性暴露，不猜测 |
| `self.method()`、实例动态分派、回调参数、函数对象转发 | 仍 unresolved，无猜测传播路径 |
| lambda 体中的明确模块函数调用 | 检查参数、闭包、推导式迭代变量与本地绑定后解析；不推测回调执行路径 |
| 无不确定命名空间的类定义体及方法默认参数中的调用 | 检查类局部遮蔽、外层绑定及模块加载时的定义顺序后解析 |
| 类基类、metaclass 或 locals / globals / exec / eval 相关动态命名空间 | 调用仍收集，保守 unresolved；不生成确定边 |

不会执行、导入或改写上传源码。运行时 monkey patch、动态 import、任意命名空间修改、复杂装饰器/继承分派等仍不被穷尽。普通包映射仍采用用户声明的源码根目录；外部依赖或搜索路径的不确定性保留诊断。名称绑定规则依据 [Python 执行模型](https://docs.python.org/3/reference/executionmodel.html)。

## 覆盖展示

源码读取、语法解析和调用绑定是不同环节。`coverage=complete` 只表示当前支持模型中没有已记录缺口，不保证任意 Python 运行行为完全覆盖。partial 警告继续保留，零影响不能推导整个项目无影响。

partial 的可选 `coverage.details` 展示源码解析成功/总文件、已确认调用、未确认调用、暂不支持作用域中的调用数。Inspect/Validate 未构建调用图，因此不提供已确认/未确认调用数。所有数值来自实际扫描与图记录；不生成进度、准确率或目标漏检百分比。

## Boltons 功能观察

官方仓库冻结 commit：`4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d`，来自 [mahmoud/boltons](https://github.com/mahmoud/boltons/tree/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d)。仅静态读取 ZIP 中 65 个 Python 文件；无源码执行、上游测试运行或独立 Ground Truth 标注。

| 拟定变更 | 修订前 Direct / 1层 / 2层 | 修订后 | 真实源码 |
| --- | --- | --- | --- |
| human_readable_list：delimiter → separator | 6 / 0 / 0 | 6 / 0 / 0 | tests/test_strutils.py 第192、198、204、234、240、243行 |
| iterutils.first：key → predicate | 0 / 0 / 0，测试类未进入范围 | 5 / 0 / 0 | tests/test_iterutils.py 第65–69行；TestFirst.test_selection |

具名作用域修订当时解析 65/65 文件，仍为 partial：1,481 个具名调用方，478 条已确认调用边，5,754 条未确认调用记录，63 个被排除的调用。旧版未确认记录为 3,264；增长来自纳入原先跳过的区域，并不代表新增了 2,490 处实际失败或漏检。外部导入、对象方法与运行时机制仍有限制。

两例确定影响的源码证据可用。测试类中的调用可以显示为影响，但“相关测试”候选筛选暂只支持模块级测试函数；空候选不代表没有应检查的测试类。

## 回归记录

具名调用、遮蔽、四种操作、星号保守策略、属性重绑定、Evidence、ZIP/指纹与 UI 文案有专项回归；新增后端 35 项、前端 4 项。保留并更新旧测试中“方法/嵌套一律排除”的断言为明确的新增支持结果，没有删除安全性测试或修改生产哈希规则。

使用同一份源码字节比较修订前后的 15 个既有 Demo，完整 JSON 逐字段不变，包括 Evidence 哈希。原 format_date + timezone 为 1/1/1 complete；page.page + zone 为 0/0/0 complete。

真实 rule HTTP 与浏览器均完成标准两例，以及 Boltons 的 first 参数重命名 5/0/0 partial。影响选择从第65行切到第69行时，源码与解释对应；更换 ZIP 和目标后原项目证据、统计、选择均清除。390px 手机覆盖提示保留，文档宽度与视口宽度均375px（可用宽度扣除滚动条），无页面横向溢出；浏览器控制台无错误。

前端 npm run check：216 passed；生产构建成功。完整后端 pytest：991 passed、2 skipped、7 subtests passed；跳过项为 Windows 无符号链接创建权限，保留既有 Starlette TestClient 弃用提示。QA 不触发真实 DeepSeek。Windows 系统级 reduced-motion 和独立 Benchmark 仍 pending。

## 类定义体与匿名函数增量（2026-10-06）

新增不可变 `CallScope` 仅描述调用上下文。`SymbolIndex.symbols` 的变更目标保持模块级函数；`callers` 同时容纳具名函数与源码定位的上下文。现有 Direct 兼容性及两层反向传播算法未修改。原始 ZIP、fingerprint、请求版本保护及 Evidence 对应规则保持原样。

`caller_symbol_id` / `impacted_symbol_id` 可新增 `module.Class.<class_body@行:列>` 或 `module.<lambda@行:列>` 形式；这两个标识不宣称类体是函数或匿名函数拥有可推断的调用者。列仍为从零开始的 AST UTF-8 字节偏移。稳定性限定于同一源码快照，源码位置变化后需要重新分析。报告 schema_version=1 及原有字段保持。partial 的可选 details 增加 `additional_call_scope_count`，`named_caller_count` 仍只计具名函数。

类体调用包括属性初始化、方法装饰器及方法默认参数中的调用。类绑定采用保守遮蔽策略，不通过猜测语句分支、类属性取值或元类命名空间来确认目标；继承/元类涉及的类体调用会保留明确未确认原因。模块加载时执行的类体引用若先于对应 import / function 定义，记录 `call_before_binding`，避免将原本未绑定的问题归因于签名变更。匿名函数参数、闭包绑定与推导式变量同样检查。类属性不会被误作方法或匿名函数的词法闭包。

只添加实际源码中出现的调用边。定义/创建匿名函数不建立“外层函数调用匿名函数”的边；声明类不建立“外层函数调用类体”的边。若一个类体或匿名函数确实调用已有 wrapper，其到 wrapper 的真实边可以成为上游检查记录。网页用“上游调用方”描述统计，并明确解释这两类来源，不改变计数规则。

与同一冻结 Boltons ZIP 的基线逐位置对比：原来 39 个类体调用及 24 个匿名函数调用全部进入收集/解析，共 63 处；8 处确认项目模块函数目标，55 处仍 unresolved。未确认原因分布：名称不在函数索引 9、局部遮蔽 16、未解析导入 3、不确定类命名空间 5、模块名称重绑定 22。新版已确认边 486，未确认调用 5,809，排除作用域调用 0，语法解析仍 65/65，coverage 仍 partial。这些数值表示当前静态模型的处理结果，不是独立准确率或运行失败数量。

实际新定位案例：对 `boltons.cacheutils.cachedmethod` 新增仅关键字必填参数 `strict`，确认 `tests/test_cacheutils.py` 第310、314、318行三处类体装饰器调用不兼容，Direct/1层/2层=3/0/0，partial；源码片段与证据来自原文件。既有 human_readable_list 改名仍6/0/0、first 改名仍5/0/0。上传源码未执行，Boltons 测试未运行。

专项新增 47 项后端测试覆盖来源位置、哈希、别名、遮蔽、类命名空间、定义顺序、同一行多匿名函数、四种变更、星号人工检查、既有问题与传播边界；两项网页渲染测试确保说明不伪造外层路径。旧“整体排除”测试改为明确支持结果并保留确定性防护。15个既有 Demo 使用相同字节比较，完整 JSON 逐字段不变。

最终回归：Backend 1,038 passed、2 skipped、7 subtests passed；Frontend 220 passed；npm run build 通过。真实 rule HTTP 与浏览器的标准 A=1/1/1 complete、B=0/0/0 complete，类体/匿名专项=2/0/0 complete，Boltons cachedmethod=3/0/0 partial；切换 Evidence 与解释同步，更换项目/目标后无旧统计或选择残留。Boltons 从第310行切至318行时展示各自真实装饰器源码，原“另有63个调用”排除提示消失，未确认调用及 partial 提示继续保留，浏览器无控制台错误。浏览器采用当前工作树的 Vite 生产预览及 /api 代理，开发热更新页面在内置验收浏览器中未加载，故未将其记为通过。Windows 系统级 reduced-motion 与独立 Benchmark 继续 pending。
