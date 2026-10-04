# Phase 6.1–6.4：Change Type 架构

Phase 6.1 建立 Operation 架构；Phase 6.2 注册 `remove_parameter`；Phase 6.3 注册 `rename_parameter`；Phase 6.4 注册 `make_parameter_required`。当前正式支持新增必填参数、删除一个普通参数、重命名一个可按关键字传入的参数，以及移除已有参数默认值。四种变化共用 before / after 兼容性判断和有限反向传播。

## 原实现影响面

| 位置 | 原有假设 | 本轮调整 |
| --- | --- | --- |
| `analysis/change_spec.py` | ChangeSpec 固定包含 AddedParameter；Validator 内直接判断只能新增一个必填参数 | 保留旧构造接口；将新增参数载荷、构造与差异校验放入 AddRequiredParameterOperation |
| `analysis/change_file.py` | JSON 必须包含 added_parameter | 继续读取旧格式；同时支持显式 operation 的结构化往返 |
| `api_change.py` | 简化请求固定 added_parameter；此处实现参数排序与插入 | 保留旧请求字段，增加可选 change_type；参数插入委托 Operation |
| `analysis/direct_impact.py` | Finding 规则名写死为 required_parameter_added_breaks_call | 由已验证的 Operation 提供规则名；兼容性算法与状态转换保持原样 |
| `analysis/report.py` | 中文变更摘要写死为新增必填参数；asdict 会自动公开模型新增字段 | 变更摘要委托 Operation；显式保留原有公开 JSON 字段 |
| `reporting/evidence.py`、`explanation/` | 已读取 Finding / ExplanationInput 中的规则、原因与变更描述 | 无需修改；源码位置、哈希、路径及解释 Provider 保持原样 |

## 模型与职责

`ChangeType` 为字符串 Enum，目前有 `ADD_REQUIRED_PARAMETER`、`REMOVE_PARAMETER`、`RENAME_PARAMETER` 和 `MAKE_PARAMETER_REQUIRED`。`ChangeOperation` 是四个具体载荷模型的类型联合；类型到载荷解码器的映射只读。后续批准新的类型后，将其加入 Enum、类型联合和映射即可，无需插件系统或可变注册器。

`AddRequiredParameterOperation` 为不可变 dataclass：

- `change_type`：固定 discriminator，不能在构造时换成其他类型。
- `added_parameter`：现有 AddedParameter，包含 name、kind、required、annotation_source。
- `insert_before`：可选的现有参数名，用于明确插入位置。
- `build_after(before)`：按现有参数类型顺序构造目标草稿。位置不合法时交由共享签名校验拒绝，不寻找替代位置。
- `validate_delta(before, after)`：确认签名只新增一个与载荷一致的必填参数；保留原有参数、默认值、注解、async 与返回注解。显式 insert_before 必须与目标草稿一致。
- `describe(target_symbol_id)` / `direct_rule_id`：为报告和 Evidence 提供变更语义，保留当前新增参数的中文措辞和规则名。
- `to_dict()` / `operation_from_dict()`：按 discriminator 编解码，拒绝未知类型、额外字段、缺失字段、非法 kind、非必填载荷等。

`RemoveParameterOperation` 同样为不可变 dataclass：

- `change_type` 固定为 `remove_parameter`；`parameter_name` 为待删除参数的 Python 标识符。
- 构造 after 前核对参数存在且 kind 为 positional-only、positional-or-keyword 或 keyword-only。缺失返回 `parameter_not_found`；删除 `*args` / `**kwargs` 返回 `unsupported_parameter_kind`。
- after 删除指定参数，其余参数对象顺序、kind、has_default、默认值与注解，以及函数名、async 和返回注解均保持原样。
- `validate_delta()` 要求差异恰好是该删除，额外的改名、重排、默认值变化等返回 `operation_signature_mismatch`。
- 变更描述为“目标 Symbol 删除参数 名称”，确定 Direct 的规则为 `parameter_removed_breaks_call`。具体不兼容原因仍由签名绑定给出。
- `legacy_added_parameter` 为 None，避免将删除意图当成新增参数。

共享 Validator 负责目标存在性、模块级函数边界、before 与源码一致、after 的 Python 签名合法性；然后委托 Operation 校验本次变化。`ChangeSpec.from_operation()` 仅在构造时生成 after；校验和影响分析不会再次生成或偷偷替换它。

## Canonical signatures

