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
| lambda、类定义体中的调用 | 继续列出排除作用域并标记 partial |

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

新版解析 65/65 文件，仍为 partial：1,481 个具名调用方，478 条已确认调用边，5,754 条未确认调用记录，63 个被排除的调用。旧版未确认记录为 3,264；增长来自纳入原先跳过的区域，并不代表新增了 2,490 处实际失败或漏检。外部导入、对象方法与运行时机制仍有限制。

两例确定影响的源码证据可用。测试类中的调用可以显示为影响，但“相关测试”候选筛选暂只支持模块级测试函数；空候选不代表没有应检查的测试类。

## 回归记录

具名调用、遮蔽、四种操作、星号保守策略、属性重绑定、Evidence、ZIP/指纹与 UI 文案有专项回归；新增后端 35 项、前端 4 项。保留并更新旧测试中“方法/嵌套一律排除”的断言为明确的新增支持结果，没有删除安全性测试或修改生产哈希规则。

使用同一份源码字节比较修订前后的 15 个既有 Demo，完整 JSON 逐字段不变，包括 Evidence 哈希。原 format_date + timezone 为 1/1/1 complete；page.page + zone 为 0/0/0 complete。

真实 rule HTTP 与浏览器均完成标准两例，以及 Boltons 的 first 参数重命名 5/0/0 partial。影响选择从第65行切到第69行时，源码与解释对应；更换 ZIP 和目标后原项目证据、统计、选择均清除。390px 手机覆盖提示保留，文档宽度与视口宽度均375px（可用宽度扣除滚动条），无页面横向溢出；浏览器控制台无错误。

前端 npm run check：216 passed；生产构建成功。完整后端 pytest：991 passed、2 skipped、7 subtests passed；跳过项为 Windows 无符号链接创建权限，保留既有 Starlette TestClient 弃用提示。QA 不触发真实 DeepSeek。Windows 系统级 reduced-motion 和独立 Benchmark 仍 pending。
