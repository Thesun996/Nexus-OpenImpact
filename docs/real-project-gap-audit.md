# 真实开源项目差距审计：python-dotenv

日期：2026-10-05。审计 OpenImpact 基线：`85aeef21d82e872bd666eda026a882da872810e9`，叠加当前工作树已有的中文展示与解释文案修改。

## 目的与结论

回答“现有能力在真实开源项目中有什么价值，以及优先补什么”。本轮只新增审计资料和复现脚本，未修改生产分析算法、API 或 React。

现有 before/after 兼容性判定、同文件调用追踪、有限反向传播和源码证据在选定案例中有效。但常见的 `src/` 包布局、相对导入和公共 API 重导出尚未贯通，导致有真实调用的目标返回零个已确定影响。报告对此返回 `partial`，不能据零结果推断项目安全。

这是一个固定项目的能力差距审计。源码复核由 Codex 辅助完成，包含选定证据位置，并非独立人工盲标 Ground Truth，不计算 Precision、Recall 或准确率，不改变冻结数据集的标注状态。

## 上游来源与输入

- 项目：[theskumar/python-dotenv](https://github.com/theskumar/python-dotenv)。
- 固定版本：[v1.1.1](https://github.com/theskumar/python-dotenv/releases/tag/v1.1.1)。本审计不声称它是最新版本。
- 实际 commit：`16e660d384b942b11879b44500afbbe021650448`。Git 的 annotated tag 对象与 commit ID 不同，复现脚本验证 commit。
- [setup.py](https://github.com/theskumar/python-dotenv/blob/16e660d384b942b11879b44500afbbe021650448/setup.py#L37) 显式声明 `package_dir={"": "src"}`；库代码位于 `src/dotenv/`，包含包初始化文件、类方法、模块级函数及相对导入。
- 本地读取全部 19 个受 Git 跟踪的 Python 文件，包括库代码、测试和 `setup.py`；HTTP ZIP 保持其目录结构，仅包含这 19 个源文件，外面增加一个项目包装目录。它是源码审计 ZIP，不声称是完整发布包。
- 未安装、导入、执行 python-dotenv，未运行它的测试、安装脚本、CLI 或配置文件。模型模式强制为 `rule`，没有 DeepSeek 请求。
- 原始源文件逐文件 SHA-256 存于本地 `source-review.json`；前后字节比对一致。Windows checkout 的换行字节可能与 Linux 不同，因此 ZIP 指纹和文件哈希对应本次实际输入，不能把不同平台的 ZIP 字节误认为必然相同。

## 先读源码，再生成预测

选定以下真实调用位置作为复核线索。假设仅增加一个没有默认值的 keyword-only 参数 `strict`，原调用保持原样。源代码仅供分析，不实际改写。

| 变更目标 | 预先阅读的调用位置 | 需要验证的事实 |
| --- | --- | --- |
| `parser.parse_key` | `src/dotenv/parser.py:147`，`parse_binding` 调用 | 同模块调用能否绑定并生成 Direct；`parse_stream` 能否成为上游 1-hop |
| `parser.parse_stream` | `src/dotenv/main.py:185,218` | `set_key`、`unset_key` 通过相对导入调用，是否被遗漏 |
| 同上 | `src/dotenv/main.py:85` | `DotEnv.parse` 内的调用是否进入支持范围或有明确边界提示 |
| 同上 | `tests/test_parser.py:169` | `from dotenv.parser import ...` 是否能对应 `src/` 内定义 |
| `main.find_dotenv` | `src/dotenv/main.py:354,391` | 两个同文件调用能否分别评估 |
| `main.load_dotenv` | `tests/test_main.py:242` | 经 `import dotenv` 和包初始化重导出的公共 API 能否追踪 |

以上是选定位置，未宣称穷尽所有相关调用。测试函数的装饰器、类作用域、条件执行等也具有额外语义；静态关系不能证明某次运行一定经过该路径。

可查证来源：[parser.py](https://github.com/theskumar/python-dotenv/blob/16e660d384b942b11879b44500afbbe021650448/src/dotenv/parser.py#L147)、[main.py](https://github.com/theskumar/python-dotenv/blob/16e660d384b942b11879b44500afbbe021650448/src/dotenv/main.py#L185)、[包初始化](https://github.com/theskumar/python-dotenv/blob/16e660d384b942b11879b44500afbbe021650448/src/dotenv/__init__.py#L3)、[测试调用](https://github.com/theskumar/python-dotenv/blob/16e660d384b942b11879b44500afbbe021650448/tests/test_main.py#L242)。

## 实际分析结果

OpenImpact 当前从 ZIP 根目录生成 Symbol ID，因此下表保留实际 `src.dotenv...` 标识，不将其伪装为 Python 安装后的 import 名称。

| Case | 实际目标 ID | Direct | 1-hop | 2-hop | Coverage |
| --- | --- | ---: | ---: | ---: | --- |
| `same_file` | `src.dotenv.parser.parse_key` | 1 | 1 | 0 | partial |
| `cross_file_and_method` | `src.dotenv.parser.parse_stream` | 0 | 0 | 0 | partial |
| `same_file_public_function` | `src.dotenv.main.find_dotenv` | 2 | 0 | 0 | partial |
| `package_public_api` | `src.dotenv.main.load_dotenv` | 0 | 0 | 0 | partial |

- `same_file`：Direct 在 `parser.py:147`；1-hop 是 `src.dotenv.parser.parse_stream`，其实际调用位置为 `parser.py:175`。两份 Evidence 的文件 SHA-256 均与实际源文件一致。
- 源码阅读还给出候选上游链 `set_key / unset_key → parse_stream → parse_binding → parse_key`（调用分别在 `main.py:185,218`、`parser.py:175,147`）。对应前一案的 2-hop 上游没有进入系统结果，因为跨文件相对导入未绑定。这条链作为审计复核线索保留，未回填为系统 Evidence，也未标记为 locked 标注。
- `same_file_public_function`：Direct 分别在 `main.py:354,391`。两份 Evidence 的文件 SHA-256 均一致。
- 另外两案没有确定 Direct，也没有 Evidence；系统没有为遗漏位置伪造证据或传播路径。
- 未解析导入：97 个绑定条目为 `module_not_in_project`，16 个为 `relative_import_unsupported`。前者包含正常外部依赖，不能全部计作内部导入缺陷。
- 函数图：22 个已解析调用点、533 条未解析调用记录。未解析中包括局部名称、外部依赖、模块顶层调用和复杂表达式等。类方法和嵌套函数体另有被排除的调用，因此这些数量不是全部 AST 调用的准确率分母。
- 19 个文件均成功解析；索引 19 个模块、96 个模块级函数。源码解析成功与语义分析覆盖完整是两种不同事实。
- 最终复验的四次本地 pipeline + Report 用时约 225～233 ms；这是单机单次观察，未排除缓存、系统负载和环境差异，不是性能 Benchmark。

## 真实 HTTP 工作流

使用本工作树的 FastAPI，在自动分配的独立 loopback 端口启动，未占用或重启负责人正在运行的 8000/5173 服务。

- 同一个源码 ZIP：Inspect 返回 200；四案分别 Validate 200、Analyze 200。
- 四案 HTTP summary 与本地 pipeline 完全一致，coverage 均为 partial。
- Inspect 和 Validate 的指纹均等于该 ZIP 的 SHA-256；Analyze 发送相同 ZIP 和 expected_fingerprint。现有 Signature Analyze 响应不返回指纹字段，复现脚本不假设该字段存在。
- 错误指纹 Analyze 返回 409 `fingerprint_mismatch`，未分析另一份项目。
- 尝试重命名 `src.dotenv.parser`：Validate 返回 422 `unsupported_module_layout`，没有绕过既有 flat-root 模块范围限制。
- Inspect 的 selectable module 数量为 1，唯一可选项是根目录 `setup.py`；实际库模块均在包目录内，当前不能作为 Module Change 候选。
- 10 个请求临时目录全部清理，其中包括模块校验失败请求；源文件未改变。
- HTTP 分析报告继续提示：“分析范围不完整；结果仅覆盖已成功解析的代码，未报告影响不能视为确定无影响。”

## 差距分类与源码依据

| 项目 | 分类 | 当前实现依据 | 对学生用户的影响 |
| --- | --- | --- | --- |
| `src/` 与 import 根不同 | 高优先级能力缺口 | `analysis/symbol_index.py::_module_name` 按路径生成名称，没有 source-root 配置 | 上传常见包项目后，测试里的 `dotenv` 与定义的 `src.dotenv` 无法绑定 |
| 相对导入 | 高优先级能力缺口 | `SymbolIndex._bind` 对 `level>0` 返回 `relative_import_unsupported` | `main.py` 到 `parser.py` 的清晰静态关系未进入函数图 |
| 包公共 API 重导出 | 后续能力缺口 | 当前绑定不追踪包初始化中的导入链 | 用户常用的 `dotenv.load_dotenv` 无法追溯到 `main.load_dotenv` |
| 类方法中的调用 | 已声明边界，仍需更清晰呈现 | `ASTParser` 的 `_CallCollector.visit_ClassDef` 不遍历方法体 | `DotEnv.parse` 中的真实调用缺席；通用未解析计数不包含所有被排除作用域 |
| Module/Symbol 只支持普通根模块 | 已声明边界 | `ModuleInventory.from_index` 将包与 nested 模块设为不可选 | 不能使用本项目的库文件演示模块重命名或删除；422 拒绝符合当前契约 |
| 诊断过多且混合原因 | UX 改进机会 | Report 汇总整个项目 unresolved，包含外部依赖、顶层调用和内部关系缺口 | 用户容易误解几百条未解析与当前变更的关系 |

本次选定受支持案例中，未发现可复现的错误确定性 Direct、错误证据哈希或虚构传播路径。这不等于证明所有代码均正确。上述包、方法问题应登记为能力缺口，避免描述成当前已承诺支持场景全部失效。

## 推荐的下一阶段

1. **先贯通静态包路径**：显式 source-root 选择/配置；普通 `__init__.py` 包的相对导入；项目内唯一目标绑定。保留同名隔离、冲突拒绝及外部依赖的保守边界。不执行 `setup.py` 推断配置，不自动猜测多根项目。
2. **提高边界可见性**：区分源码解析、支持作用域和绑定结果；显示被排除的类方法/嵌套作用域。零确定影响但 partial 时，给出具体缺口和人工检查入口。若需要扩展公开字段，先单独设计向后兼容契约。
3. **再增加有限重导出**：只追踪明确且无重绑定的静态 re-export 链；加入循环、多源冲突和未知初始化行为的拒绝案例。
4. **用真实变化持续验证**：每项能力先补独立人工复核的真实调用样本，再实现。性能、准确率和学生理解提升分别评估，不能用 Demo 通过数替代产品效果。

不建议此时扩展所有类继承、动态属性或复杂运行时行为。成本包括作用域绑定、Python 包搜索路径、多根冲突、装饰器和运行时重绑定处理；扩大支持范围必须保持 Evidence-first 确定性。

项目价值可以体现为：在真实项目中准确找出分散调用、关联有限上游路径、说明证据和未覆盖区域，让学生知道应该检查哪些文件。单个“缺少必填参数”报错只是其中一个可验证规则。现阶段优先补真实项目适用性，尚无独立效果指标支持“已显著提升开源维护效率”的结论。

## 复现

在仓库根目录，使用已经安装 OpenImpact 和后端开发依赖的 Python 环境：

```sh
git clone --depth 1 --branch v1.1.1 https://github.com/theskumar/python-dotenv.git .local/real-project-audit/python-dotenv-v1.1.1
python scripts/audit_python_dotenv.py .local/real-project-audit/python-dotenv-v1.1.1
```

如该本地 checkout 已存在，直接运行第二行，不覆盖现有目录。脚本校验固定 commit 与选定源码行，强制 rule，运行独立真实 HTTP 服务，并在结束后关闭它。

产物位于忽略目录 `.local/real-project-audit/results/`：

- `source-review.json`：预先阅读的位置和实际源文件哈希，明确标记 `not_ground_truth`。
- `results.json`：分析与 HTTP 观测。
- `*-report.json`、`*-http-report.json`：实际报告，项目路径为 `.`。
- `inspect-response.json`、`nested-module-validation.json`：实际响应。
- `python-dotenv-v1.1.1-sources.zip`：本次源码输入，可由负责人手动上传复验。

这些输出不进入生产 fixtures，不纳入 Git 提交，也不参与冻结 Benchmark 的标准答案。

## 回归与保护

- 前端：`npm run check`，191 passed，包含生产 build 成功。
- Backend：统一进程环境后完整 pytest 为 798 passed、1 skipped，另有 7 subtests passed（42.22 秒）；保留一条现有测试客户端依赖弃用警告。
- 初次 `python -X utf8 -m pytest` 出现 2 failed、796 passed、1 skipped：父进程强制 UTF-8、测试子进程仍用 Windows 本地编码，导致 JSON stdout 解码失败；未修改测试或断言。采用进程环境 `PYTHONUTF8=1` 和 `OPENIMPACT_LLM_PROVIDER=rule` 统一复验。
- 已有 1,288 个文件建立逐字节保护快照，结束时全部一致；本轮只新增本文与审计脚本。上游 checkout 的 Git status 也保持干净。`git diff --check` 通过。
- 本轮不填写、review 或 lock Ground Truth；不修改 Core、不调用模型，不处理其他工作树的标注资料。
- 既有 `native reduced-motion verification` 与独立人工 Benchmark 的尾项不因此次审计标记为 PASS。
- 最新 fetch 后，`origin/main` 为 `3a5a582`，当前 HEAD 比它多 10 个提交；工作树还有本轮开始前的 27 个已跟踪修改及前端新增文件。本次不将这些既有成果混入审计发布或合并，保留原状态。