ChangeSpec 保留 `before`、`after` 公开名称，并提供 `before_signature` / `after_signature` 只读视图。这两个结构化签名是参数绑定的事实来源。

| 修改前 | 修改后 | 结论 |
| --- | --- | --- |
| compatible | incompatible | 本次变化导致的确定 Direct Impact |
| compatible | compatible | no_impact |
| incompatible | incompatible | pre_existing_problem，不计入本次 Direct |
| incompatible | compatible | compatibility_improved，不计入本次 Direct |
| 任一为 manual_review | 任意 | manual_review，不作为确定传播种子 |

Direct Engine 不按 change_type 重写兼容性判断。参数绑定原因始终取自实际签名，例如将 `b` 插在 `a` 前面后，`f(1)` 缺少的参数会是 `a`。Operation 提供规则与意图；调用边、before/after 状态、位置和证据仍由现有流程给出。

## 结构化往返示例

Operation JSON：

```json
{
  "change_type": "add_required_parameter",
  "added_parameter": {
    "name": "timezone",
    "kind": "positional_or_keyword",
    "required": true,
    "annotation_source": null
  },
  "insert_before": null
}
```

内部 `ChangeSpec.to_dict()` 默认保留 operation，可通过 `change_spec_from_dict()` 反序列化；before / after 仍必须提供。`load_change_spec()` 支持同一解码逻辑。若同时提供旧意图字段和 operation，它们必须一致，否则明确拒绝。

旧 CLI change.json、旧 ChangeSpec 五参数构造接口以及旧简化 HTTP 请求仍可使用。旧构造自动生成对应的新增参数 Operation；不支持的旧 change_type 仍由 Validator 返回明确诊断。

HTTP 响应与 CLI JSON Report 使用 `to_dict(include_operation=False)`。对于新增类型，继续保留 `change_type`、`target_symbol_id`、`before`、`after`、`added_parameter` 五个原字段，省略 operation，旧 JSON 不变。删除、重命名和移除默认值类型的 added_parameter 为 null，operation 必须保留，即使 include_operation=False 也不能丢失变更意图。schema_version 仍为 1，原新增 Demo 与前端请求没有修改。

HTTP 的 `change_type` 可选，缺省仍为 `add_required_parameter`。其余 multipart 字段、ZIP 重传、指纹核对、临时目录清理和错误响应流程继续使用原实现。

## 架构验收

测试覆盖四种 Operation 和 ChangeSpec 的 JSON 往返、载荷拒绝、旧字段冲突、canonical signature 判定、源码不变，以及旧 / 显式新增类型 HTTP 请求的完整响应一致性。删除测试还覆盖位置 / 关键字 / 混合调用、可选参数、仅关键字 / 仅位置参数、既有问题、兼容性改善、展开参数、多个 Direct 种子、循环、去重、真实源码 Evidence、规则解释、CLI 和 HTTP。重命名回归还覆盖名称合法性、仅 name 改动、keyword / positional 两个完整链 Demo，以及真实 TCP HTTP 和失败清理。移除默认值测试重点覆盖默认值存在性、非法位置参数顺序、None / False / 0 / 空字符串、混合参数种类及显式传参零影响，现有回归继续运行。

## 删除参数的 CLI 与 HTTP

CLI 的完整 ChangeSpec 示例位于 `examples/parameter_removal/change.json`：before / after 均为结构化签名，operation 为：

```json
{"change_type": "remove_parameter", "parameter_name": "timezone"}
```

```powershell
python -m openimpact analyze examples/parameter_removal --change examples/parameter_removal/change.json --format json
```

示例调用链为 `page → dashboard → report → format_date`。`format_date(date, timezone="UTC")` 计划删除可选 timezone；report 明确传入该关键字，after 下不再接受，产生一个 Direct，并沿原反向图产生一个 1-hop 和一个 2-hop。签名默认值 / 注解文本采用当前 AST Parser 的规范表达，例如 `default_source="'UTC'"`；源码证据仍保留实际原文，不改变其哈希或位置。

HTTP 继续使用 inspect / validate / analyze 原路径和同一 ZIP；简化配置为：

```json
{
  "change_type": "remove_parameter",
  "target_symbol_id": "utils.format_date",
  "parameter_name": "timezone"
}
```

省略 change_type 仍按新增类型处理，不根据 parameter_name 猜测删除意图。删除配置拒绝混入 added_parameter 或 insert_before；错误结构、状态码、指纹与资源清理约定见 `api-contract.md`。

## 重命名参数：Phase 6.3

