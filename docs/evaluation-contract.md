# Phase 6.6：Multi Change Type 评测契约

状态：**已实现哈希校验的本地 Evaluation Runner；待负责人和成员 B 提供独立 Benchmark 与人工 Ground Truth。**

本契约依据 `integration/multi-change-web@1cd8480` 的真实 Core 数据结构制定。它约定后续交付格式与计算口径，不构成已完成评测的声明，不改变生产 JSON `schema_version=1`。现状与缺口见 [接入核查记录](phase6.6-evaluation-readiness.md)。

## 1. 交付与标注独立性

成员 B 需交付源码、结构化 Change、人工标注、标注记录、Runner/指标脚本及复现说明；如果已有实现，优先适配已有成果，不另建平行体系。

人工标注按以下顺序进行：

1. 根据实际源码及 Python 调用绑定语义核对 before/after；仅考虑当前四种已支持变化。
2. 逐个目标调用点记录绑定依据，区分确定新增不兼容、仍兼容、既有问题、兼容性改善、展开参数人工检查及未解析调用。
3. 按源码中的明确调用边，独立标注确定 Direct 上游最多两层、Direct seed、可接受路径和去重结果。
4. 记录标注者、复核者、版本、争议及标注时间；冻结源码和标签哈希后再对照 analyzer。审核人信息由实际参与人员提供。
5. 发现差异时保留原始源码、标签和系统输出。标签修订必须有独立的语义依据、版本变更和人工复核记录，不能以系统输出为答案。

本轮没有代填人工姓名、标注依据或答案。六个 `examples/` Demo、生产 pytest 断言和 `frontend/tests/fixtures/change-specs.json` 仅用于回归，不计入独立 Benchmark。AI 可协助整理格式，不能将生成的答案宣称为已交付的人工标注。

## 2. 样本规模与覆盖计划

建议 **28 个独立案例，每类 7 个**；可接受交付规模为 24–30 个，每类至少 5–6 个。以下表格是选题计划，源码、调用位置与标签均待实际交付，不能据此填写得分。

| Change Type | 建议 7 项选题 |
| --- | --- |
| add_required_parameter | 普通位置参数缺失及完整三边链；已显式提供参数；keyword-only 新参数；修改前已不兼容；原来位置实参过多而修改后可绑定；分别含 `*args` / `**kwargs` 的调用；同名隔离、无法绑定的 import 或动态调用 |
| remove_parameter | 删除已传位置参数及完整链；关键字/混合调用与多个 Direct seed；未使用的可选参数；既有绑定错误；原来缺少被删除的必填参数；展开参数；positional-only/keyword-only 与 cycle、多路径去重 |
| rename_parameter | 旧关键字调用及完整链；纯位置调用；keyword-only 参数；原来使用新名字的调用；无关关键字造成的既有错误；展开参数；unresolved 与同名模块隔离 |
| make_parameter_required | 省略可选位置参数及完整链；已用位置/关键字显式提供；省略 keyword-only 默认参数；合法 positional-only 与混合参数；既有不兼容；展开参数；包含解析失败文件的 partial 项目及共享上游去重 |

每个案例原则上对应一个项目快照、一个目标和一次有效 Change。一个案例可以含多个调用点和混合分类，不能将整个项目只标为一个正/负标签。至少安排同一行两个调用、多个 seed、超过两层的上游、cycle 和同长度多路径，验证位置身份及有限传播。

默认值为 `None`、`False`、`0`、`""` 的语义，以及不支持的参数 kind、非法签名等应列入边界记录；若将同一源码上的多次 Change 作为不同案例，必须公开共享来源，不能虚增独立项目数。无效 Change 是单独的校验集，不作为零影响负例。

不强迫每类覆盖每种状态。交付时提供“实际覆盖表”；例如 make-required 只收紧必填约束，当前模型内没有 compatibility-improved 场景，该项记为不适用，并保留其他类型的改善案例。

## 3. 建议数据组织与字段

以下目录是**待接入布局**，本轮不创建空样本或标签文件：

