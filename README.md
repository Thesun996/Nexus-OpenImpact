# Nexus OpenImpact

网页已增加报告追问和只读项目源码目录：可从影响证据或回答引用打开完整 Python 文件并定位行号。追问依据当前变更报告，模型不可用时明确使用规则回答。详见 [报告工作台](docs/report-workspace.md)。后端与前端启动方式保持原流程。

普通包支持已扩展：网页可显式选择源码根目录，支持普通包的静态相对导入。src 布局填写 `src`；默认 `.` 保留旧流程。详见 [使用方式与边界](docs/package-imports.md) 和 [包项目 Demo](examples/package_signature_change/README.md)。

调用覆盖已补齐：类方法与嵌套函数中的明确模块级函数引用进入签名检查；报告分别展示源码解析、已确认调用和未确认调用数量，保留 partial 的真实边界。详见 [覆盖修订与 Boltons 实测](docs/call-coverage.md)。

## AI 驱动的代码变更影响分析助手

---

## 项目简介

Nexus OpenImpact 是一个面向学生开发者和开源贡献者的代码变更影响分析工具。

它帮助开发者回答：

> “如果我修改某段代码，会影响项目中的哪些部分？为什么？”

项目通过静态代码分析技术，分析代码之间的调用关系，
识别修改可能影响的函数、模块以及调用路径，并生成带有代码证据的影响报告。

---

## 项目目标

很多开发者在修改开源项目时会遇到：

- 不清楚修改会影响哪些地方；
- 不理解函数之间的依赖关系；
- 修改后容易产生隐藏错误。

OpenImpact 希望通过 AI 与静态分析结合，
帮助开发者理解代码变化带来的影响。

---

## 当前开发阶段

当前阶段：

当前独立集成成果支持三个领域、八种变更：四种函数签名变更、模块重命名/删除、公开模块级变量或常量重命名/删除。CLI、ZIP Inspect / Validate / Analyze 与 Tracework React 均可使用。三个领域分别保持签名兼容性、静态导入绑定、静态符号引用的判定依据；上游传播只建议检查。V1.1 / V1.2 成果尚待负责人最终审核，未合并 main。详见 [两轮交付报告](docs/v1.1-v1.2-delivery.md)、[模块契约](docs/module-changes.md) 和 [符号契约](docs/symbol-changes.md)。

目标：

完成项目基础结构搭建，
并逐步实现 Python 代码变更影响分析能力。

---

## 本地安装与 Demo

需要 Python 3.11 或更新版本。在 PowerShell 中，将 `<仓库地址>` 替换为团队实际仓库地址：

```powershell
git clone "<https://github.com/lhy070311/Nexus-OpenImpact.git>" Nexus-OpenImpact
cd Nexus-OpenImpact
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m openimpact analyze examples/signature_change --change examples/signature_change/change.json
python -m openimpact analyze examples/signature_change --change examples/signature_change/change.json --format json
```

预期摘要：Direct 1、1-hop 1、2-hop 1、coverage complete。项目版本为 `0.1.0`；Core 分析仍使用标准库，HTTP 服务安装 FastAPI 和 Uvicorn。运行完整测试时，在已激活的虚拟环境内执行 `pip install -e ".[test]"` 和 `python -m pytest -q`。

删除参数 Demo 使用独立的 `examples/parameter_removal`，保持原 Demo 不变：

```powershell
python -m openimpact analyze examples/parameter_removal --change examples/parameter_removal/change.json
python -m openimpact analyze examples/parameter_removal --change examples/parameter_removal/change.json --format json
```

该示例计划删除 `utils.format_date` 的可选参数 `timezone`，现有调用仍显式传入它，预期同样为 1 / 1 / 1、complete。未提供被删除可选参数的调用仍可兼容，不能计为 Direct。当前支持删除 positional-only、positional-or-keyword 和 keyword-only 参数；拒绝删除 `*args` / `**kwargs`。类型模型和限制见 [Change Type 架构](docs/change-types.md)。