`RenameParameterOperation(parameter_name, new_parameter_name)` 为不可变 dataclass，discriminator 固定为 `rename_parameter`。旧名必须存在，新名必须为合法 Python identifier、不能是 keyword、不能等于旧名、不能与任何现有参数重名（包括 *args / **kwargs 的名字）。支持 `positional_or_keyword` 和 `keyword_only`，保留被改名参数的原始位置、kind、默认值及注解，保留其他参数、函数名称、async 和返回注解。`validate_delta()` 精确核对唯一变化为该参数的 name，不重新构造用户声明的 after。

明确拒绝重命名 `positional_only`、`var_positional`、`var_keyword`。这些形式涉及函数体引用或更复杂语义，当前模型仅评估调用签名兼容性。

Unicode 名称与 Python AST 一致按 NFKC 归一化，再进行重名、相同名称及关键字检查；after 与序列化 operation 使用规范名字，避免全角 `ａ` 等名称绕过 `a` 的冲突校验或与调用关键字错配。

API 简化配置：

```json
{
  "change_type": "rename_parameter",
  "target_symbol_id": "utils.f",
  "parameter_name": "timeout",
  "new_parameter_name": "delay"
}
```

通过原 validate / analyze endpoint 提交，同一 ZIP 和 fingerprint 约定不变；不能混入 added_parameter 或 insert_before。CLI 使用包含 before、after 和 operation 的完整 ChangeSpec，示例位于以下两个独立目录：

```powershell
python -m openimpact analyze examples/parameter_rename_keyword --change examples/parameter_rename_keyword/change.json --format json
python -m openimpact analyze examples/parameter_rename_positional --change examples/parameter_rename_positional/change.json --format json
```

两个项目均为 `page → dashboard → report → utils.f`，签名由 `f(a, timeout)` 变为 `f(a, delay)`。keyword Demo 的实际调用为 `f(a, timeout=5)`，预期 Direct / 1-hop / 2-hop = 1 / 1 / 1、complete；positional Demo 为 `f(a, 5)`，预期 0 / 0 / 0、complete，Evidence 与 Explanation 数组为空。

| 调用（原签名 f(a, timeout)） | before | after | 归类 |
| --- | --- | --- | --- |
| f(1, 5) | compatible | compatible | no_impact；位置绑定不依赖参数名称 |
| f(1, timeout=5) / f(a=1, timeout=5) | compatible | incompatible | Direct；旧关键字无法绑定到新签名 |
| f(1, delay=5) | incompatible | compatible | compatibility_improved；不计 Direct |
| f(1, timeout=5, extra=1) | incompatible | incompatible | pre_existing_problem；不计 Direct |
| f(1, *args) / f(**payload) | manual_review | manual_review | 不猜测展开内容，不传播 |

仅关键字的可选参数未被显式传入时，两次签名都能兼容。若函数保留 **kwargs，旧关键字可能被其接受；是否缺少新名对应的必填参数仍由真实 after 签名决定，不能看到旧 keyword 就一律报 Direct。

确定 Direct 使用规则 `parameter_renamed_breaks_keyword_call`，原因保留实际 before / after 绑定诊断。报告层通过 Operation 的 `evidence_reason()` 给 Evidence 补充 `timeout → delay` 语义；原 add/remove 返回原 reason，完整旧报告保持不变。EvidenceBuilder 的文件、行号、片段、哈希及传播路径不变；Explanation 输入只读取当前 Evidence 与 Operation 描述，rule 模式无需模型请求。

## 移除默认值：Phase 6.4

`MakeParameterRequiredOperation(parameter_name)` 为不可变 dataclass，discriminator 固定为 `make_parameter_required`。参数必须存在、kind 为 `positional_only` / `positional_or_keyword` / `keyword_only` 且当前有默认值；拒绝 `var_positional` / `var_keyword`。名称按 Python NFKC 规则规范化。`build_after()` 仅清除指定参数默认值，保留其名称、顺序、kind、annotation，保留全部其他参数与函数元信息；随后复用共享签名合法性检查。`validate_delta()` 精确检查唯一变化是该默认值移除，不在分析时重新生成 after。

当前模型的无默认值表示为 `has_default=False, default_source=None`，有无默认值由 has_default 判断。

| 源码状态 | has_default | default_source |
| --- | --- | --- |
| timeout=None | true | 字符串 `"None"` |
| timeout=False | true | 字符串 `"False"` |
| timeout=0 | true | 字符串 `"0"` |
| timeout="" | true | 字符串 `"''"`（AST 规范文本） |
| timeout，无默认值 | false | null |