```text
benchmark/
  manifest.json
  cases/<case_id>/project/...
  cases/<case_id>/change.json
  cases/<case_id>/ground-truth.json
  ANNOTATION.md
evaluation/
  runner.py                 # 如成员已有实现，沿用实际入口
  README.md
```

### 3.1 Manifest

| 字段 | 要求 |
| --- | --- |
| benchmark_version | 数据集自身的版本；不修改生产报告版本 |
| cases | 案例列表，Case ID 唯一 |
| case_id / change_type | 稳定 ID；四种正式 discriminator 之一 |
| project / change / ground_truth | 相对交付根目录的路径；不得含绝对路径或越界路径 |
| source_hashes | 每个输入源码相对路径及原始字节 SHA-256，包含会导致解析失败的文件 |
| change_sha256 / ground_truth_sha256 | 固定本次变化及标签版本 |
| tags / source_group | 实际场景标签；公开共享源码或派生来源 |
| origin / annotation_record | 人工构造或真实仓库来源、版本/许可及标注记录引用 |

### 3.2 Change 输入

Core Runner 使用完整 ChangeSpec：`change_type`、`target_symbol_id`、`before`、`after`、`operation`，旧 add 的 `added_parameter` 格式仍可用。字段与 [Change Type 文档](change-types.md) 一致，不自行写另一套签名构造算法。

`load_change_spec()` 读取完整 Core 格式；HTTP 简化配置仅含用户意图，不能直接传给这个 loader。已有 HTTP Runner 可继续通过 validate/analyze 构建变化，必须保持同一 ZIP/fingerprint，另报 HTTP 耗时；Core 和 HTTP 指标不能混算。

### 3.3 Ground Truth

| 字段 | 要求 |
| --- | --- |
| case_id / target_symbol_id / change_type | 与 Manifest 和 Change 一致 |
| annotation | 实际标注者/复核者 ID、时间、标签版本及独立性说明 |
| scope | 支持范围、已知不可判定区域、是否穷尽标注可比较调用点；partial 案例尤其需要说明 |
| call_assessments | 每个明确目标调用的调用者、位置、before_status、after_status、effect 和人工绑定依据 |
| direct_call_sites | 只包含 `compatible → incompatible` 的确定调用点 |
| indirect_impacts | 上游 Symbol、1-hop/2-hop、Direct seed 引用、各 seed 的可接受最短路径及标注依据 |
| manual_review_call_sites | 展开参数等无法静态确认的调用；不得填为确定 Direct |
| unresolved_calls | 文件位置、调用者（允许 null）、语法表达式、无法解析原因；不猜 target |
| expected_coverage | `complete` / `partial`，以及预期解析错误、unresolved import/调用或歧义位置 |
| rationale | 逐项引用源码，说明 Python 参数绑定及真实静态调用边，Indirect 只表示上游需要检查 |

标签必须保持 Direct 集合与 `call_assessments.effect=direct_impact` 一致，manual/既有问题/改善/仍兼容分别存储。标注不全、哈希失配、ID 重复、无复核记录或 Change 无效的案例记为数据问题，不能当作通过案例。

## 4. 与当前源码对接

现有入口已具备，后续 Runner 只负责编排和比较：

```python
from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.explanation.fallback import RuleBasedProvider

spec = load_change_spec(change_file)
run = analyze_project(project_root, spec)
report = build_report(run, explanation_provider=RuleBasedProvider())
```

| 数据 | 读取位置 |
| --- | --- |
| 确定 Direct | `report.direct_impacts` / `run.direct.findings` 中 effect=direct_impact |
| 完整 before/after 分类 | `run.direct.assessments`；公开 Report 没有全量 compatible/improved 数组 |
| Indirect 和 seed/path | `report.indirect_impacts[*].sources` 或 `run.indirect.findings` |
| manual review / 既有问题 | `report.manual_reviews` / `report.pre_existing_problems` |
| unresolved | `run.graph.unresolved_calls`；Report 的 diagnostics 只保留位置、expression、reason |
| coverage / 解析诊断 | `report.coverage` / `report.diagnostics` |
| Evidence | `report.evidences`；Explanation 同序，仅做契约检查，不参与判定得分 |

