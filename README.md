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

Phase 1.4：Repository Scanner、单文件 AST Parser、Symbol Index 与确定性 Call Graph 已实现；变化影响分析尚未实现。

目标：

完成项目基础结构搭建，
并逐步实现 Python 代码变更影响分析能力。

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
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
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
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
uv run --no-project --with pytest python -m pytest -q
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

ChangeSpec、影响分析、LLM、源码哈希与资源限额尚未实现。