默认值表达式只作为语法文本保存和比较，不执行、不求值。原来有默认值但省略传参的调用会从 compatible 变为 incompatible；显式提供值的调用继续兼容。该变化只收紧同一签名的必填条件，在当前模型内不会产生 incompatible → compatible；共享引擎的 compatibility_improved 分类和旧类型的对应测试保留。

签名顺序示例：

| before / 操作 | 结果 |
| --- | --- |
| f(a=1, b=2)，只移除 b 默认值 | 拒绝 invalid_after_signature；不会生成 f(a=1, b) 或改动 a |
| f(a=1, /, b=2)，只移除 b 默认值 | 拒绝 invalid_after_signature；位置参数默认顺序跨越 / 检查 |
| f(a=1, b=2)，只移除 a 默认值 | 合法 f(a, b=2) |
| f(a=1, *, timeout=30)，移除 timeout 默认值 | 合法 f(a=1, *, timeout)；keyword-only 不受位置参数默认顺序约束 |

同一 validate / analyze API 接受：

```json
{
  "change_type": "make_parameter_required",
  "target_symbol_id": "utils.connect",
  "parameter_name": "timeout"
}
```

该配置仅接受这三个字段，不允许 added_parameter、new_parameter_name、insert_before 或 default。参数不存在 / 已必填 / kind 不支持 / after 非法分别为 HTTP 422 `parameter_not_found` / `parameter_already_required` / `unsupported_parameter_kind` / `invalid_after_signature`。指纹不一致仍为 409。HTTP 请求与临时快照生命周期不变。

CLI 使用包含 before、after 和 operation 的完整 ChangeSpec：

```powershell
python -m openimpact analyze examples/parameter_required_missing --change examples/parameter_required_missing/change.json --format json
python -m openimpact analyze examples/parameter_required_explicit --change examples/parameter_required_explicit/change.json --format json
```

两者均为 `page → dashboard → report → utils.connect`，计划将 connect(address, timeout=30) 改为 connect(address, timeout)。missing Demo 的真实调用省略 timeout，预期 1 / 1 / 1、complete；explicit Demo 的真实调用为 connect(address, timeout=10)，预期 0 / 0 / 0、complete。零影响的 Evidence / Explanation 为空。

确定 Direct 规则为 `parameter_became_required_breaks_call`。Operation 的 evidence_reason 补充“参数从可选变为必填，移除原有默认值”；实际原因继续包含修改前兼容、修改后缺少该必填参数。报告的 before 保存原默认值语法文本；文件、位置、源码片段、哈希与路径由原 EvidenceBuilder 提供。Explanation 只解释这些事实，不决定影响。report.py、EvidenceBuilder 和 Provider 本轮无需修改；schema_version=1，added_parameter=null，operation 完整表达 intent。

## 当前能力边界

删除参数并不自动等于调用不兼容。`f(a, b=2)` 的 `f(1)` 可以继续兼容；若保留 `*args` / `**kwargs` 定义，原有显式实参也可能仍合法。含展开实参的调用继续 manual_review，未解析调用继续 unresolved，不成为确定传播种子。

本轮只评估签名兼容性，不判断参数删除后函数体是否仍引用它，也不判断位置实参重新绑定后的业务含义或返回值变化。例如 `f(a, b, c=3)` 删除 b 后，`f(1, 2)` 仍可绑定到 a、c，不能直接宣称确定不兼容。Indirect 仍仅表示上游待检查路径。

Phase 6.1 的主要补齐点为：公开序列化需要保留新类型的 operation；JSON 解码需正确处理删除的 added_parameter=null；API 配置从单一新增形式扩展为按类型读取载荷。Direct、Call Graph、传播和 Evidence 算法无需改动。

参数重命名分析不修改源码、不检查函数体内部旧参数名引用，也不评估 positional-only 重命名的内部引用风险。reflection / inspect.signature、docstring、type comment 和 external string references 均不在本轮范围内。纯位置调用的 No Impact 仅表示没有新增调用绑定不兼容，不能据此保证函数体或整个程序安全。

移除默认值同样仅分析调用签名兼容性，不分析函数体业务逻辑、默认值本身变化导致的行为差异、reflection / inspect.signature、docstring 或 external configuration。含展开实参的调用仍为 manual_review，不猜测、不作为确定传播种子。当前只注册四种已批准 Operation，未实现 make_parameter_optional。