重命名 Demo 分别验证关键字调用与纯位置调用：

```powershell
python -m openimpact analyze examples/parameter_rename_keyword --change examples/parameter_rename_keyword/change.json --format json
python -m openimpact analyze examples/parameter_rename_positional --change examples/parameter_rename_positional/change.json --format json
```

两者都计划将 `utils.f(a, timeout)` 的 timeout 改为 delay。keyword Demo 的实际调用仍传 `timeout=5`，预期 1 / 1 / 1、complete；positional Demo 使用 `f(a, 5)`，预期 0 / 0 / 0、complete。新名须合法且不重名，拒绝重命名 positional-only、`*args`、`**kwargs`。当前仅评估调用兼容性，不分析函数体旧名引用、reflection / inspect.signature、docstring / type comment / 外部字符串引用；不会替用户修改源码。

移除已有默认值的两个 Demo：

```powershell
python -m openimpact analyze examples/parameter_required_missing --change examples/parameter_required_missing/change.json --format json
python -m openimpact analyze examples/parameter_required_explicit --change examples/parameter_required_explicit/change.json --format json
```

计划将 `utils.connect(address, timeout=30)` 改为 `connect(address, timeout)`。missing Demo 省略 timeout，预期 1 / 1 / 1、complete；explicit Demo 显式传入 timeout，预期 0 / 0 / 0、complete。支持三个普通参数 kind，拒绝 `*args` / `**kwargs`、原本已必填的参数和非法默认值顺序；不重排其他参数。`None`、False、0、空字符串都属于现有默认值。本轮仅分析调用签名兼容性，不分析函数体逻辑、默认值变化的业务行为、reflection / inspect.signature、docstring 或 external configuration。

本地启动 Demo API：

```powershell
python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

分析任务由独立的本机 Worker 领取。需要项目库的“开始分析”或失败任务重试时，另开一个终端运行：

```powershell
python -m openimpact.worker
```

Worker 和 API 必须使用相同的 `OPENIMPACT_DB_PATH` 与 `OPENIMPACT_SNAPSHOT_DIR`（未设置时均使用仓库内 `.openimpact/`）。开发时可用 `python -m openimpact.worker --once` 只处理一项已排队任务。另开终端可调用 `GET http://127.0.0.1:8000/api/v1/health` 或 `POST http://127.0.0.1:8000/api/v1/demo/analyze`。请求与响应字段见 [API 契约](docs/api-contract.md)。

### 解释 Provider 配置

`create_explanation_provider()` 默认读取 `OPENIMPACT_LLM_PROVIDER=rule`，使用本地规则解释。需要在 Python 中主动调用 DeepSeek 解释时，可在当前 PowerShell 会话设置环境变量：

```powershell
$env:OPENIMPACT_LLM_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "<你的 Key>"
```

CLI JSON 和分析 API 现已在报告中返回 `explanations[]`，默认由本地规则生成。只有配置 DeepSeek 且存在 Key 时，解释阶段才会向模型发送本次 Evidence 中的源码片段、位置、变更描述、规则、原因和调用路径；请求失败或输出校验失败时使用规则解释。`explanations[]` 与 `evidences[]` 同序，证据不可用时对应的解释为 `null` 并附诊断。不要把真实 Key 写入仓库或提交到 Git。

真实 API 联调可运行 `python scripts/deepseek_live_check.py`；替换 Key 时可加 `--prompt-key` 在本地终端隐藏输入。脚本明确区分模型成功与规则回退，完整操作和本轮实际结果见 [DeepSeek 联调说明](docs/deepseek-live-check.md)。

检查自己的 Python 项目时，先将源码打成 ZIP，再调用：

```powershell
curl.exe -X POST -F "file=@project.zip;type=application/zip" http://127.0.0.1:8000/api/v1/projects/inspect
```

