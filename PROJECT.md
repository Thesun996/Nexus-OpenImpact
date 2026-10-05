# Nexus OpenImpact 项目总纲

当前增量范围：函数签名领域支持用户显式源码根目录与普通包静态相对导入。类方法、重导出及运行时包搜索仍不覆盖；Module / Symbol 领域保持根目录普通文件限制。最新依据见 [普通包支持契约](docs/package-imports.md)，后文早期阶段范围为历史基线。

> 更新日期：2026-10-01（Asia/Shanghai）  
> 文档状态：待项目负责人确认。  
> 项目阶段：Core MVP v0.1.0 已完成；Phase 2.5 进行后端契约冻结验收。
> 读者：项目负责人、团队成员、后续 Codex / AI 开发助手、比赛答辩材料整理人员。

本文统一记录产品定位、范围、技术边界、开发约束与当前事实，作为后续开发的项目总纲。本文中的“计划”“建议”“待确认”均不代表功能已实现。功能完成必须有代码、对应测试和可复核结果支撑。

## 文档导航

1. [项目定义与背景](#1-项目定义与背景)
2. [用户、痛点与使用场景](#2-用户痛点与使用场景)
3. [核心价值与产品差异](#3-核心价值与产品差异)
4. [中文与学生适配](#4-中文与学生适配)
5. [Evidence-first 原则](#5-evidence-first-原则)
6. [V1 Scope 与验收边界](#6-v1-scope-与验收边界)
7. [Out of Scope](#7-out-of-scope)
8. [技术架构与模块职责](#8-技术架构与模块职责)
9. [数据模型与影响定义](#9-数据模型与影响定义)
10. [静态分析与 LLM 的职责边界](#10-静态分析与-llm-的职责边界)
11. [Python 支持范围与技术限制](#11-python-支持范围与技术限制)
12. [旧 Nexus 资产复用边界](#12-旧-nexus-资产复用边界)
13. [本地开发与团队协作](#13-本地开发与团队协作)
14. [测试与评测](#14-测试与评测)
15. [两周 V1 路线图](#15-两周-v1-路线图)
16. [V2 与长期扩展方向](#16-v2-与长期扩展方向)
17. [当前项目状态与待确认事项](#17-当前项目状态与待确认事项)
18. [事实维护规则](#18-事实维护规则)

## 1. 项目定义与背景

### 1.1 项目名称与一句话定位

- 项目名称：**Nexus OpenImpact**。
- 简称：**OpenImpact**。
- 一句话定位：**面向学生开发者和开源新贡献者的代码变更影响学习助手。**

当前 V1 的核心问题是：

> “我准备做一个小改动，这个改动会影响项目里的哪些地方？为什么？”

OpenImpact 不是自动修复工具，不是企业安全平台，不是 Copilot 替代品，不是 IDE 替代品。

它帮助用户理解项目、检查改动影响、寻找代码证据和相关测试，由用户决定如何修改代码。

### 1.2 项目背景

团队由 3 名学生组成，准备参加 2026 全球校园人工智能算法精英赛的“AI + 开源”方向。团队此前开发的 Nexus 面向“智能体互联”赛道，已有 React、FastAPI、Python、LLM 调用、独立 Worker、SQLite、任务状态、测试与部署实践。

OpenImpact 是独立的新项目。旧 Nexus 仅作为只读参考工程，按文件或函数挑选通用资产。新项目业务、数据、配置和依赖均须独立。

团队当前希望在约两周内完成范围受控、可以本地演示、可以验证分析结果的 V1。

### 1.3 AI + 开源赛题关系

产品围绕真实开源贡献过程中的“理解修改影响”展开：学生导入一个 Python 开源项目，围绕 Issue 或小型改动提出 ChangeSpec，检查调用关系、受影响位置及相关测试，再自行完成贡献。

AI 的价值体现在中文解释、工程概念教学和证据总结；开源场景提供真实项目、修改任务、验证案例与贡献学习过程。静态分析是判断基础，LLM 是可选的解释增强环节。

项目应支持本地仓库和 ZIP 演示，避免运行能力依赖 GitHub 在线服务。GitHub URL 导入可后续增加。

“AI + 开源”方向与团队参赛意向来自项目交接说明。当前未在本项目中核验该方向的完整正式规则、评分表、开源许可及提交要求，答辩材料不得将产品规划写成已满足赛事全部要求。

## 2. 用户、痛点与使用场景

### 2.1 目标用户

1. 中国计算机、软件工程及相关专业学生。
2. 刚开始参与 GitHub / Gitee 开源项目的贡献者。
3. 会写 Python、掌握基础 Web、CRUD 和 Git，但缺少真实工程修改经验的人。

核心用户通常能编写局部功能，但对模块依赖、调用链、Breaking Change、回归测试及修改边界缺乏把握。

### 2.2 核心痛点

- 找到函数引用后，仍不清楚哪些调用会因本次修改失效。
- 难以判断影响会沿哪些调用路径传播。
- 缺少依据选择需要检查的测试。
- 工具输出过于简略，难以把结果转化为工程知识。
- 面对陌生开源仓库，担心遗漏影响而不敢提交修改。

### 2.3 典型使用场景

**场景一：新增必填参数。** 用户计划把 `format_date(date)` 修改为 `format_date(date, timezone)`。系统发现 `report.py` 中仍有 `format_date(x)`，展示该调用的源码位置，说明新签名要求额外参数，并沿调用链列出上层待检查位置。

**场景二：参与开源 Issue。** 学生导入本地开源项目，选定目标函数与拟修改签名，阅读影响报告、证据和相关测试后，在自己的开发工具中修改代码。

**场景三：团队评审与学习。** 成员使用同一个示例报告解释修改风险，讨论证据和测试选择。报告辅助评审，不替代人工审查与实际回归测试。

依赖升级（如 Pydantic 大版本迁移）属于后续扩展验证场景，当前不承诺实现，也不将产品绑定为某一个依赖的迁移工具。

## 3. 核心价值与产品差异

核心价值包括：具体变化驱动分析、可定位代码证据、有限调用路径传播、中文教学式解释，以及本地可复现的使用方式。

> 专业工具通常告诉开发者“结果”，OpenImpact 还要帮助学生理解“为什么”。

这是一项产品设计目标，不用于概括所有现有工具的能力。不同 IDE、Copilot 产品和企业工具的具体功能会随版本变化，未经核验不作绝对竞争性声明。

| 对比对象 | 常见使用重点 | OpenImpact 的设计重点 |
| --- | --- | --- |
| IDE Find Usages | 定位符号引用 | 结合拟修改签名解释哪些引用不兼容、依据是什么 |
| Copilot 类助手 | 编写、补全与讨论代码 | 围绕明确变更形成可验证影响报告与学习说明 |
| 企业影响分析工具 | 大型工程治理、协作与集成 | 面向学生的小范围 Python 分析、中文解释与本地演示 |

OpenImpact 不追求在所有语言、动态行为或工程规模上覆盖企业工具。产品差异应通过真实案例与用户理解效果展示。

## 4. 中文与学生适配

默认输出使用学生能够理解的中文，保留必要英文术语，并在首次出现时解释。例如：Breaking Change 指可能使原有调用方式不再兼容的接口变化。

一条有效解释至少关联：修改前形式、修改后形式、当前调用、兼容性原因及检查建议。例如：

> 修改后 `format_date` 需要 `date` 和 `timezone` 两个参数。这里仍调用 `format_date(x)`，没有提供 `timezone`，因此与新签名不兼容。请检查该调用应使用哪个时区。

V1 提供中文报告、中文 README 和中英混合源码的正确读取。中文自然语言输入、中文 Changelog 与更丰富的中英混合文档理解逐步扩展；首版 ChangeSpec 使用结构化输入，中文自然语言转 ChangeSpec 不属于首个闭环。

学生模式首先体现为默认输出风格，无需增加独立模式切换或复杂用户画像。

## 5. Evidence-first 原则

1. 重要影响发现必须尽量提供文件位置、代码片段、规则与调用路径。
2. 将证据、规则结论、LLM 解释分开存储，能够追溯解释的来源。
3. 区分“已解析的调用关系”“不确定关系”“未解析调用”，不把猜测混入确定发现。
4. 每次分析绑定输入源码快照标识或文件哈希，避免代码更新后行号与报告失配。
5. 无法可靠判断时输出原因和人工检查提示；未发现影响不等于证明没有影响。
6. LLM 不得虚构文件、行号、调用关系或测试结果。
7. 报告说明扫描覆盖范围、跳过文件、解析错误与未支持情况。

旧 Nexus 的执行证据用于记录源码快照和任务执行来源；OpenImpact 的分析证据用于证明一项变更为何关联具体代码。两者用途需要分别设计。

## 6. V1 Scope 与验收边界

### 6.1 当前优先支持的最小闭环

- Python 项目。
- 模块级函数。
- 可以明确解析的 import 和本地调用。
- 函数签名变化，首先实现新增必填参数。
- Phase 6.2 扩展：删除一个 positional-only、positional-or-keyword 或 keyword-only 参数；拒绝删除 `*args` / `**kwargs`，仍仅评估调用签名兼容性。
- Phase 6.3 扩展：重命名一个 positional-or-keyword 或 keyword-only 参数；拒绝重命名 positional-only、`*args`、`**kwargs`。不分析函数体旧名引用、reflection / inspect.signature、docstring / type comment / external string references。
- Phase 6.4 扩展：移除已有 positional-only、positional-or-keyword 或 keyword-only 参数的默认值，使其必填；拒绝 *args / **kwargs、原本必填的参数及非法签名，保留全部其他签名事实。仅分析调用兼容性，不分析函数体逻辑、默认值本身变化的行为、reflection / inspect.signature、docstring 或 external configuration。
- Direct Impact。
- 1-hop Indirect Impact。
- 2-hop Indirect Impact。
- 文件、行号、代码片段及传播路径证据。
- 中文解释。

首个闭环以本地目录、结构化 ChangeSpec、命令行和 JSON 报告完成。无需模型密钥、网络服务、数据库或前端即可验证核心规则。

### 6.2 两周 V1 产品目标

在最小闭环通过测试后，逐步增加：

- 本地仓库目录与 ZIP 导入；普通目录也可分析，不要求必须含 `.git`。
- 基于明确调用路径的相关测试提示。
- 项目与分析任务的持久化、基础任务状态及报告下载。
- 工程分析 Dashboard：变化摘要、影响列表、证据详情和统计。
- 可选 LLM 中文解释；模型不可用时保留规则报告与模板说明。

Dashboard 展示直接影响、间接影响、相关测试与人工检查项。计数必须说明按发现、符号还是文件统计；测试类别允许与影响类别交叉，不能把所有卡片数字直接相加作为唯一总数。

### 6.3 条件性扩展

以下内容来自初始方向规划，只有核心闭环稳定且工期允许时再逐项纳入：函数重命名、import 路径变化及轻量影响图。删除普通参数与限定范围的参数重命名已获负责人授权，分别纳入 Phase 6.2 和 Phase 6.3；具体范围见上述最小闭环及 `docs/change-types.md`。

类/API 重命名、简单返回值类型变化、第三方依赖 Breaking Change 移入后续候选范围，不构成当前 V1 核心验收承诺。每次扩大范围应先补充支持条件、规则与测试。

## 7. Out of Scope

V1 暂不包含：

- Java、JavaScript、C++ 或通用多语言分析。
- 任意代码语义变化、完整类型推断或任意 Python 动态行为解析。
- 自动修复、自动 Commit、自动 PR、自动 Merge。
- 自动执行未知仓库、导入目标模块、运行陌生项目测试或 Docker 自动执行。
- 企业安全平台、企业 CI/CD、复杂多人权限系统。
- 多 Agent 系统、自由规划调度与旧平台接入。
- GitHub 实时深度集成、在线服务作为演示前提。
- A312 部署、旧服务调整、Windows 到 A312 实时同步。

分析目标中的测试文件属于被读取的源码。开发者运行 OpenImpact 自身的受控测试，与运行用户导入仓库的测试是两种不同操作。

## 8. 技术架构与模块职责

### 8.1 总体流水线

```text
本地目录 / ZIP
    → Repository Scanner
    → AST Parser
    → Symbol Index
    → Call / Import Graph
    → ChangeSpec 校验
    → 签名兼容规则与 Impact Engine
    → Evidence Collection
    → 中文模板说明 / 可选 LLM Explanation
    → Impact Report
```

分析核心使用 Python 标准 AST 和确定性规则。后续服务层采用 FastAPI、SQLite、独立 Worker，前端采用 React + TypeScript。Embedding / Retrieval 暂缓，待明确出现检索需求再评估。

当前本地目录闭环由 `analyze_project(project_path, change_spec)` 顺序编排 Symbol Index（内部调用 Scanner 和 AST Parser）、Call Graph、ChangeSpec 校验、Direct 与 Indirect。`python -m openimpact analyze` 从 JSON 加载结构化 ChangeSpec，输出中文终端报告或机器可读 JSON。固定样例位于 `examples/signature_change/`。ZIP、完整源码片段证据、持久任务和服务层仍待实现。

### 8.2 Repository Scanner

当前已实现的第一步：`RepositoryScanner(project_path).scan()` 递归返回排序后的相对 `Path` 列表，仅收集常规 `.py` 文件，跳过 `.git`、`.venv`、`__pycache__`、`node_modules`、`dist`、`build` 目录及链接条目（含 Windows junction）。不读取或执行源码；输入无效或遍历失败时抛出异常。扫描期间目录应保持稳定，不提供针对并发文件系统替换的隔离保证。

本轮按负责人限定的扫描范围交付。以下内容读取、哈希、资源限额和 ZIP 导入仍属后续计划，尚未实现。

发现可分析的 `.py` 文件，记录相对路径、编码读取结果与内容哈希。排除 `.git`、虚拟环境、依赖安装目录、缓存和构建产物；对文件数、单文件大小与总读取量设置上限。

不跟随符号链接或 Windows junction 越出分析根目录。ZIP 导入需要检查路径穿越、链接条目、文件数量和解压总量，并放入新项目管理的数据目录。具体限额在实现前确定。

### 8.3 AST Parser

当前已实现：`ASTParser(path).parse()` 读取一个 Python 文件，返回 `ParsedModule`。模型位于 `analysis/models.py`，记录模块级函数与参数种类、模块顶层 import 原始形式、调用表达式及实参形态；`FunctionCall` 保留所在文件、模块级调用者及未绑定的 callee 结构路径。读取、编码和语法错误分类为诊断，错误文件不产生部分语法事实。函数列表仅含模块级函数；类方法与嵌套函数体中的调用不进入正式 `calls`。当前没有项目级解析调度器。

读取源码文本并解析 AST，收集函数定义、参数、默认值是否存在、import、调用表达式和源码位置。目标代码只作为数据处理，不使用 `exec`、`eval` 或目标模块导入。

语法错误、编码错误单独记录，不默默丢弃，也不阻止其他有效文件的分析。嵌套函数和类方法即使被 AST 识别，也不代表首版支持它们的完整调用语义。

### 8.4 Symbol Index

当前已实现：`SymbolIndex(project_path).build()` 从 Scanner 与 AST Parser 结果建立项目模块和模块级函数索引。函数 ID 采用相对路径生成的模块名加函数名，例如 `utils.format_date`；Symbol 同时保存相对文件路径与定义事实。明确的绝对 `import` / `from ... import ...` 及别名只在索引内能找到项目模块或函数时绑定。无法确认的绑定保留 `unresolved` 与原因；解析失败文件、重名模块与重名函数不产生猜测性绑定。当前不解析调用目标，不构建调用图。

以项目、模块路径和限定名称标识符号，维护作用域、函数签名和导入别名。避免只按函数名拼接调用边。

当前索引支持模块级函数与明确的绝对 import 绑定；Call Graph 在此基础上处理本模块函数与导入后的明确调用。相对导入、复杂包布局与 `src` 布局仍需逐项实现并测试，不能默认已全面支持。

### 8.5 Call Graph

当前已实现：`CallGraph(SymbolIndex(project_path).build()).build()` 保存静态确定的函数到函数调用边，边记录调用者、被调用者、相对文件、行列、`resolved` 状态及同模块 / from import / module import 的解析依据。模块顶层调用、未知名称、外部或 unresolved import、局部或目标模块名称遮蔽、动态表达式和过长属性链保留为 `unresolved_calls`，不会形成确定边。循环调用可以同时保存两条边；相同调用点去重，不进行传播、深度计算或影响判断。

记录“调用者 → 被调用者”的有向边，并为每条边保存调用位置与解析状态。供后续引擎使用的反向索引尚未实现。

调用图是静态可解析关系的近似，不能保证运行时一定执行该路径。图遍历必须有深度上限、循环处理和发现去重。

### 8.6 ChangeSpec

当前实现使用结构化的 `ChangeSpec`：变化类型、目标 Symbol ID、修改前与修改后的 `FunctionSignature`，以及类型明确的 Operation。正式注册 `AddRequiredParameterOperation`、`RemoveParameterOperation`、`RenameParameterOperation` 和 `MakeParameterRequiredOperation`；旧新增参数格式中的 `AddedParameter` 保留兼容。签名由函数名、参数元组、异步标记和返回注解组成；参数保留种类、默认值有无、默认值表达式及注解。默认值与注解只读取并比较语法表达式，不求值。

```json
{
  "change_type": "add_required_parameter",
  "target_symbol_id": "utils.format_date",
  "before": {
    "name": "format_date",
    "parameters": [{"name": "date", "kind": "positional_or_keyword", "has_default": false}]
  },
  "after": {
    "name": "format_date",
    "parameters": [
      {"name": "date", "kind": "positional_or_keyword", "has_default": false},
      {"name": "timezone", "kind": "positional_or_keyword", "has_default": false}
    ]
  },
  "added_parameter": {"name": "timezone", "kind": "positional_or_keyword", "required": true}
}
```

上述新增示例继续有效。Python 接口为数据类、`ChangeSpec.from_operation()` 和 `validate_change_spec(index, spec)`，JSON 支持 `load_change_spec()` / `change_spec_from_dict()`。共享校验要求目标为已索引的模块级函数、修改前签名与源码一致、修改后符合 Python 参数规则，再委托 Operation 确认只新增一个必填参数、只删除指定普通参数、只重命名指定可按关键字传入的参数或只移除指定现有参数的默认值。删除操作必须保留其余参数和函数元信息，且不能删除 `*args` / `**kwargs`。before / after 始终是兼容性判断的事实来源。失败返回结构化诊断，不进入影响分析；校验不修改目标仓库，源码在建索引后若变化，应重新构建索引。首版暂不依赖 LLM 从自然语言猜测目标。完整删除示例见 `examples/parameter_removal/change.json`。重命名使用 parameter_name / new_parameter_name，保留顺序、kind、默认值、注解及其他签名信息；新名必须合法、非关键字、与旧名不同且无冲突。两个独立示例位于 `examples/parameter_rename_keyword/change.json` 与 `examples/parameter_rename_positional/change.json`，分别验证 1/1/1 与 0/0/0。其 No Impact 只表示调用绑定未新增不兼容，不保证函数体内部引用安全。Phase 6.4 的 make_parameter_required 使用 parameter_name，明确要求参数当前 has_default=true；after 仅置 has_default=false、default_source=null。原默认值 None 对应文本 "None"，与无默认值状态区分。非法默认顺序在构造及校验阶段拒绝，不重排或修改其他参数。独立 Demo 位于 examples/parameter_required_missing 与 examples/parameter_required_explicit，分别为 1/1/1 和 0/0/0、complete。

### 8.7 Impact Engine

当前已实现 Direct 层：先校验 ChangeSpec，再仅对 Call Graph 中已解析且 `callee_symbol_id` 等于目标 Symbol ID 的调用，使用 AST Parser 已提取的位置参数数量、关键字名称及展开标记分别检查修改前、修改后签名。`CallCompatibilityAssessment` 保存两次兼容性状态、原因、规则及调用位置。只有修改前兼容、修改后不兼容才生成确定的 Direct `ImpactFinding`；任一状态需要人工判断时可生成 `manual_review` Finding。两次都兼容、两次都不兼容、或从不兼容变为兼容，均不计入本次 Direct Impact。`direct_impact_count` 仅统计确定的直接影响。含 `*args` 或 `**kwargs` 的调用保守归入人工检查。

当前已实现 1-hop / 2-hop 有限间接传播：仅以确定 Direct Finding 为种子，建立调用边的反向查找表，从 Direct 调用者向上按广度优先遍历，最多两层。每个上游符号只产生一条间接 Finding，层级取最近的确定路径；不同 Direct 种子的证据分别保留，同一种子的多条路径保留一条最短代表路径。证据路径按 `上游调用者 → … → Direct 调用者 → 变更目标` 保存原始 `CallEdge`，末端与 Direct Finding 的文件、行列和符号对应。循环和重复符号通过逐种子 visited 截断。间接状态为 `needs_review`，仅表示位于上游调用路径中，不能断言运行时失败。完整 Evidence Report 尚未实现。

Phase 1.8 报告区分确定 Direct、1-hop、2-hop、人工检查及既有问题，并提供解析错误、未解析调用和 import 摘要。部分文件解析失败时，剩余项目仍可分析，`coverage.status` 标为 `partial`，附文件诊断。目标缺失或 ChangeSpec 校验失败会返回非零退出码；JSON 格式或字段类型错误由 CLI 明确报错。该阶段形成了 `schema_version=1` 的本地 JSON 报告契约，后续 API 沿用此契约。

发现应区分“与新签名确定不兼容”“潜在间接影响”“信息不足”。间接可达性不能直接升级为确定运行失败。

### 8.8 服务层与前端

引擎通过纯函数或明确服务接口供 CLI、API 和 Worker 调用，避免分析规则依赖 HTTP、SQLite 或 UI。

`openimpact.api:app` 已提供健康检查、内置 Demo 分析、上传 ZIP inspect、ChangeSpec 校验和上传项目完整影响分析接口。上传项目经受限 ZIP 导入获得模块与 Symbol Index；服务从当前源码签名构建 ChangeSpec，复用 Core Validator 校验，再对同一临时项目快照调用现有 `analyze_project()` 和 `build_report()`。HTTP 报告的 `project_path` 规范为相对根目录 `.`，partial coverage 附明确说明。接口及错误响应见 `docs/api-contract.md`。任意服务器路径、持久任务、Worker 和前端仍未实现。

持久任务后续处理排队、运行、成功、失败与取消。模型解释失败不应抹掉已经完成的静态报告；静态分析重放与付费模型调用重试分别制定策略。

前端采用工程分析 Dashboard，以影响列表和证据详情为核心。轻量图是可选展示增强，聊天框不作为唯一交互入口。

## 9. 数据模型与影响定义

### 9.1 核心模型

| 模型 | 主要用途 |
| --- | --- |
| Project | 项目标识、导入来源、分析根目录与快照信息 |
| SourceFile | 相对路径、哈希、解析状态与诊断 |
| Symbol / FunctionDefinition | 符号身份、作用域、签名和定义位置 |
| FunctionCall | 调用者、目标、参数形态、位置与解析状态 |
| ImportReference | 导入来源、名称、别名与位置 |
| ChangeSpec | 用户计划的变化 |
| ImpactFinding | 影响位置、类型、规则、确定性、原因和建议 |
| Evidence | 源码定位、片段、哈希与关系证据 |
| AnalysisTask | 分析输入、状态、事件及报告引用 |
| ImpactReport | 发现集合、统计、覆盖范围、限制与解释 |

这是逻辑模型清单。首版不要求每个模型独立建表，也不强制一模型一文件。

### 9.2 Evidence Model

建议证据字段包括：`evidence_id`、`snapshot_id`、相对 `file`、起止行列、`snippet`、`source_hash`、`symbol_id`、`rule_id` 和相关调用边标识。

每项 ImpactFinding 引用证据 ID，并分别保存兼容性结论、关系解析状态、影响类型和依赖路径。严重程度与确定性分开表达，避免用一个“高风险”标签掩盖解析不确定。

LLM 解释只能引用本次报告中已有的证据 ID。证据片段由程序从源文件提取，不让模型生成行号。具体字段名称可在实现时细化，变化须同步测试与文档。

### 9.3 Direct / 1-hop / 2-hop 定义

本项目采用以下计数约定，`graph_distance` 表示到变更目标的调用边数：

| 类型 | graph_distance | 含义 |
| --- | --- | --- |
| Direct Impact | 1 | 直接调用目标的调用点受到本次规则影响 |
| 1-hop Indirect | 2 | 直接受影响调用者的上一层调用位置，需要检查 |
| 2-hop Indirect | 3 | 再上一层调用位置，需要检查 |

```text
page() → dashboard() → report() → format_date()
  │           │           │             │
2-hop       1-hop        Direct        变更目标
```

该示例需要四个函数、三条调用边。仅有 `A → B → C` 且修改 C 时，覆盖 Direct 与 1-hop Indirect。

Direct 仅包含修改前兼容、修改后确定不兼容的调用点；已有的不兼容调用和人工检查项不计入确定 Direct 数量。Indirect 表示需要检查的依赖路径，不承诺运行时必然失败。当前按上游符号去重，保留每个 Direct 种子的一条最短代表路径；最多传播至 2-hop。

### 9.4 相关测试

优先依据可解析调用链识别相关测试，记录证据路径。仅由文件命名、目录邻近或文本检索推测的测试须标记为候选。

报告中出现测试文件不代表已运行测试，也不代表该测试一定失败。

## 10. 静态分析与 LLM 的职责边界

| 工作 | 负责方 | 约束 |
| --- | --- | --- |
| 源文件、符号、import、调用位置 | AST 与索引 | 保存可复核位置 |
| 支持范围内的参数兼容判断 | 确定性规则 | 不交给 LLM 猜测 |
| 有限调用路径传播 | 图遍历 | 明确深度与不确定性 |
| 中文基础原因与建议 | 规则模板 | 无模型也可输出 |
| 教学式解释与报告总结 | 可选 LLM | 依据已有发现与证据 |
| 复杂语义变化理解 | 后续研究 | 当前不作为确定结论来源 |

模型输入应限于解释所需内容，不默认上传整个仓库。首次启用远程模型时应清楚说明会发送哪些源码片段；具体交互与配置方式在接入阶段确定。

模型输出需结构化校验，拒绝不存在的证据引用。仓库注释、README 和源码中的文本都作为待分析数据，不能作为改变系统行为的指令。超时、截断、格式错误或不可用时保留静态报告。

## 11. Python 支持范围与技术限制

### 11.1 首版明确范围

以当前解析器支持的 Python 语法为边界，优先模块级普通函数和明确 import。首先验证新增必填参数，再根据进度加入其他签名变化。

首版规则必须至少区分：缺少新增必填参数、已提供该参数、新增可选参数，以及名称相同但属于不同符号的调用。

### 11.2 暂不可靠支持的动态行为

- `eval`、`exec`、运行时生成代码。
- `importlib`、`__import__` 等动态导入。
- monkey patch、运行时重绑定、无法消除的变量遮蔽。
- `getattr` 等动态属性调用。
- 高阶函数、回调、函数作为值流转后的目标解析。
- 改写签名或调用行为的装饰器。
- 继承、多态、描述符、元类及复杂实例方法派发。
- 通配符导入、复杂 re-export 和运行时修改模块搜索路径。
- 无法静态确定内容的 `*args`、`**kwargs` 展开。
- 复杂条件导入、框架注入、插件发现和跨仓库调用。

遇到这些形式应保留诊断或人工检查提示。系统不执行目标项目来补全动态行为，也不以 LLM 推测替代确定性证据。

### 11.3 最大技术风险

最大风险是调用目标解析错误，导致错误调用边进一步污染影响路径和中文解释。应优先控制误报、保存解析状态、测试同名符号与遮蔽边界，并公开支持范围。

其他限制包括：静态可达不等于运行时可达；仓库外部调用者不可见；新版本语法可能超出解析器能力；过大的仓库可能触发资源限额；类型注解不保证实际返回值；源码变动会使旧报告过期。

## 12. 旧 Nexus 资产复用边界

### 12.1 审计来源与结论

旧项目只读路径：`E:\编译\2026人工智能算法精英赛`。

Phase 0 检查了前后端结构、配置、模型客户端、任务契约、Worker、SQLite、证据模块及测试代码。审计没有执行旧测试或构建，没有复验服务器运行状态；旧文档历史测试数字不作为此次验收结果。

核心结论：通用机制有复用价值，OpenImpact 分析核心需要新建。当前旧 Store 同时承载 SQL 和任务业务，前端 App 较集中，尚无可整套复制的独立 Repository / Service 层或组件库。

### 12.2 A：可以直接复制的资产

| 旧资产 | 复用条件 |
| --- | --- |
| `frontend/src/api.ts` | 新 API 沿用 `/api/v1` 与兼容错误格式 |
| `frontend/tsconfig.json` | 沿用 React / TypeScript 工程结构 |
| `frontend/src/main.tsx` | 保留对应挂载入口与文件结构 |
| pytest、Ruff 配置片段 | 重写项目名称、路径和依赖 |
| 时间、错误和终态判断等小函数 | 按函数提取并适配命名 |

### 12.3 B：需要重构后复用

| 旧资产 | 保留价值 | 必须调整 |
| --- | --- | --- |
| DeepSeek Client | 异步、超时、取消、脱敏、用量 | 独立配置、结构化解释校验、降级 |
| SQLite Store | WAL、事务、幂等、领取与迟到结果保护 | 新领域模型、移除旧库兼容与文本任务字段 |
| Worker | 独立执行、续租、停止与任务状态 | 移除 Agent 选择和旧 Transport，接入分析流水线 |
| FastAPI 工厂 | 生命周期、任务、SSE、下载、健康检查 | 新项目和报告接口，移除 Agent 接口 |
| Pydantic 契约与配置 | 校验、SecretStr、状态与错误 | 新模型、独立环境前缀和数据路径 |
| 执行证据模块 | 哈希、快照、路径边界检查 | 清除旧平台白名单，与分析证据分离 |
| React App | 状态、URL 恢复、事件与异常处理 | 拆组件，重建 Dashboard |
| 行为测试 | 并发、超时、取消、脱敏、持久化经验 | 替换输入、领域模型和断言 |
| 开发启动脚本 | 端口、子进程、日志与清理 | 独立模块、端口、目录 |

旧项目的 `Store.heartbeat()` 用于本地 Worker 存活检查，可重构复用；它与比赛平台心跳上报分别处理。

### 12.4 C：不应该迁移

- Research Pack、Paper Agent、摘要分析业务及其业务测试。
- 本地 Agent Registry、AgentCard、能力审核选择、AgentTransport、旧 fixture 文本流程。
- 旧业务任务类型、前端模式与旧结果模型。
- 旧数据库、历史任务、日志、证据包、虚拟环境、依赖安装目录及构建缓存。
- 旧 README、AGENTS.md 与旧赛道规则整份复制。

可以参考 Research Pack 中“证据必须存在于输入”和“结构化结果校验”的原则，不能迁入其业务逻辑。

### 12.5 D：旧比赛平台内容必须排除

- 整个 `integrations/aip`，包括 Leader / Partner、Inbox 和平台协议实验。
- AIC、ACS、Dingdang、Discovery、RabbitMQ、AMP、HeartbeatEmitter。
- Fluent Bit、Kafka heartbeat、平台 allowlist、平台专用接口。
- `deploy/amp`、平台诊断脚本、Inbox 专用 systemd 配置。
- 证书、私钥、Token、密码、平台 secrets、旧 `.env` 和机器私有配置。
- 执行证据模块中收集 `integrations/aip` 的旧白名单。

这里的“排除”仅作用于新项目迁移范围，绝不删除或修改旧项目文件。最终部署时可参考 systemd、Release / Rollback 的经验，但需要独立编写新模板，不复制旧生产配置。

## 13. 本地开发与团队协作

### 13.1 路径与环境约束

- 当前维护文档：`E:\编译\2026人工智能算法精英赛新赛道\Nexus-OpenImpact\PROJECT.md`。上级目录中的早期草案不再同步维护。
- 当前代码目录：`E:\编译\2026人工智能算法精英赛新赛道\Nexus-OpenImpact`，由负责人本轮指定。
- 旧 Nexus：只允许阅读、分析和经筛选复制通用代码，禁止写入、删除或修改部署配置。
- A312：最终部署目标，当前禁止操作。

开发流程固定为：

```text
Windows 本地开发 → 本地测试 → GitHub 版本管理
→ 项目基本完成 → 独立确认最终部署 → A312
```

禁止停止旧服务、修改旧服务器部署或建立 Windows → A312 实时同步。

### 13.2 推荐目录布局

```text
Nexus-OpenImpact/
├── PROJECT.md
├── README.md
├── AGENTS.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── src/openimpact/
│   ├── cli.py
│   ├── repository/       # scanner、后续 importer
│   ├── analysis/         # models、parser、index、graph、rules、engine、evidence
│   ├── reporting/        # JSON 与中文报告
│   ├── providers/        # 后续模型解释
│   ├── persistence/      # 后续 SQLite
│   ├── api/              # 后续 FastAPI
│   └── worker.py         # 后续后台任务
├── examples/
├── tests/
│   └── fixtures/
├── frontend/             # 引擎验收后加入
├── docs/
└── var/                  # Git 忽略
```

这是建议结构，不代表已经创建。按阶段只建立实际使用的模块，避免提前堆叠空目录与抽象层。

### 13.3 Git / GitHub 协作原则

- 新项目独立仓库；按小任务建分支，提交应有明确验收条件。
- 通过 PR 描述变化、共享契约、实际测试结果和限制，合并前由另一名成员复核。
- 模型、API 和前端类型变化一起更新，避免成员分别维护互相冲突的字段。
- 不提交 `.env`、证书、密钥、数据库、日志、缓存与个人材料。
- 保留复用代码来源和许可证信息；仓库许可证与公开时间另行确定。
- GitHub 推送或合并不触发 A312 自动部署。
- 旧项目未发现可直接复用的 `.github` 自动验证配置；新项目需要时另建。

三人角色划分尚未正式确定。可按分析核心、API/持久化、前端/评测分工，但先共同跑通最小闭环并确认共享契约。

## 14. 测试与评测

### 14.1 测试策略

使用 OpenImpact 自身的受控 fixture 验证分析结果，不执行导入仓库代码。

核心行为测试覆盖：

1. 新增必填参数导致明确调用不兼容。
2. 已正确提供参数、新增可选参数等不应误报情形。
3. 位置与关键字参数、仅限位置与仅限关键字参数的支持边界。
4. 同名函数、明确别名、遮蔽与无法解析调用。
5. Direct、1-hop、2-hop、循环调用、多路径和深度上限。
6. 证据行号、片段、文件哈希与源码一致。
7. 语法错误、编码问题、链接路径、超限文件与 ZIP 边界。
8. 相关测试提示有依据，未执行测试的状态表述准确。

接入服务后增加持久化、并发领取、取消和迟到结果保护测试；接入模型后使用模拟网络测试超时、脱敏、结构校验与降级。真实模型验收单独记录环境、用量和结果。

每个小阶段通过对应行为测试后再扩大范围，不用测试数量代替分析质量。

### 14.2 评测思路

先建立人工可核验的小型 Golden Set，再引入具有明确变更意图的真实开源 commit / migration PR。记录项目版本、变更类型、标准影响位置、证据与限制。

真实 PR 的修改文件只作为参考：其中可能包含顺带重构，也可能遗漏受影响位置，需人工审核后形成标准答案。

| 指标 | 说明 |
| --- | --- |
| Direct Impact Precision | 报出的直接影响中，正确发现的比例 |
| Direct Impact Recall | 已标注直接影响中，被系统找到的比例 |
| File Recall@K | 若输出排序列表，前 K 个文件覆盖标准影响文件的比例 |
| False Positive Rate | 需先定义有限负样本集合，再计算误报比例 |
| Evidence Accuracy | 文件、位置、片段与规则依据正确的比例 |

指标需明确按调用点、符号还是文件统计，报告样本数与未支持情况。没有定义负样本集合时不直接发布 False Positive Rate。

baseline 使用文本搜索与类似 Find Usages 的直接引用扫描。各方法在相同样本、相同输入下比较；中文解释质量单独评审证据忠实度、可理解性和建议具体程度，不编造 AI 综合分。

## 15. 两周 V1 路线图

以下是建议工作节奏，以 PROJECT.md 获确认并正式开始开发之日为起点，不构成已承诺的日历完成日期。

| 时段 | 目标 | 验收产物 |
| --- | --- | --- |
| 第 1—2 天 | 独立工程、scanner、AST、最小索引 | 本地示例可解析，目标代码无执行 |
| 第 3—4 天 | ChangeSpec、新增必填参数规则、证据 | Direct Demo 与正反用例通过 |
| 第 5—6 天 | 明确 import、有限传播、诊断 | 四函数调用链覆盖三种影响类型 |
| 第 7 天 | 首个引擎闭环整理 | CLI、JSON、中文报告与边界说明 |
| 第 8—9 天 | ZIP、任务接口与持久化 | 本地导入到报告查询流程可复现 |
| 第 10—11 天 | Dashboard 与可选模型解释 | 列表、证据、统计及无模型降级 |
| 第 12—13 天 | Golden Set、baseline、回归 | 可核验指标与失败案例 |
| 第 14 天 | 演示、README、答辩素材 | 从干净本地环境复现核心场景 |

时间不足时优先收缩条件性扩展和图展示，保留确定性分析、代码证据、中文解释和本地演示闭环。发现工期偏差应更新范围与路线图，不能将未实现事项标为完成。

## 16. V2 与长期扩展方向

候选方向包括：更多签名变化、函数及 import 重命名、有限类方法分析、可靠条件下的返回类型变化、依赖 Breaking Change、GitHub URL 导入、中文自然语言 ChangeSpec、中文 Changelog、交互影响图、检索辅助和更丰富真实项目评测。

Pydantic 大版本迁移可作为验证案例，规则设计应能表达一般变化，避免硬编码整个产品。

后续方向按用户价值、证据可验证性、误报率和实现成本筛选。自动修复、企业安全、多语言及自动 PR 不属于已确认长期承诺，若要纳入需单独重新定义范围。

## 17. 当前项目状态与待确认事项

### 17.1 当前事实

| 项目 | 状态 |
| --- | --- |
| 初始项目交接说明 | 已完整阅读 |
| Phase 0 旧资产审计 | 已完成只读源码与文档审计 |
| PROJECT.md | 本文为待负责人确认的总纲草案 |
| 独立代码目录 | 已存在，采用负责人指定的当前项目路径 |
| Phase 1 分析引擎 | Scanner、AST、Symbol Index、Call Graph、ChangeSpec、Direct / 1-hop / 2-hop、流水线和 CLI 报告已实现；完整源码片段证据尚未实现 |
| Core MVP v0.1 工程验收 | 版本 `0.1.0`；项目虚拟环境中 `pip install -e .` 成功；清除 `PYTHONPATH` 后导入、中文 / JSON Demo 均成功，摘要为 Direct 1、1-hop 1、2-hop 1、coverage complete |
| 新项目测试与评测 | Phase 2.5 完整 pytest：155 passed、1 skipped（Windows 符号链接权限）；三步真实 HTTP 与 CLI 回归已验收，真实项目评测尚未实施 |
| 新项目前端、API、Worker、数据库 | Demo、ZIP inspect、ChangeSpec 校验及用户项目影响分析 API 已实现；前端、Worker、数据库尚未实现 |
| 新 GitHub 仓库 | 尚未创建或核验 |
| A312 | 本轮及当前开发阶段不操作 |

### 17.2 待确认或需在实现前细化的事项

1. **代码目录与文档归属（已明确）：** 采用负责人指定的 `E:\编译\2026人工智能算法精英赛新赛道\Nexus-OpenImpact`，维护该仓库中的本文。
2. **两周验收：** 本文区分核心闭环、产品目标和条件性扩展；需确认最终优先级与起始日期。
3. **Python 与项目布局：** 具体支持的语法版本、源码根目录、相对导入及包布局需要以测试明确。
4. **资源与输出契约：** 文件/ZIP 限额、路径条数、统计口径、严重程度与去重方式在实现前细化。
5. **模型使用：** 默认关闭还是由用户首次启用、发送片段的告知方式、预算与模型配置待接入时确定。
6. **团队与开源：** 仓库归属、成员分工、许可证、公开时间和赛事正式提交要求尚待明确。

后续助手不得将这些问题视为已获得默认批准。与首个本地静态闭环无关的决定可延后，不必提前引入实现。

## 18. 事实维护规则

- 用户最新明确指令优先；本文提供项目范围基准，详细接口与架构决定可放入后续 docs 文档。
- 范围、路径、数据契约或支持边界变化时，同步更新本文相应部分。
- 已实现结论必须注明对应测试或验收记录，历史结果不能替代当前验证。
- 规划与实际状态分开记录，失败案例和已知限制不得隐去。
- 引用旧 Nexus 的资产时保留来源，不继承旧赛道目标和平台义务。
- 负责人已授权 Phase 2.2 的 Python 项目 ZIP 导入检查；本轮不提交 Git，不扩展分析算法或 Change 类型，不实现上传项目的影响分析、LLM、前端或持久化，不操作 A312。
- ZIP inspect 仅调用现有 Scanner、AST Parser 和 Symbol Index。上传 5 MiB、multipart 请求体 5 MiB + 64 KiB、256 条目、128 文件、单文件解压 1 MiB、总解压 10 MiB、压缩比 200；逐条校验路径与条目类型，分块复核解压字节，临时隔离目录在请求结束后清理。单层外包装目录按规则剥离，Python 包根目录保留。接口字段、错误码与覆盖语义见 `docs/api-contract.md`。
- 负责人已授权 Phase 2.3 的 ChangeSpec 配置与校验 API；沿用同一 ZIP 校验及临时索引流程，从目标 Symbol 读取当前签名，新增必填参数后调用现有 Core Validator。可选预期指纹不符时拒绝；本轮不提交 Git，不修改 Core 分析规则或执行影响传播。
- 负责人已授权 Phase 2.4 的用户项目完整影响分析 API；复用上述 ZIP 与 ChangeSpec 流程，在请求专用临时目录中调用现有 Core 分析和报告能力。部分覆盖时不把零条影响表述为全项目确定无影响；本轮不提交 Git，不新增分析规则或 Change 类型。
- 负责人已授权 Phase 2.5 后端契约冻结验收；`docs/api-contract.md` 记录三个正式业务接口，`docs/frontend-handoff.md` 与 `docs/api-samples/` 供前端开发交接。上传项目在每次请求结束后清理，指纹只用于核对本次 ZIP 字节，不提供项目持久化或服务器路径输入。本轮不新增业务功能或分析规则，不提交 Git。

### 变更记录

| 日期 | 变化 | 状态 |
| --- | --- | --- |
| 2026-10-01 | 根据项目交接说明、Phase 0 审计和本轮范围要求建立总纲 | 待负责人确认 |
| 2026-10-01 | 按负责人指定目录进入 Phase 1，仅实现 Repository Scanner；验收命令见 README，测试位于 tests/repository/test_scanner.py | 6 项通过、1 项因权限跳过；待人工代码检查 |
| 2026-10-01 | 实现单文件 AST Parser 和语法事实模型；验收命令见 README，测试位于 tests/analysis/test_ast_parser.py | 完整 pytest 18 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 审核修订：补充 callee 结构路径、调用者和边界测试 | 完整 pytest 22 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 实现项目级 Symbol Index 和明确 import 绑定，保留 unresolved 原因 | 完整 pytest 32 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 实现确定性 Call Graph、未解析调用诊断及作用域遮蔽边界 | 完整 pytest 45 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 实现结构化 ChangeSpec 与新增必填参数校验，保留明确诊断；测试位于 tests/analysis/test_change_spec.py | 完整 pytest 60 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 实现新增必填参数的直接调用兼容性判断；测试位于 tests/analysis/test_direct_impact.py | 完整 pytest 75 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 审核修订：分别判断修改前后兼容性，区分确定 Direct、既有问题、无影响、兼容性改善及人工检查 | 完整 pytest 77 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 实现以确定 Direct 为种子的 1-hop / 2-hop 反向传播、路径证据、循环与多路径去重；测试位于 tests/analysis/test_indirect_impact.py | 完整 pytest 87 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | 建立本地结构化 ChangeSpec 加载、流水线、CLI、JSON / 中文报告及固定 Demo；测试位于 tests/analysis/test_pipeline_cli.py | 完整 pytest 95 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | Core MVP v0.1 冻结前验收：补充 `src` 布局的 editable packaging，在项目虚拟环境中无 `PYTHONPATH` 复现 Demo；README 改为安装后直接运行 | 完整 pytest 95 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | Phase 2.1：内置 Demo 的 FastAPI 服务、接口契约和 HTTP 测试；直接返回既有 Core JSON Report | 完整 pytest 100 passed、1 skipped；待审核，未提交 Git |
| 2026-10-01 | Phase 2.2：安全 ZIP 导入检查、模块/符号/参数/诊断 JSON、根目录识别及接口文档；提交前补充重复/归一化冲突与拒绝后清理测试 | 完整 pytest 128 passed、1 skipped；真实 HTTP 正常 ZIP 200、危险路径 400、原 Demo 200；待审核，未提交 Git |
| 2026-10-01 | Phase 2.3：简化 HTTP 变更配置、源签名读取、ChangeSpec 构建与 Core Validator 校验；复用 ZIP 安全导入与指纹核对 | 完整 pytest 143 passed、1 skipped；真实 HTTP 成功 200、指纹不符 409、无效 ZIP 400；待审核，未提交 Git |
| 2026-10-01 | Phase 2.4：上传 ZIP 的完整影响分析 API、相对路径报告与 partial coverage 提示；复用已冻结 Core 能力 | 完整 pytest 151 passed、1 skipped；真实 HTTP Demo Direct / 1-hop / 2-hop 各 1、coverage complete，指纹不符 409、无效 ZIP 400；待审核，未提交 Git |
| 2026-10-01 | Phase 2.5：三步 HTTP 工作流、安全输出核查、接口契约与前端交接样例 | 完整 pytest 155 passed、1 skipped；真实 HTTP 三步均 200，Direct / 1-hop / 2-hop 各 1、coverage complete，改 ZIP 后旧指纹 409；CLI 中文 / JSON 与固定 Demo API 通过；待审核，未提交 Git |


## V1.1 当前实现补充

在四种函数签名变更基础上，新增根目录普通模块重命名与拟定删除的静态导入影响分析。Function 核心与报告 v1 保留；Module 有独立事实、虚拟布局、依赖图、证据和领域报告 v1，详见 [模块能力边界](docs/module-changes.md)。上游传播只建议检查，complete 仅限定 project_root_static；包、相对/条件/动态机制保守诊断。没有真实文件改动、外部模型判断或独立模块 Benchmark 准确率。

## V1.2 当前实现补充

负责人授权增加第三领域 Symbol：唯一公开模块级简单变量/常量定义的拟重命名或删除，包含静态引用、虚拟 Before/After 绑定、真实源码证据、独立领域报告及三领域 Web 工作流。只支持根目录普通模块、可证明的简单定义和明确读取；局部遮蔽与同名隔离，动态写入/复杂作用域/包/重导出保守诊断。确定 Direct 证明新出现的项目静态引用断裂，上游模块需要检查；没有执行或修改用户源码。原六种变更报告逐字段回归，契约见 [符号能力边界](docs/symbol-changes.md)。完整验收及 Git 状态见 [两轮交付报告](docs/v1.1-v1.2-delivery.md)，独立 Benchmark 仍待人工成果，未报告准确率。
