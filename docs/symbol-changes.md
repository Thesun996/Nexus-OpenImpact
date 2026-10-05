# V1.2 公共模块符号变更契约

## 领域与范围

`change_domain="symbol"` 新增两种不可变 Operation：`rename_module_symbol`、`remove_module_symbol`。原 Function 的四种签名变更和 Module 的两种模块变更继续使用各自模型、判断依据和报告，没有全局 schema 升级。

本轮只支持项目根目录、唯一且受支持的普通 `.py` 模块中，公开名称的单次简单 `Assign` 或有值的 `AnnAssign`。可确定的字面量包含 None、布尔、数字、字符串及简单字面量容器；读取 AST 事实，不计算表达式、不 import 项目、不执行源码。大写名称标记为 constant，其他公开名称标记为 variable，二者共享引用语义。源码 hash 是完整文件原始字节的 SHA-256。

复杂/链式/解包/条件赋值、重复绑定、私有名称、动态导出和不支持的包候选保留禁用原因，不能作为目标。名称冲突检查包含同模块函数、类、import及其他静态绑定，包括函数定义时default/decorator中的赋值、类作用域明确global写入与match mapping rest绑定。新名须为公开、规范 Unicode Python identifier，不能为 keyword、旧名或已占用名称。

## 引用矩阵

| 引用 | 当前处理 |
| --- | --- |
| `from config import MAX_RETRIES` | 确认唯一根模块公共符号；保留真实导入位置 |
| `from config import MAX_RETRIES as RETRIES` | alias 读取绑定相同定义；导入与读取为独立实际位置 |
| `import config; config.MAX_RETRIES` | 两段属性读取确认模块和成员 |
| `import config as cfg; cfg.MAX_RETRIES` | 通过明确 alias 绑定 |
| 目标模块内部 `MAX_RETRIES` | 在受支持作用域内确认唯一模块定义 |
| 同名函数参数/局部变量 | local，不归入模块符号 Direct |
| 其他模块同名变量 | 按 module.symbol ID 隔离 |
| 读取发生在导入/定义之前 | unresolved，不作为新增 Direct 种子 |
| from import 函数 | 保持原 Function 领域，不伪造变量缺失 |
| 条件、相对、wildcard、嵌套/类/推导式及复杂重导出 | manual_review 或边界诊断，partial |
| 外部库、未知对象属性、缺失成员 | unresolved，partial，无猜测传播 |
| getattr / 复杂属性 | 保守诊断；无法证明的读取不成为确定影响 |
| 项目属性写入 | 该目标引用降级 manual_review，防止虚拟删除后重新创建旧名 |
| setattr / delattr / vars / exec / eval，包括明确builtins模块/函数alias | 项目级动态写入保护；已解析变量引用转人工检查 |
| 类/嵌套作用域属性写入，模块 `__dict__` 获取或写入 | 保守项目级动态写入诊断，引用转人工检查；不猜测运行时重新绑定 |
| Name/Attribute 类型注解 | 当前不做注解求值；保留manual_review引用与真实位置 |
| match mapping rest局部变量 | local遮蔽，不归入模块符号Direct |
| globals / 动态生成模块定义 | 禁用相关模块目标，保留真实位置的诊断 |

动态写入保护按整个项目保守处理，可能降低可确定结果数量；没有基于字符串猜测写入目标。仅只读动态访问不自动把全项目降级。

## 虚拟变更与影响

`SymbolChangeSpec` 保存目标 `VariableSymbol` 快照和类型安全的 Operation。Before 有名称、模块、相对文件、起止行列、原定义、value_source、annotation_source、source_hash；Rename After 只投影新名称、ID 和定义文字，保留值、注解和位置；Remove After 为 null。`modifies_source=false`。

Direct 条件为：同一稳定 `reference_id` 在 Before 唯一绑定目标项目符号，After 因本次投影成为 `symbol_not_in_project`。certainty 为 `definite_project_reference_break`，只证明受支持静态模型内新出现的引用断裂，不保证业务运行失败。原 unresolved、manual_review、no_impact、resolution_improved 不成为传播种子。

Direct 按真实源码引用位置计数：一个 from import 与后续 alias 读取可以形成两个位置。Indirect 按上游模块去重，复用 Module Dependency Graph 中 importer → target 的真实导入边，反向最多两层。每个 Direct seed/上游保留一条最短代表路径，visited 处理循环；多个 seed 的证据保留，Direct 来源模块不重复计为 Indirect。