Core 分析不得 import/执行样本模块或运行其测试。Runner 不使用 LLM，显式指定 RuleBasedProvider。不得为获得分数补猜 unresolved 目标或调用路径。

## 5. 匹配身份与状态

- Direct、assessment、manual 的唯一键：`(case_id, target_symbol_id, caller_symbol_id, file, line, column)`。不能只按名字、行号或统计数量匹配。
- 路径边：`(caller_symbol_id, callee_symbol_id, file, line, column)`。
- Indirect：`(case_id, target_symbol_id, impacted_symbol_id, impact_type)`；另做 Symbol-only 对照以指出 hop 分类错误。
- unresolved：`(case_id, file, line, column)`；另核查 caller、expression、reason，不为其补上推测 target。项目所有 unresolved 都应记录，包括模块顶层调用，不能全部当作目标的漏报。
- 文件为项目相对 POSIX 路径，统一 `/`；保留大小写和 Unicode，不匹配本机 `report.project_path`。
- 调用 line 从 1 起，column 为 AST `col_offset`，从 0 起并按 UTF-8 字节偏移；SyntaxError 的诊断列由异常 offset 提供，单独处理。
- 不用中文 reason 全文、文件绝对路径、JSON 数组顺序或解释 confidence 作为分析正确性的身份键。

| before / after | effect | 确定 Direct / 传播 seed |
| --- | --- | --- |
| compatible / incompatible | direct_impact | 是 |
| compatible / compatible | no_impact | 否 |
| incompatible / incompatible | pre_existing_problem | 否 |
| incompatible / compatible | compatibility_improved | 否 |
| 任一 manual_review | manual_review | 否 |
| 未能解析 target | unresolved，未进入 assessment | 否 |

当前展开参数策略对任何 `*args` / `**kwargs` 调用先返回 manual_review。评测应分别记录保守策略正确性和无法判定范围，不将它们混成普通阴性。

## 6. Indirect 路径判定

当前 `graph_distance` 包含末端 Direct 边：1-hop 为 2、2-hop 为 3，上游传播层数为 `graph_distance-1`。

每个 Direct call site 是一个 seed；一个上游 Symbol 只计一个 Finding。跨 seed 取最小传播层数分类，保留每个可达 seed 的一条最短代表路径。已经是任一 Direct caller 的 Symbol 不再标为 Indirect。

对每个输出 `sources` 验证：

1. 路径起点为当前 impacted Symbol，方向为上游 caller → Direct caller → 目标。
2. 每条边与人工核验的源码调用位置一致，前后连通；末边精确匹配所引用的确定 Direct call site。
3. 上游遍历部分不重复节点，最多两层；对该 seed 为最短可接受路径。附加的真实末端 Direct 边允许形成递归或环形闭合，例如 `g → f → f` 或 `t → c → t`，不能仅因目标节点再次出现就判为错误路径。
4. 同一个 seed/上游对只出现一次；合法的同长度路径允许任选人工记录中的一条。
5. 不同 seed 的路径长度可以不同；Finding 的整体 graph_distance 取最短长度，不能要求所有 sources 都等长。

标注应提供各 seed/上游的可接受路径集合或经人工核验的调用边集合及最短距离。不能为迁就当前排序结果只接受 analyzer 选出的那条路径。路径正确性与路径/seed 完整性分开报告，避免遗漏所有路径却获得高正确率。

## 7. 指标与异常口径

### 7.1 Direct

对固定、已穷尽标注的可比较范围，以调用点集合计算：

```text
TP = |predicted_direct ∩ expected_direct|
FP = |predicted_direct - expected_direct|
FN = |expected_direct - predicted_direct|
Precision = TP / (TP + FP)
Recall = TP / (TP + FN)
F1 = 2 × Precision × Recall / (Precision + Recall)
```