此 inspect 接口只读取 `.py` 源码并建立符号索引，不运行上传代码。返回模块、模块级函数、参数、覆盖状态及解析诊断；上传文件在请求结束后清理。ZIP 需满足上传大小、条目数及解压上限，具体数值、项目根目录识别和错误码见 [API 契约](docs/api-contract.md)。HTTP 请求不接受服务器本地项目路径。

选择 inspect 返回的 Symbol ID 后，可把简化变更 JSON 作为 `change` 表单字段，连同同一 ZIP 提交到 `POST /api/v1/changes/validate`。可选 `expected_fingerprint` 用于核对文件版本。服务会从源码读取当前签名，按新增、删除、重命名或移除默认值配置构建 ChangeSpec，并交给 Core Validator 校验；请求格式及诊断见 [API 契约](docs/api-contract.md)。删除配置示例为 `{"change_type":"remove_parameter","target_symbol_id":"utils.format_date","parameter_name":"timezone"}`，重命名配置示例为 `{"change_type":"rename_parameter","target_symbol_id":"utils.f","parameter_name":"timeout","new_parameter_name":"delay"}`；移除默认值配置为 `{"change_type":"make_parameter_required","target_symbol_id":"utils.connect","parameter_name":"timeout"}`。所有类型均使用现有 API 路径。

使用同样的表单字段调用 `POST /api/v1/projects/analyze`，即可对本次上传的 ZIP 生成 Core JSON 影响报告。报告中的 `project_path` 为相对根目录 `.`；`coverage.status=partial` 时需结合诊断查看未覆盖代码，零条影响不代表整个项目确定无影响。调用示例和状态码见 [API 契约](docs/api-contract.md)。

前端开发可直接使用 [前端交接说明](docs/frontend-handoff.md) 与 [真实 HTTP 响应样例](docs/api-samples/inspect-response.json)。上传页选择“保存并读取项目”后，可以刷新页面并从项目库选择“使用此快照分析”，无需再次上传 ZIP。直接读取 ZIP 的原流程仍可使用。快照接口、存储边界和验收见 [项目快照分析](docs/snapshot-workflow.md)；当前仍为本机工作台，没有账号级项目隔离。

独立人工标注 Benchmark 到位后，可运行：

```powershell
python -m openimpact.evaluation path/to/benchmark --output .local/evaluation-result.json
```

Runner 会先验证 manifest、源码/变更/标签 SHA-256 和人工复核元数据，再用静态分析输出与标签比较 Direct、Indirect 和 coverage。它不会运行样本源码，也不会使用项目内 Demo 或 analyzer 输出冒充 Ground Truth。目录与字段要求见 [评测契约](docs/evaluation-contract.md)。

---

## V1 第一版本目标

第一版本主要支持：

- Python 项目分析；
- 模块级函数分析；
- 明确 import 关系分析；
- 函数签名变化检测；
- 调用影响传播分析；
- 代码证据生成；
- 中文解释报告。

---

## 核心流程

当前支持递归发现 `.py` 文件，忽略 `.git`、`.venv`、`__pycache__`、
`node_modules`、`dist`、`build` 目录，以及符号链接和 Windows junction。
扫描返回按路径排序的相对 `Path` 列表，不读取或执行目标源码。
调用方可通过 `scanner.project_path / relative_path` 获取完整路径。
不存在的输入抛出 `FileNotFoundError`，文件输入抛出 `NotADirectoryError`；
遍历错误向调用方传播。扫描期间项目目录应保持稳定。

```python
from openimpact.repository.scanner import RepositoryScanner

scanner = RepositoryScanner("path/to/project")
for relative_path in scanner.scan():
    print(relative_path.as_posix())
```

在项目根目录的 PowerShell 中执行测试（仅使用 Python 标准库）：

```powershell
python -m unittest discover -s tests/repository -v
```

单文件 AST Parser 可使用 `ASTParser(path).parse()`。它返回 `ParsedModule`：模块级函数、模块顶层 import、调用语法事实，以及读取、编码或语法错误诊断。调用名称尚未绑定到函数定义。解析器不会执行目标源码。