传播路径 `modules` 只包含真实上游模块边，例如 `page → dashboard → client`；最终 `config.MAX_RETRIES` 引用作为 `terminal_reference` 单独保存。不会添加不存在的 client → config 调用边，不把代表路径描述为完整项目图。

## HTTP 输入

继续复用三个业务端点和原 multipart 规则：

- `POST /api/v1/projects/inspect`：必填 file；追加 `symbol_inventory`、`symbol_coverage`、`symbol_diagnostics`，原十个 Function/Module Inspect 字段保持。
- `POST /api/v1/changes/validate`、`POST /api/v1/projects/analyze`：必填 file 和 change(JSON string)，可选 expected_fingerprint。每次重复上传同一原始 ZIP。

```json
{"change_domain":"symbol","change_type":"rename_module_symbol","target_symbol_id":"config.MAX_RETRIES","new_symbol_name":"RETRY_LIMIT"}
```

```json
{"change_domain":"symbol","change_type":"remove_module_symbol","target_symbol_id":"config.MAX_RETRIES"}
```

Symbol 配置不接受额外路径、added_parameter 或其他 Operation 字段。合法配置返回200；目标不存在、目标不支持、名称非法/不规范/冲突/相同或字段错误返回422，使用原 `validation.valid=false`、`validation.diagnostics` 结构。ZIP 错误、安全限制和409 fingerprint_mismatch 完全沿用既有流程；内部异常为安全500，不回显路径或堆栈。Validate 与 Analyze 在各自请求中，对同一经过指纹验证的 ZIP 快照建立 Spec；React 再核对配置 revision、Inspect identity 和已校验 Spec。

## 独立 Symbol Report v1

判别三元组：`(change_domain="symbol", report_kind="symbol_impact", schema_version=1)`。旧 Function Report 和 Module Report 不变。主体：

| 字段 | 含义 |
| --- | --- |
| change / validation | 实际 Symbol Spec / 校验结果 |
| summary.direct_reference_count | 确定受影响的实际符号引用位置数 |
| summary.indirect_1hop_module_count / indirect_2hop_module_count | 按最短距离归类的上游模块数 |
| summary.manual_review_count | 人工检查引用与语法/导入边界诊断项数，非独立受影响符号数 |
| summary.unresolved_reference_count | 未解析符号引用与普通导入项数 |
| counting_units | Direct unique_source_reference，Indirect unique_upstream_module |
| reference_assessments | 同一引用 Before / After 解析与 effect |
| reference_impacts | Direct 引用位置、before_resolution、after_resolution、rule/reason |
| symbol_indirect_impacts | hop、来源 Direct ID、真实上游依赖路径与终端引用 |
| coverage / diagnostics | `project_root_static_symbols` 限定范围、解析/候选/导入/读取诊断 |
| evidences / explanations | Direct 后接 Indirect，同序、同 evidence_reference |

HTTP 另有 project_name/project_fingerprint；所有文件与位置使用项目相对路径。complete 只表示明确声明的支持范围完成；partial 的0条结果不证明全项目无影响。不同领域的 coverage 分开使用，不能用旧 Function coverage 替代 Symbol coverage。

Evidence 来自安全源码快照读取，含实际源码片段、原始文件 hash、位置、rule、reason、Before/After 解析及 propagation_path。文件缺失、位置/哈希无效或读取异常时 status=unavailable，保留影响结论。中文规则说明使用已有事实，risk_level=unknown；confidence=1 表示规则事实确定度，不表示运行失败概率。本轮不调用外部模型。

React 根据记录 ID、类型、目标、位置、Before/After 以及路径/末端引用再次检查同序对应关系。证据不匹配或不可用时不能借用相邻记录，解释区明确降级。源码按普通 React 文本呈现。

真实脱敏响应见 `api-samples/symbol-inspect-response.json`、`symbol-validation-response.json`、`symbol-report-response.json`，均来自实际接口输出。

## 使用与边界

```text
python -m openimpact analyze examples/symbol_rename --change examples/symbol_rename/change.json --format json
python -m openimpact analyze examples/symbol_removal --change examples/symbol_removal/change.json --format json
python -m openimpact analyze examples/symbol_no_impact --change examples/symbol_no_impact/change.json --format json
python -m openimpact analyze examples/symbol_boundaries --change examples/symbol_boundaries/change.json --format json
```

前两项1/1/1 complete，第三项0/0/0 complete，边界项1/1/1 partial。它们是功能用例，未充当独立人工 Ground Truth。不分析任意数据流、值变化行为、包初始化、动态 import hook、反射及任意 Python 运行时语义。
