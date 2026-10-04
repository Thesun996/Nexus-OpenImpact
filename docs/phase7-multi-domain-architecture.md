# Phase 7.0：Multi-Domain Change 架构审计

日期：2026-10-04。基线：`integration/multi-change-web@1cd8480a7e37049956060556b912abe963f89486`。

**本轮仅为源码审计和待审核设计。rename_module、remove_module、模块依赖图及以下新数据契约均未实现。** 当前正式能力仍为四种函数参数变化。本文不修改生产 Core、API、React 或现有 Signature Changes。

建议保留现有 Function/Signature 流水线，在入口增加轻量 Change Domain 分发；Module 使用独立的模块布局、Import 引用解析和证据。Symbol/Structure 域暂不注册业务 Operation。

## 1. Git 与基线保护

| 工作树 / 分支 | HEAD | 本轮开始状态 |
| --- | --- | --- |
| Nexus-OpenImpact / main | 3a5a582 | 干净 |
| Nexus-OpenImpact-change-types / feature/change-types | 327248e | 干净 |
| Nexus-OpenImpact-ui-redesign / feature/ui-redesign | f34d243 | 干净 |
| Nexus-OpenImpact-frontend / integration/frontend-react | 9ab08fc | 干净 |
| Nexus-OpenImpact-multi-change-web / integration/multi-change-web | 1cd8480 | 三份 Phase 6.6 文档未提交，ahead origin/main 6 |

已有未提交内容为 `docs/evaluation-contract.md`、`docs/phase6.6-evaluation-readiness.md`、`docs/phase6.6-evaluation-readiness.json`。这些文件原样保留，Phase 7 不将其覆盖、丢弃或混入新的业务提交。

本轮只新增本文，不创建分支，不暂存、commit、push、merge 或修改 main。后续建议：先由负责人分别审核 Phase 6.6 文档和本文，建立精确范围的 Checkpoint；工作区干净后，从包含 `1cd8480` 的最新集成 Checkpoint 创建 `feature/multi-domain-changes` 独立工作树。旧 main 尚未包含全部四类型 Web 成果，不能作为直接起点。

下面命令仅为后续操作建议，本轮未执行；目录或分支存在时停止核查，不强制覆盖：

```text
git worktree add -b feature/multi-domain-changes ../Nexus-OpenImpact-multi-domain-changes integration/multi-change-web
```

## 2. 真实 Core 审计

### 2.1 已实现组件与边界