```python
from openimpact.analysis.ast_parser import ASTParser

result = ASTParser("path/to/project/report.py").parse()
for function in result.functions:
    print(function.name, function.parameters)
```

完整测试可在项目根目录运行：

```powershell
pip install pytest
python -m pytest -q
```

`SymbolIndex(project_path).build()` 使用扫描与解析结果登记项目模块、模块级函数，以及明确 import 的本地绑定。`symbols` 以 `module.function` 为键；`bindings` 记录本地名称的项目内模块或函数目标，无法确认时保存 `unresolved` 与原因。索引不会解析 `FunctionCall` 的目标。

```python
from openimpact.analysis.symbol_index import SymbolIndex

index = SymbolIndex("path/to/project").build()
print(index.symbols)
print(index.bindings)
```

`CallGraph(index).build()` 将已解析的函数调用保存为 `edges`，将模块顶层、动态或无法确认目标的调用保存为 `unresolved_calls`。调用边只表示静态可确定的关系，不表示运行时一定执行或发生错误。

```python
from openimpact.analysis.call_graph import CallGraph

graph = CallGraph(index).build()
print(graph.edges)
print(graph.unresolved_calls)
```

`ChangeSpec` 通过结构化的修改前后签名、目标 Symbol ID 和新增参数描述计划变化；`validate_change_spec(index, spec)` 检查目标、当前签名及“新增必填参数”的合法性，返回诊断，不修改源码。当前只支持此一种变化类型。

`analyze_direct_impact(graph, spec)` 先校验变化，再只评估已解析到目标符号的调用边。`assessments` 逐调用点保存修改前后兼容性与原因；`findings` 仅包含本次变化造成的确定 Direct Impact 或需要人工检查的调用。`direct_impact_count` 只统计修改前兼容、修改后不兼容的调用点；无效变化返回诊断和空结果。

`propagate_indirect_impact(graph, direct_result, max_depth=2)` 只从确定 Direct Finding 出发，沿调用图反向查找最多两层。结果按上游符号去重，并保留通向原始 Direct 调用点的 `CallEdge` 路径；间接结论表示“建议检查”，不表示运行时一定失败。

固定 Demo：`examples/signature_change/`，包含 `utils.py`、`report.py`、`dashboard.py`、`page.py` 和结构化 `change.json`。安装后的命令见“本地安装与 Demo”。

CLI 的 `text` 格式为中文终端报告，`json` 格式包含 `change`、`validation`、`coverage`、`summary`、Direct / Indirect 结果与 `diagnostics`。`change.json` 使用显式的 `before`、`after` 参数数组及 `added_parameter`；每个参数至少提供 `name`、`kind`、`has_default`。无效输入返回非零退出码；部分 Python 文件无法解析时，仍输出其余可分析结果，并标记 `coverage.status=partial`。

报告已包含源码片段、源码 SHA-256、中文解释和明确的不可用状态；ZIP 导入设置上传与解压限制。DeepSeek 可用于证据解释与报告追问，真实模型成功需要有效密钥和调用来源核验。

函数签名报告可追加 `related_tests`：从已有确定影响及最多两层上游路径中，定位符合 pytest 默认命名的模块级测试函数，展示相对文件、候选测试定位、实际调用路径与源码依据。没有测试文件的旧报告保持原样；空候选不代表无需回归测试。服务不会导入或运行上传测试，类方法、fixture、自定义收集配置、更深路径以及 Module / Symbol 领域的测试定位暂未覆盖。详见 [相关测试定位契约](docs/related-tests.md)。


## V1.1 本地模块变更

新增 rename_module / remove_module，限定项目根目录普通 .py 与明确顶层静态导入。Web 目标页切换模块领域后，继续使用 Inspect → Validate → Analyze。只分析拟定变更，不修改源码。参考 [范围、启动与契约](docs/module-changes.md)。