分母为 0 时为 `null`，同时输出 TP/FP/FN、预测数和真值数。Precision 或 Recall 为 null 时 F1 为 null；两项都有定义且都是 0 时 F1=0。空真值且空预测的案例另报 `exact_match=true`，不将三项指标填为 1。

整体 micro 先汇总 TP/FP/FN 再计算；分 Change Type 采用同一口径。若报告 macro，只平均有定义的值并列出参与案例数。complete/partial 分层报告，明确 partial 人工标注范围，不将局部召回写成全项目召回。

真值 manual_review 被系统升级为 Direct 计 FP，并标注“越过人工检查边界”；真值 Direct 被系统返回 manual_review 计 FN，另报 abstention。unresolved、真正 no_impact、既有问题和 compatibility-improved 分区展示；不得共用一个“非 Direct”成功率。

### 7.2 其他必要指标

| 指标 | 分子 / 分母与附加记录 |
| --- | --- |
| Indirect Symbol Precision/Recall | 去重后的 `(Symbol, impact_type)` 集合 TP/FP/FN；另列错误 hop 与重复 Finding |
| Indirect 路径正确性 | 合法输出 source paths / 全部输出 source paths；无输出路径时 null |
| 路径来源完整性 | 正确覆盖的 `(上游 Symbol, Direct seed)` 对 / 人工要求的可达对；列 missing_sources、错误 seed、无依据边 |
| Coverage 分类正确性 | expected 与 actual 的 complete/partial 相同的有效案例数 / 有效案例数；附 2×2 分类表与原因差异 |
| 边界分类 | manual、unresolved、pre-existing、improved、no-impact 各自的 expected/actual 集合与错分记录；不算确定 Direct |
| Evidence 契约 | 位置/源码/hash/路径来源、available/unavailable 和 Explanation 同序关联；不将中文解释评分混入 Precision |
| 分析成功率 | 成功产出有效结果数 / 已接纳案例数；分析异常与无效 Change 另列，不视为正确零影响 |

Coverage 当前在 parse_errors、unresolved_calls、unresolved_imports 或模块/符号歧义存在时为 partial。manual_review 单独存在不会令 coverage partial。partial 的零结果不能证明全项目无影响。

平均分析耗时使用 `perf_counter` 包围 `analyze_project()`；另记录 Change 读取、Report/Evidence/Rule 解释及整次 Runner/CLI 耗时。建议每案例一次预热、五次串行测量，保留全部原始测量、环境和重复次数；整体均值取每个案例分析均值的平均。启动 Python 的 CLI 耗时不能标为纯 Core 分析耗时。超时/异常需保留，不能以删去慢案例改善均值。

## 8. Runner 与报告验收

待真实成果交付后按以下顺序接入：核验来源及哈希 → 校验标签完整性与人工复核 → 固定版本运行现有入口 → 保存原始报告/assessments → 逐点对照 → 汇总指标 → 人工复核失败案例。

结构化结果至少保留：运行版本/环境、数据集与标签哈希、实际总数和分类型数量、接纳/拒绝/失败数、TP/FP/FN 与 null 分母、分类型及 complete/partial 指标、错误路径和缺失 source、各边界分类分布、逐次耗时与原始差异位置。Markdown 摘要应链接可复现案例，不隐藏失败记录。

输入不合格、分析异常或标签争议时返回明确状态，并保留其数量；不得静默跳过。单案例失败不能使其余原始记录丢失。公开结果不携带个人绝对路径、密钥或临时环境内容；本地原始报告可放入已忽略的 `.local/`。指标与标签文件不得由 analyzer 输出覆盖。

仓库已提供 `python -m openimpact.evaluation <benchmark-dir>`：它会核验 Manifest、源码、Change 与人工标签的 SHA-256，拒绝不完整或不一致的输入后再调用现有静态分析，并输出 Direct、Indirect 与 Coverage 指标。它不生成 Ground Truth，也没有可对外宣称的独立 Benchmark 分数。交付真实数据后，可优先适配成员 B 的 Runner 或用该入口运行冻结数据；生产 Core 保持冻结。
