# Nexus OpenImpact

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

Phase 1.8：本地项目目录、结构化 ChangeSpec、完整分析流水线及中文 / JSON CLI 报告已实现；完整源码片段证据和服务层尚未实现。

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

预期摘要：Direct 1、1-hop 1、2-hop 1、coverage complete。项目版本为 `0.1.0`，运行时没有第三方依赖。运行完整测试时，在已激活的虚拟环境内安装 `pytest` 并执行 `python -m pytest -q`。

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

测试推荐、完整源码片段证据、LLM、源码哈希与资源限额尚未实现。