| 组件与源码依据 | 当前事实 | 复用边界 |
| --- | --- | --- |
| [RepositoryScanner](../src/openimpact/repository/scanner.py#L16) | 扫描普通 `.py`；排除六类目录及链接/junction；返回相对路径 | 可直接复用发现能力和路径约束；没有 Python 安装布局解析 |
| [ASTParser](../src/openimpact/analysis/ast_parser.py#L177) | 提取模块级普通/async 函数、直接顶层 import、限定作用域 call、名称遮蔽事实 | import 语法事实可复用；完整引用/作用域与导入位置元数据不足 |
| [语法模型](../src/openimpact/analysis/models.py#L40) | ImportReference 有 type/module/name/alias/level/起止行；FunctionCall 有 caller、callee 结构和实参形态 | 不能把 FunctionCall 当作 ImportReference；函数对象等非调用引用尚无完整索引 |
| [SymbolIndex](../src/openimpact/analysis/symbol_index.py#L47) | `modules` 映射 module→文件；`symbols` 仅为模块级函数；保存解析失败和歧义 | 可作为模块目录和已有定义事实；模块没有独立描述模型 |
| [Import 绑定](../src/openimpact/analysis/symbol_index.py#L126) | `_module_reason()` / `_bind()` 位于 SymbolIndex 内，没有独立 ImportResolver 文件 | 可提取/适配其项目内查找规则；本地名称绑定表不能代替完整 Import 引用清单 |
| [CallGraph](../src/openimpact/analysis/call_graph.py#L14) | function caller→callee；每边有真实 call site；只建立确定调用边 | 无 ModuleDependencyGraph；顶层调用不伪造成函数 caller |
| [ChangeSpec / Operation](../src/openimpact/analysis/change_spec.py#L470) | before/after 固定 FunctionSignature；四种 Operation 仅改变参数 | 继续完整保留；模块变化不能填写虚构签名 |
| [Direct Engine](../src/openimpact/analysis/direct_impact.py#L78) | 绑定实参与 canonical before/after；只有 compatible→incompatible 为确定 Direct | 可复用状态转移原则；参数绑定算法不适用于 Import |
| [Indirect Engine](../src/openimpact/analysis/indirect_impact.py#L65) | 从确定调用种子反向 BFS，最多两层，逐 seed 最短路径、去重 | 可复用策略；现有模型与 `_direct_edge()` 强依赖函数 CallEdge |
| [EvidenceBuilder](../src/openimpact/reporting/evidence.py#L59) | 接收函数 Direct/Indirect；安全读源码、相对路径、整文件 SHA-256、失败 diagnostic | 读取与失败降级规则可复用；调用路径/target_symbol 需要独立模块适配 |
| [Report](../src/openimpact/analysis/report.py#L144) | schema_version=1；Direct 是调用兼容性，Indirect 是上游函数 | 当前报告没有模块 Direct/Indirect 契约，不能塞入异构 Finding |
| [API Change Builder](../src/openimpact/api_change.py#L78) | 仅查 `index.symbols`，从 FunctionDefinition 读取签名 | ZIP、指纹、清理和线程池可复用；目标与 builder 必须按域区分 |

### 2.2 模块识别是否完整

当前能发现限定范围内的 Python 源文件，不能宣称完整模拟 Python 模块加载：

- `utils.py → utils`，`pkg/utils.py → pkg.utils`，`pkg/__init__.py → pkg`；根 `__init__.py → __init__`。
- `src/pkg/utils.py → src.pkg.utils`，没有自动识别安装后的 `pkg.utils`；不读取 pyproject 的 package_dir、source roots 或运行时 sys.path。
- `pkg.py` 与 `pkg/__init__.py` 都映射为 pkg，会进入 ambiguous_modules，不猜唯一身份。
- 解析失败文件仍可出现在 modules，但不提供函数定义及可绑定的模块结果；模块是否被发现和是否能可靠解析需分开。
- 扩展模块、`.pyi`、安装依赖、完整 namespace package 和复杂包初始化均未完整覆盖。
- ZIP inspect 的 `source_root` 表示剥离的外包装目录，[相关输出](../src/openimpact/repository/zip_inspector.py#L212)不能当作已确认的 Python import root。

函数 ID `module.function_name` 只在同一快照内稳定。改名或移动模块会改变函数 ID，没有跨版本实体 ID 或 Git rename 推断。未来 Operation 必须显式记录旧→新身份映射。

### 2.3 源码位置现状

模块有实际相对文件路径，函数有定义起止行，调用有真实行列及源码表达式。ImportReference 有起止行、成员和别名，**没有 column/end-column、完整 statement ID、语句片段或 scope 字段**。

`from utils import f, g` 会产生两个 ImportReference；同一行多个 import 也可能共享行号。因此 `(file,line)` 不能作为唯一身份，缺失列号不能补成 0。模块声明本身没有一个类似函数定义的 AST 节点；模块 Evidence 应锚定文件及真实 import 语句。

## 3. 当前 Import 能力矩阵

以下结论来自 [AST 收集](../src/openimpact/analysis/ast_parser.py#L223)、[绑定规则](../src/openimpact/analysis/symbol_index.py#L135)及现有测试。

| 形式 | 当前语法事实 / 绑定 | 调用或模块分析注意 |
| --- | --- | --- |
| `import utils` | 支持，项目内唯一且解析成功时绑定模块 utils | 可作为 flat 模块引用基础 |
| `import utils as u` | 支持，local u→utils | alias 改变本地名称，不改变声明的目标模块 |
| `from utils import format_date` | 已定义模块级函数存在时支持 | 保存目标函数及所属模块 utils |
| `from utils import format_date as fd` | 支持 | fd 不应参与按文本猜模块身份 |
| `from pkg import helpers as h` | pkg 及 pkg.helpers 明确存在时可绑定子模块 | 包初始化语义仍未模拟 |
| `import pkg.helpers as h` | 可绑定完整模块 pkg.helpers | 不能因此宣称完整 namespace/package 支持 |
| `import pkg.helpers` | 完整子模块及根 pkg 均需存在；local 绑定目标为 pkg | 完整声明依赖仍是 pkg.helpers，不能只读 binding.target_module |
| `pkg.helpers.f()` | callee 结构可保存，但三段链不进入确定函数图 | `h.f()` 两段别名调用可按现有规则解析 |
| `from .utils import f` / `from .. import x` | AST 保存 level；绑定为 relative_import_unsupported | 当前不支持相对解析 |
| `from utils import *` | 记录事实；wildcard_import_unsupported | 不展开名称、不推测导出 |
| re-export / `__all__` | 不追踪导出表 | compat 中导入 f 不等于索引存在 compat.f 定义 |
| 常量、类等 from-import 成员 | 函数/子模块之外没有完整 Symbol 注册 | 不能从 name_not_in_project_module 推断运行时不存在成员 |
| 函数内、class、条件/try 块中的 import | 未进入直接顶层 imports 清单 | 部分仅作为名称遮蔽记录，没有完整 Import Evidence |
| `importlib.import_module()` / `__import__()` | 无动态 ImportReference 和字符串目标绑定 | 不能升级为确定模块影响 |
| 外部库或缺失模块 | 均可得到 module_not_in_project | 不能仅凭该诊断区分外部已安装库和真实缺失模块 |

同名隔离使用完整 module ID，如 `a.utils` 和 `b.utils`，不按 basename 匹配。重复本地名会覆盖 `bindings[module][local_name]` 并标 unresolved；原始 `ParsedModule.imports` 保留各条语法事实。新的引用分析需逐 occurrence 保存解析结果。

现有测试依据：[四类绑定与包路径](../tests/analysis/test_symbol_index.py#L46)、[relative/wildcard/解析失败/歧义](../tests/analysis/test_symbol_index.py#L93)、[局部 import 边界](../tests/analysis/test_ast_parser.py#L90)、[动态目标及遮蔽](../tests/analysis/test_call_graph.py#L130)。

## 4. Change Domain 最小扩展方案

### 4.1 方案比较与推荐

| 方案 | 评估 |
| --- | --- |
| 在旧 ChangeSpec 中增加 Module Operation，但仍填写 FunctionSignature | 不采用，目标和兼容性事实失真 |
| 将旧 ChangeSpec 全部泛型化，before/after 改为任意对象 | 不采用，扩大冻结函数流程的修改面，也削弱类型校验 |
| 保留旧 ChangeSpec，增加 ModuleChangeSpec 和轻量域分发 | **推荐**；只在明确入口选择域内 validator/pipeline/report |

建议使用少量不可变模型与静态 discriminator 映射，不建立插件发现、动态注册器、Factory 层级或通用 DSL：

```text
Function domain
  现有 ChangeSpec + 四种 Operation
  before/after FunctionSignature
  现有 analyze_project → Direct/Indirect → build_report

Module domain（待实现）
  ModuleChangeSpec + RenameModuleOperation / 后续 RemoveModuleOperation
  before 模块身份/布局 + after 虚拟模块目录
  ImportReferenceAssessment → ImportDirect → Module Indirect → Module Report

Symbol / Structure domain（后续设计，不注册）
  旧/新定义身份 + Reference Index
  裸函数引用、回调、类/变量等需逐项建设，不能承诺已覆盖
```

旧输入缺少 change_domain 时仍进入 Function，保留四类 change_type、旧 add 缺省和旧 before/after JSON。域/类型不匹配、未知域或尚未注册的 Symbol Operation 明确拒绝。当前生产 API 仍不接受下述多域字段。

### 4.2 Module 域的最小事实模型

| 建议模型 | 核心事实 |
| --- | --- |
| ModuleDescriptor | 快照内 module_id、实际 source_file/hash、模块种类、解析状态、分析根及不可选原因 |
| ImportReferenceFact | 原始声明路径/type/member/alias/level、source_module、真实 span、scope、statement/alias ordinal、稳定 reference_id |
| ImportResolution | 声明依赖模块与 local binding 分开；resolved_project/unresolved、依据与原因，保留每个 occurrence |
| ModuleChangeSpec | target_module_id、before descriptor、after layout projection、类型明确的 operation；无函数签名 |
| ImportReferenceAssessment | reference_id、before/after 项目解析结果、effect、reason、来源和目标身份映射 |
| ModuleImportFinding / ModuleIndirectFinding | 导入引用 Direct 或上游模块检查项；独立统计单位及证据路径 |

ModuleDescriptor 可由现有 SymbolIndex 生成视图，避免重复 Scanner/AST。Import 的项目查找规则应成为可复用纯函数/适配器；保留声明项账本与现有局部名绑定表各自职责。`import pkg.sub` 的 declared dependency 和 bound root 必须分别保存。

ImportReferenceFact 建议身份为 `(snapshot_id, source_file, statement_ordinal, alias_ordinal)`，不依赖可冲突的本地名。后续经批准补真实列号、scope 和 source segment；未提供时为 null/行范围，不伪造精确位置。

Module before/after 是对同一源码快照的**只读虚拟目录投影**：rename 显式删除旧目录项、增加新名称映射；remove 删除目标项。实际文件和 import 语句不修改，Evidence 仍读取真实 before 源码。旧→新映射由用户意图提供，不用同名或源码相似度猜测。

## 5. Rename Module：最小可靠支持范围

### 5.1 首版边界

建议首版只允许项目根下的单个普通 `.py` 模块，如 utils.py→formatting.py：

- 目标在当前快照内唯一、可解析，basename 是可明确表示的模块名；拒绝 `__init__.py`、特殊 `__main__`、包目录整体改名和 source-root 移动。
- 首版的 flat/root 限制同时适用于变更目标与确定依赖图的参与模块：均为项目根下普通 `.py`。子目录文件仍由 Scanner 发现、保留语法事实；其中的导入属于首版未覆盖范围，记录位置和原因并标明 partial，不静默丢弃，也不纳入确定传播路径。以后扩展普通嵌套模块时再确认包和解析根规则。
- 新名是合法 Python identifier，非 keyword，不包含路径或点号；不与现有文件、目录/包、模块 ID 冲突。
- 目标 basename 和新名必须已经是 NFKC 规范形式；例如 `ｆｏｏ.py` 与 AST 中归一化为 `foo` 的声明无法直接对应，应明确拒绝。规范形式中的中文等合法名称可保留。对仅大小写变化、casefold/NFKC 等价冲突也保守拒绝，避免跨平台身份差异；不偷偷规范化物理路径或选择另一个模块。
- 仅处理可确定的直接模块顶层绝对 import；from-import 首版需能证明成员为已有模块级函数。未知常量/类、wildcard、re-export 或包语义不补猜。
- 计划语义为旧项目模块名称不再保留；兼容 shim、同时重写 import、多个目录搬迁属于后续组合变化，首版不隐含执行。
- 解析范围固定声明为 `project_root_static`：只证明该项目根内的引用关系变化，不模拟实际 sys.path、已安装同名包或初始化执行。已知内置/标准库碰撞或解析根不明确时拒绝确定归因或转 manual_review。

ModuleChangeSpec 应记录解析假设及支持范围。仓库中有 utils.py 并不能证明所有运行环境的 `import utils` 都选择它；不得把当前 resolver 的名字命中当作无条件运行时保证，也不要通过 find_spec/import 目标模块验证。

### 5.2 示例与确定 Direct 条件

以下为未来设计案例，当前 API 尚无 rename_module：

```python
# report.py，真实源码中的导入仍保留旧名字
from utils import format_date
```

同时满足下列条件时，可报告**确定的项目内导入引用断裂**：

1. 此真实 ImportReference 在 before 下唯一绑定到计划目标 utils；对于 from-import，成员也在支持范围内可确认。
2. 目标快照、源码位置和 hash 一致，目标未歧义/解析失败；解析根及支持假设已明确。
3. rename 计划经校验，仅将 utils 的项目身份映射为 formatting，未保留旧名 shim，未制造冲突。
4. 在该虚拟 after 目录中，原声明 utils 不能再绑定到其原项目目标；原引用已经明确解析，也没有其他受支持的旧名保留机制。

结论应写为：“此导入原来绑定到项目模块 utils；计划重命名后旧项目名称不再提供，该引用需要检查/更新。”不能声称真实运行必定抛 ImportError，更不能声称格式化函数的参数不兼容。

| before / after 项目解析事实 | 归因 |
| --- | --- |
| 明确绑定目标 / 原目标因本次计划不可用 | ImportDirect |
| 明确绑定其他模块 / 同一目标仍可绑定 | no_impact |
| before 无法解析 / after 仍无法解析 | 原有解析缺口，保留 unresolved；不计本次 Direct |
| before 或 after 依赖未支持机制 | manual_review / unresolved；不成为确定传播 seed |
| 本范围无指向目标的引用 | 零确定影响；只说明当前范围未发现，不证明全项目无影响 |

alias 只改变引用在本地的名称，`import utils as u` 和 `from utils import format_date as fd` 都保留 utils 身份，因此不妨碍明确的 Module 判断。匹配依赖完整身份与快照，不搜索 `utils` 字符串后直接归因。

### 5.3 包、相对与动态机制

`__init__.py` 初始化、`__all__`、重导出链、namespace package、相对 import、动态 import 和运行时修改路径先暂缓。包模块命名已被索引不等于包加载语义已被支持。无法确认的引用/模块标明原因，保留 manual_review/unresolved 和 scope。

当前 AST 不完整记录条件/局部 import，现有 complete 也不代表这些依赖已被覆盖。后续模块事实层需记录这些未支持构造的位置或保守诊断，并使 Module coverage 为 partial；不改变旧 Function 报告的既有覆盖计算。对无法识别的任意动态机制，始终显示静态范围限制，不承诺全量依赖。

## 6. Remove Module 的共用基础

两种 Module Operation 共用同一模块目录、Import 引用账本、resolver、before/after assessment、依赖图、证据及报告：

| Operation | 专属验证与投影 |
| --- | --- |
| RenameModuleOperation | 旧目标存在且受支持；新名称/路径无冲突；显式旧→新映射；旧项目名称不保留 |
| RemoveModuleOperation | 旧目标存在且受支持；after 将目标标为删除；其余模块布局保持 |

Import 影响引擎只比较解析事实，不再分别为 rename/remove 建立两套扫描、绑定或传播逻辑。实际源码保持不变。删除 `__init__.py`、包目录树、二进制扩展模块及可能保留的外部同名提供者仍属于未支持/不确定范围。

Remove 的“已解析项目目标 → 因本次删除不可用”与 Rename 共用确定归因条件。原来 unresolved 的 import 不能自动被标为本次新增问题。

## 7. Graph、Direct/Indirect 与 Evidence 语义

### 7.1 两种图的结构区别

| 项目 | 现有 CallGraph | 待建设 ModuleDependencyGraph |
| --- | --- | --- |
| 节点 | 模块级函数 Symbol ID | 快照内 Module ID |
| 边 | 函数 caller→callee | importer module→被明确依赖的模块 |
| 位置 | 函数调用表达式 | 真实 ImportReference |
| Direct | 本次变化使调用 compatible→incompatible | 本次计划使已绑定项目导入引用的原目标不可用 |
| seed | 确定 Direct call site 的 caller | 确定 ImportDirect 的 importer module |
| 上游 | 函数调用路径 | 模块静态依赖路径 |

模块图从首版范围内逐 occurrence 的已解析导入事实建立，范围之外保留诊断，不能把函数图按文件名聚合当作完整模块图。导入可以没有函数调用，函数调用也不能证明所有导入依赖。

ImportDirect 按导入声明项/reference 计数；同语句多成员分别保留 reference_id，UI 明示计数单位，另可展示受影响模块去重数。不能将函数 call-site 数与 import-reference 数直接混算。

### 7.2 有限反向传播

建议复用现有策略：明确边的反向索引，从 Direct importer 向上最多两层；每 seed 使用 visited/BFS，同一上游模块只计一个 Finding，保留每个 seed 一条最短代表路径，跨 seed 取最小层数。已有 Direct importer 的模块优先显示 Direct，不重复标为 Indirect。

路径以 before 快照的真实 Module ID 表示，末边锚定原始 ImportDirect，并单独展示 Operation 的旧→新身份映射。多个同长度代表路径可任选一条真实路径，不能称其为完整项目图。末端 Direct 边允许形成真实递归/环形闭合，循环不得导致无限遍历。

例如 future fixture 中存在实际 import 边 `page → dashboard → report → utils`，且 `report → utils` 为确定 ImportDirect，则 report 为 Direct importer，dashboard 为 1-hop、page 为 2-hop。若保留当前距离约定，graph_distance 包括末端 Direct 边，分别为 1/2/3。

Module Indirect 的表述为：“此模块位于确定导入引用影响的上游静态依赖路径中，建议检查。”不声明执行、失败概率或一定运行失败。unresolved、manual_review、原有解析缺口和无影响项不传播。现有函数 Indirect 入口的强类型模型不接受模块种子，未来建设模块薄适配，不重构冻结的函数分析。

### 7.3 Import Evidence

建议独立 ImportEvidence，记录 domain、target_module_id、before/after 名称、reference_id、真实相对文件及 span、import 表达式、整文件 source_hash、rule/reason、before/after resolution 与模块依赖路径。

Direct Evidence 必须展示原始 import 语句；Indirect 每条 source path 展示各条真实导入位置，末边精确引用对应 Direct seed。source_hash 是实际 before 文件原始字节 SHA-256，不为尚未执行的 formatting.py 捏造源码或 hash。

复用 EvidenceBuilder 的安全读取、编码/行号错误、相对路径和 unavailable 原则；数据适配需区分 import_sites 与 call_sites，不将模块 ID 填入虚构的 caller_symbol_id。导入列号未记录时为 null/行范围，缺证据则 unavailable。证据生成失败不推翻已有静态事实，也不从别的影响项借用片段。

[ExplanationInput](../src/openimpact/explanation/models.py#L32)及 [fallback](../src/openimpact/explanation/models.py#L146)目前只校验函数 Evidence 并解释“调用/参数”。未来须显式增加 Import/Module 解释适配与规则措辞，保留旧函数输入/输出；先采用 rule 模式。LLM 不参与 Import 或 Symbol 解析，本轮与规划中的首版联调均不调用 DeepSeek。

## 8. API / React 后续影响面

### 8.1 API

- Inspect 已返回 `modules[{module,file,parse_status}]`，可展示模块清单；解析失败项仍在列表，歧义项在 diagnostics。未来补充模块种类、module_id、受支持 Operation、可选状态和原因，不能把所有 discovered module 都设为可重命名。
- 不复制 ZIP 解压或引入服务器路径输入。Inspect/Validate/Analyze 保持原 ZIP 重传、fingerprint、同请求快照、线程池及 finally 清理。
- Validate/Analyze 增加轻量域路由。旧 payload 缺省 Function，原四类签名 builder/validator/report 原样；Module 单独查模块目录，不要求 target_symbol_id 或 before/after signature。
- 无效名称、缺失/歧义/未支持目标、新名冲突需清晰 4xx；fingerprint mismatch 保留 409。具体新增字段与状态码在 Phase 7.5 冻结后方可成为公开契约。

以下 JSON **仅为设计草案，当前 API 会拒绝**：

```json
{
  "change_domain": "module",
  "change_type": "rename_module",
  "target_module_id": "utils",
  "new_module_name": "formatting"
}
```

Remove 将使用同一域与目标字段，change_type 为 remove_module，不新增专用 endpoint，不混入 added_parameter。

### 8.2 报告版本与兼容

现有 schema_version=1 的 `direct_impacts`、`indirect_impacts`、before/after、target_symbol、call_sites 都具有函数语义。仅往其中塞入 Module Finding 会导致旧 React 误读。

建议：**Function Report v1 逐字段保持；Module Report 使用显式 schema_version=2 + change_domain=module 的独立契约**，仍可由原 Analyze endpoint 在用户显式请求 Module 域时返回。此版本建议待负责人批准，本轮不升级任何生产 schema。

Module Report 草案字段：module change/布局投影、import_assessments、import_impacts、module_indirect_impacts、带明确计数单位的 summary、coverage/diagnostics、Import Evidence 及对应解释。不能伪造旧 signature 字段，也不能让旧函数数组为空却沿用有非零数量的旧函数统计。

新客户端按 domain/schema 使用适配器；旧 Function 客户端继续得到原响应。模块 Evidence 与 Explanation 继续一一对应并核对 metadata/reference_id，不能借用现有函数 evidence 匹配规则直接混合异构对象。

### 8.3 React

当前 [changeDraft](../frontend/src/state/changeDraft.js)、[actions](../frontend/src/state/actions.js#L139)、[ChangePage](../frontend/src/pages/ChangePage.jsx#L51)只处理四种函数参数变化，actions 还比较真实 before/after signature。直接返回 Module 结果会被现有校验拒绝。

未来按域增加目标选择及草稿：Function 继续选择 Symbol/参数；Module 选择实际模块和新名，展示“当前文件/计划文件”，草稿与后端确认分开。无函数的项目仍可能有可选模块，不能以空 symbols 列表阻断 Module 流程。

切换域/目标/操作继续取消旧请求、更新 revision、清除 Validate/Analyze/Report；原始 File、fingerprint 和 race protection 保留。报告中的 Module Trace 标注为“模块依赖路径”，Source Evidence 优先，所有源码按文本安全渲染。统计明确“导入引用/上游模块”；partial/unavailable 和中文辅助解释语义保持。

本轮没有修改任何 React 文件、请求逻辑或 reportData 映射。

## 9. Rename Module 最小测试规划

表中“当前”指已存在的语法/绑定能力，**不表示 rename_module 业务已实现**。所有 future Case 仍需人工根据源码和解析范围核验，不直接把现有程序输出当成 Ground Truth。

| 类别 | 当前能力 | 后续新增 / 首版决策 | 必须验证的语义 |
| --- | --- | --- | --- |
| 直接 import | flat 顶层绑定已支持 | 增加虚拟目录 assessment，首版支持 | 原项目目标因计划消失；精确 import 位置 |
| from import | 已知模块级函数成员支持 | 首版限定这些明确成员 | 不将未知类/常量自动视为 before 成功 |
| 两种 alias | 已支持事实与绑定 | 首版支持 | alias 不改变目标模块，证据保留原语句 |
| 同名模块 | 全名隔离、歧义诊断已有 | 首版测试 root 目标与其他目录同 basename；嵌套目标暂缓 | 不按文件 basename 串线；与外部名字不混同 |
| 子目录 importer | 模块路径和部分绝对绑定已有 | 首版暂缓确定 Module 分析，保留位置与 partial；后续扩展解析根/包规则 | 不把未覆盖的导入隐藏为零影响或补入确定路径 |
| 相对导入 | level 已保存，绑定拒绝 | 暂缓解析，补明确 scope/diagnostic | 不猜 Direct，Module coverage partial |
| 不相关模块 | 可匹配其他唯一项目模块 | 首版支持隔离检查 | 不生成目标的 Direct 或路径 |
| 多 Import seed | AST 列表保留，binding 表不足 | 新 reference_id/ledger 和去重，首版支持 | 同行/多成员/重复 alias 不丢失，统计单位一致 |
| 动态 Import | 没有字符串目标解析 | 暂缓，保守诊断和范围说明 | 不将文字命中升级 Direct |
| 无新增影响 | 可发现未被明确导入的模块 | 首版零结果测试 | 本范围 0，不宣称所有运行时引用安全 |
| 上游传播 | 无模块依赖图 | 建 ModuleDependencyGraph，首版支持两层 | 只用确定 seed；真实 import 链，超过两层截断 |
| cycle / dedup | 函数策略已有，模块实现不存在 | 首版必测 | visited、多 seed/多路径合并、真实末边锚点 |
| partial / unresolved | 已有解析错误和部分绑定诊断 | 扩展模块专属 coverage，首版必测 | 无效目标拒绝；其他失败文件保留已确认结果与范围警告 |
| 包初始化 / re-export | 路径映射部分存在，加载/导出不完整 | 暂缓 | 明确 unsupported/manual，不宣称 before 成功 |
| 新名冲突 / 特殊路径 | 尚无 Module Operation 校验 | 首版拒绝测试 | 文件/目录/大小写/NFKC 冲突、非法新名不改源码 |
| shim 或原名仍保留 | 尚无组合计划 | 不隐含支持 | 不自动归因确定断裂，不执行修复 |

所有新测试同时验证解析只读、文件 hash 未变、模块与函数报告隔离；保留四种 Signature Change 的完整回归与六个 Demo 基线。

## 10. Phase 7.1–7.6 建议修改文件

以下为分阶段预计范围，未创建生产文件；每阶段实施前需审核对应字段与验收。路径省略共同前缀 `src/openimpact/`，新文件明确标记。

| 阶段 | 目标与预计生产文件 | 预计测试 / 文档 |
| --- | --- | --- |
| 7.1 | Import/Module 事实与逐引用解析。新增 `analysis/module_facts.py`、`analysis/import_resolver.py`；在批准范围内补 `analysis/models.py`、`ast_parser.py` 的真实 import span/ordinal/scope；适配 `symbol_index.py` 共用项目查找规则，旧绑定行为不变 | 新 module_facts/import_resolver 测试；补 AST/Index 元数据回归；模块范围说明 |
| 7.2 | RenameModule 校验、虚拟 after 目录、ImportDirect。新增 `analysis/module_change.py`、`module_impact.py`、`change_domain.py`；旧 `change_spec.py` / `direct_impact.py` 不增加模块判断分支 | 新 Module Operation / ImportDirect 测试；旧四类型逐字段回归 |
| 7.3 | 依赖图、两层传播、Import Evidence/Module Report/CLI。新增 `analysis/module_graph.py`、`module_pipeline.py`、`module_report.py`、`reporting/import_evidence.py`；模块传播函数放入 `analysis/module_impact.py`，不放入 pipeline。`change_domain.py` 分发配置加载，模块 loader 放入 `module_change.py`，`__main__.py` 调用分发入口；旧 `change_file.py` / pipeline / report 保持。安全读取共用 `reporting/source_reader.py`，旧 `reporting/evidence.py` 仅作必要委托并验证行为一致；独立规则解释使用 `explanation/module_models.py`、`module_fallback.py` | 新 graph/propagation/evidence/report/CLI 测试；报告草案及解释边界；必要时拆子步骤 |
| 7.4 | RemoveModule 复用。仅扩展 `analysis/module_change.py` 的操作校验/投影和描述；复用 7.1–7.3 引用/传播/Evidence | Remove Direct/Indirect/无影响/不确定回归；验证没有第二套 Import 引擎 |
| 7.5 | HTTP 域接入与契约。`api_change.py` 加轻量分发，新增 `api_module_change.py`；适配 `api.py` 与 `repository/zip_inspector.py` 的模块候选项/报告序列化；旧 multipart、ZIP 安全及响应保留 | API validate/analyze、fingerprint、partial、失败清理、线程池；更新 api-contract / handoff / samples，经批准落地 Module Report 版本 |
| 7.6 | React 多域工作流及最终整合。`state/changeDraft.js`、`workflow.js`、`actions.js`；`FunctionSelectPage.jsx` 增加域目标选择或独立 ModuleSelectPage；`ChangePage.jsx`、`ReportPage.jsx` 用域内展示适配器；保留旧 reportData；按真实数据调整展示组件 | 四种函数流程加 Rename/Remove 的 Web E2E、竞态/错误/响应式；完整 pytest/check/build；独立评测待人工成果，不编造指标 |

现有 `change_file.py` 强制读取函数目标和 before/after signature，因此模块配置不能直接交给旧 loader；轻量域入口需先识别配置域，再选择域内 loader。新增模块传播的算法与 orchestration 分开，不将遍历逻辑塞入 pipeline。

`explanation/module_models.py` / `module_fallback.py` 预计提供独立 ModuleExplanationInput 与规则适配；复用通用 ExplanationResult，保留原 `explanation/models.py`、RuleBasedProvider 和 `explain_safely` 的函数行为，不把模块输入直接传给只接受函数 Evidence 的 Provider。首版模块解释走明确的规则路径，不需要修改 DeepSeek Provider。生产文件拆分应服从实际规模，不为尚未实现的 Symbol 域建立空框架。

## 11. 风险、不支持范围与本轮验证

优先风险是错误的 Module 绑定进入传播：source-root、外部同名库、包初始化/重导出、重复 local binding 和省略的条件 import 都可能污染结论。解决顺序为明确身份/范围 → 逐引用解析与诊断 → 虚拟布局差异 → 证据 → 有限传播，不能以字符串搜索或 LLM 填补缺口。

V1.1 最小方案仍不覆盖：自动重写 import、自动改文件/修复；任意 sys.path/path hook；完整 namespace/package/re-export；动态执行/反射；函数体业务行为；项目外调用者；完整 Symbol/Structure 引用。针对未知机制，结果与 UI 必须保留范围说明、manual_review/unresolved/partial。

当前评测仍缺成员 B 的独立人工成果，Phase 6.6 的三份文档保持原样；本架构审计不替代定量评测，也不将现有 Demo 重新命名为 Benchmark。

本轮以源码和现有测试核查能力；执行 Scanner/AST/Index/CallGraph 既有专项测试，**45 passed、1 skipped**。没有新增算法或运行新 Module Operation，也未重跑/冒称全套 597 项测试为本轮结果。既有稳定基线保留，后续任何实施必须重新执行完整回归。

负责人待确认的关键设计为：首版 flat/root/绝对顶层范围；Domain 分发与模块 Direct 的项目解析语义；reference 计数单位；Module Report 的显式版本；Phase 7 分步次序。审核通过后再进入 7.1。
