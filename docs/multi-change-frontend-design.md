# Phase 6.5 Step 1：四种 Signature Change 的前端接入设计

状态：设计与影响面审计完成，等待负责人审核。本文未实现 React 接入，也未合并分支。

## 1. 审计依据与当前基线

审计日期：2026-10-04。

| 范围 | 实际基线 | 工作区情况 |
| --- | --- | --- |
| 最新远程主线 | `origin/main`，`3a5a582` | 本轮 fetch 后确认；原 main 工作区干净 |
| Backend Phase 6 | `feature/change-types`，`101d838` | 相对 main 为 0 behind / 1 ahead；Phase 6.4 仍有未提交修改 |
| Tracework UI | `feature/ui-redesign`，`deb7e82` | 相对 main 为 0 behind / 1 ahead；动效与统计区仍有未提交修改 |
| 两条 feature 的共同基线 | `3a5a582` | 已提交差异与当前未提交文件合并计算，没有同路径修改交集 |

审计读取两条 feature 的实际工作区，以包含尚未提交的第四种 Change 和最新 UI。只合并现有提交会遗漏这些成果。当前没有执行 merge、rebase、commit、push，也没有创建集成分支。

主要依据：

- 后端 `src/openimpact/api_change.py`、`analysis/change_spec.py`、`docs/api-contract.md`、`docs/change-types.md` 与六个真实示例目录。
- 前端 `ChangePage.jsx`、`ReportPage.jsx`、`state/workflow.js`、`state/actions.js`、`state/WorkflowContext.jsx`、`api/client.js`、`pages/reportData.js` 和现有测试。
- `frontend/DESIGN.md`，保留 Tracework 的 Change → Trace → Evidence 阅读顺序、六色 Token、字体、键盘操作与响应式规则。
- 实际读取已安装的 `frontend-design/SKILL.md`，应用任务优先、真实内容决定结构、克制交互与既有视觉方向优先的规范；本轮未调用外部 Skill CLI。

本轮实际运行当前 UI 的 `npm run check`：**97 passed，0 failed，生产构建成功**。该命令已经包含 `npm run build`。这些结果证明现有单类型 UI 基线可用；四种 Change 的浏览器验收将在 Step 2 实施后执行。

## 2. 单一 Change Type 的硬编码影响面

下列路径以 `frontend/` 为根，审计对象为 Tracework 工作区当前版本。

| 位置 | 当前假设或行为 | 四类型接入所需调整 |
| --- | --- | --- |
| `src/state/workflow.js`：`createInitialState`、`DEMO_RECEIVED`、Inspect 重置 | `change` 只有 `parameterName/parameterKind/insertBefore`，没有类型 | 使用带类型的统一草稿工厂；所有初始化与重置入口采用同一默认策略 |
| 同文件：`buildChangePayload` | 所有配置生成 `added_parameter`，缺省依赖后端的新增类型 | 一个构造函数按四种已注册类型输出各自允许的字段，拒绝未知类型 |
| 同文件：`SYMBOL_SELECTED` | 保留原参数名，只清空插入位置 | 更换函数后重置当前类型的配置，避免继续引用旧函数参数 |
| 同文件：`CHANGE_UPDATED` | 将所有字段平铺合并 | 类型切换完整替换 operation；普通编辑只更新当前类型允许的字段 |
| 同文件：`isSupportedDemoChange` | 只检查固定 Symbol、参数名、kind、插入位置 | 增加明确的 add 类型约束，保留离线演示仅支持原固定案例的边界 |
| `src/state/actions.js`：Validate / Analyze | 生命周期通用；调用统一 payload builder；成功响应目前主要检查 target | 保留取消、revision、重复点击保护；补类型与已校验 Change 的一致性检查 |
| `src/pages/ChangePage.jsx` | 标题、表单、按钮可用性、草稿说明、高亮都围绕新增必填参数 | 统一页面中加入类型选择、现有参数选择和 rename 新名称字段；区分草稿预览与已确认签名 |
| `src/components/workflow/WorkflowParts.jsx`：`SignatureText` | `addedParameterName` 与 `oi-added-parameter` 仅表达新增名称 | 将展示标记泛化为新增、删除、重命名、移除默认值；保留安全文本渲染与不修改原对象的要求 |
| `src/pages/ReportPage.jsx`：`ChangeOverview` | 固定“新增必填参数”，读取 `added_parameter.name/kind/required` | 根据本次报告的 `change_type/operation` 显示四类操作，兼容旧 add 报告 |
| `src/pages/UploadPage.jsx`、`src/components/AppShell.jsx` | 支持范围文案写着“新增一个必填参数” | 简短说明四种签名变更；保留 Python / 模块级函数与独立演示标识 |
| `frontend/DESIGN.md` | 配置页、报告 Change 区和部分范围说明仍采用 add 场景 | 在 Step 2 补充本次已审核设计，保留现有 Token、布局、Motion 与证据规则 |
| `tests/workflow.test.js`、`actions.test.js` | 草稿字段、payload 和固定演示断言仅覆盖 add | 保留旧安全回归，增加四类型构造、切换、取消和晚返响应测试 |
| `tests/workflowRendering.test.js`、`reportRendering.test.js` | 草稿、参数高亮、报告目标主要使用 add fixture | 增加类型配置、禁用原因、四类真实报告与零影响渲染 |
| `tests/apiClient.test.js` | Client 本身通用，但测试 change 示例仅为 add | 用四类 JSON 验证原 Client 的 FormData、原始 File、指纹及 signal，无需重写 Client |
| `tests/motion.test.js` | 参数或 Symbol 编辑已覆盖，尚无类型切换 | 验证切换类型后退出中的旧报告也立即失效 |

以下能力可直接保留：

- `api/client.js` 已通用发送 `JSON.stringify(change)`，不手写 multipart boundary；接口地址集中管理。
- `WorkflowContext.jsx` 的 Provider、原始 File 和 actions 生命周期无需重新组织。
- `formatSignature()` 已根据结构化参数显示 `/`、`*`、`*args`、`**kwargs`、默认值和注解，能正确显示无参函数。
- 函数列表来自 Inspect 的完整 Symbol，未把实际项目目标写死为 Demo 函数。
- `reportData.js` 的同序 Evidence / Explanation 匹配与完整性诊断依赖调用身份、位置、源码快照和路径，没有 add 专属判断。
- ImpactIndex、TraceView、EvidencePanel、ExplanationPanel 和统计组件使用已有影响类型及报告数据，无需因 Change Type 重写。

补充发现：`docs/api-contract.md` 的详细四类型说明已齐全，但成功响应后的概括段仍只提“增加或删除参数”；`docs/frontend-handoff.md` 也保留早期交付阶段的历史说明。Step 2 可同步澄清四类型范围，不调整公开字段或接口语义。

## 3. 统一 Change Draft 状态模型

保留一个 `state.change`，使用 `changeType` 区分 operation 字段。项目、ZIP、Inspect、fingerprint、选中 Symbol、validation、report、loading、error 与 revision 继续使用现有顶层状态。

建议用 JSDoc 描述四个明确分支，无需迁移 TypeScript，也无需 schema DSL 或插件注册框架：

```text
ChangeDraft =
  { changeType: "add_required_parameter",
    operation: { parameterName, parameterKind, insertBefore } }
  | { changeType: "remove_parameter",
      operation: { parameterName } }
  | { changeType: "rename_parameter",
      operation: { parameterName, newParameterName } }
  | { changeType: "make_parameter_required",
      operation: { parameterName } }
```

初始值：

```json
{
  "changeType": "add_required_parameter",
  "operation": {
    "parameterName": "",
    "parameterKind": "positional_or_keyword",
    "insertBefore": ""
  }
}
```

完整提交草稿通过选择器读取 `selectedSymbolId` 和上述 `change`；目标对象通过 `getSelectedSymbol(state)` 从当前 Inspect 获取。无需在草稿中再保存一份 Symbol 对象或第二个 target ID。

`createChangeDraft(type)` 只处理四个初始配置；一个 payload builder、一个页面、一个 Validate / Analyze 生命周期服务所有类型。类型未知时明确拒绝构造请求，不默认为 add。

### 3.1 状态失效规则

| 用户事件 | 保留 | 立即清理 / 重置 | 请求保护 |
| --- | --- | --- | --- |
| 更换 ZIP / 新项目 | 既有 health 状态 | Inspect、fingerprint、Symbol、草稿、校验、报告与旧错误 | 继续取消旧请求并递增 revision |
| 切换 Change Type | 同一 File、Inspect、fingerprint、目标 Symbol、health | 整体替换 operation；清除 validation、report、旧配置错误和业务 loading | 通过现有 actions 的取消入口，revision + 1；晚返结果不得写入 |
| 更换 Symbol | File、Inspect、fingerprint、当前 Change Type、health | 当前类型字段恢复空初始值；清除 validation、report、旧错误 | 同样取消旧请求并递增 revision |
| 修改当前类型字段 | File、Inspect、fingerprint、Symbol、当前类型 | 旧 validation / Analyze / report；不保留上一版已确认签名 | 使用当前类型字段白名单，沿用取消与 revision |
| 409 fingerprint mismatch | 原始 File、health | 按既有逻辑清除所有失效项目上下文 | 要求重新 Inspect，不自动改指纹继续分析 |

新增类型切换事件可命名 `CHANGE_TYPE_SELECTED`，经 `actions.selectChangeType()` 进入现有 `changeState()`；不建立另一套并发控制。切换回旧类型也恢复空配置，不缓存上一类型的校验或报告。

可提交状态从当前字段与目标推导，不另存重复的 `isValid`。前端输入齐全只允许点击 Validate；只有当前 revision 对应的后端 `validation.valid=true` 才允许 Analyze。

## 4. 参数选择 UX

新增类型输入新名称；其余三类从当前 Inspect 的 `parameters[]` 选择真实现有参数，按源码顺序展示。行内显示参数名、kind 的中文说明及当前默认值，不创造后端没有提供的类型推断。

| 类型 | 可选项 | 禁用项与可见说明 |
| --- | --- | --- |
| add_required_parameter | 新名称；三种普通参数 kind；可选 `insert_before` | 不提供新增 `*args` / `**kwargs`；插入位置只能来自本函数现有参数，合法性仍待 Validate |
| remove_parameter | positional-only、positional-or-keyword、keyword-only；可删必填或可选参数 | `*args` / `**kwargs`：“当前不支持删除展开参数” |
| rename_parameter | positional-or-keyword、keyword-only | positional-only：“当前不分析仅位置参数重命名涉及的函数体引用”；展开参数：“当前不支持此类重命名” |
| make_parameter_required | 三种普通 kind 且 `has_default === true` | 已必填：“当前没有默认值，已经是必填参数”；展开参数：“当前不支持移除展开参数的默认值” |

`has_default` 是判定依据：`None`、`False`、`0`、`""` 均是合法默认值，不能用 `default_source` 的真假值筛选。缺失必要元数据时提示“参数信息不足，请重新读取项目”，不猜参数可用性。

使用原生 radio / select 和可见文字说明。禁用原因放在参数行或其旁说明中，不只放在无法获得焦点的 disabled 控件 Tooltip 中。支持状态同时有文字与符号，不只靠颜色。触控区域至少 44px。

没有合格参数时保留完整目标及禁用原因，显示“此函数没有可用于当前变更的参数”，允许切换类型或返回选择其他函数。不得自动选择另一参数、另一 Symbol 或 Demo 目标。

前端筛选不包含完整 Python 签名合法性判断。例如 `f(a=1, b=2)` 中 b 仍符合“普通参数 + 有默认值”的选择条件；移除其默认值可能造成非法顺序，最终由 Validate 返回 `invalid_after_signature`。不自动修改 a 或重排参数。

## 5. ChangePage 的统一交互与签名预览

页面顺序：

```text
目标 Symbol / 实际文件位置
Change Type：新增必填参数 | 删除参数 | 参数重命名 | 改为必填参数
当前类型配置
原始签名（Before） → 草稿修改后预览（Draft After）
校验变更
后端确认的修改后签名（Validated After） / 真实诊断
开始分析
```

保留当前 Tracework 页面和 Motion 外壳。类型选择器采用带短说明的四个原生单选项：桌面可一行或 2×2，窄屏 2×2；配置区域跟随所选类型变化，统一保留目标、签名对照和操作区。

| 类型 | 配置与变化标记 |
| --- | --- |
| 新增必填参数 | 新名称、kind、可选插入位置；`+ timezone` |
| 删除参数 | 选择现有参数；Before 中标记 `− timeout`，After 移除该参数 |
| 参数重命名 | 选择现有参数 + 新名称；`timeout → delay` |
| 改为必填参数 | 选择有默认值的参数；`timeout=30 → timeout`，注明移除默认值 |

标记使用既有改动铜 `#A8432D`，同时显示操作文字 / 符号。只强调本次差异，避免四块同权重装饰卡片。保留 Canvas / Surface / Ink / Border / Accent、既有中英文字体、代码字体和间距。

### 5.1 三种签名来源必须分开

1. **Before**：来自当前 Inspect 目标；Validate 后可显示该响应的 canonical `change_spec.before`。
2. **Draft After**：只做展示用的结构化拷贝转换，持续标注“草稿预览 · 尚未校验”。不发送 before / after 给 API，不计算兼容性，也不设置校验成功状态。
3. **Validated After**：仅来自当前成功响应的 `change_spec.after`，标注“已确认变更 · 后端校验通过”。本机或上传源码均未被修改。

建议新增一个纯展示辅助函数：删除只去掉所选参数；rename 只替换名称；make-required 只清除该参数的展示默认值；其余参数与注解保持。新增预览按照现有契约的参数组末尾 / 显式 `insert_before` 展示，不自动寻找合法位置。其结果不进入核心分析或 API 请求。

继续复用 `formatSignature()` 的分隔符规则，覆盖 `page()` → `page(zone)`、删除最后一个 positional-only / keyword-only 参数及变长参数组合，避免 `page(, zone)` 和多余 `/` / `*`。字段不完整、参数不存在或无法确定插入位置时显示预览不可用，不拼造签名。

不在前端重新实现 Python identifier、keyword、完整参数顺序或兼容性校验；基础空值检查与参数选择可用性足够。尤其不能用只允许 ASCII 的正则拒绝合法中文参数名。后端 rename / make-required 的 NFKC 规范名字以响应为准。

输入改变后已确认签名立即消失。422 保留用户当前输入与真实 `validation.diagnostics`，失败响应中的候选 after 如存在只能标为“未通过”；Analyze 保持禁用。

### 5.2 响应式与交互反馈

- 1440 / 1280px：复用现有工作区，目标、配置与签名对照保留清晰主次；长 Symbol 和路径可折行。
- 768px：类型选择和表单两列或单列，签名对照可以上下排列，不挤压输入。
- 390px：目标 → 类型 → 配置 → Before → Draft After → Validate → Validated After / 诊断 → Analyze，操作可触控，代码仅局部横向滚动。
- 键盘可进入单选组、切换类型、选择参数、编辑和提交；禁用原因、错误与 partial 提示始终可读。
- 沿用轻量状态过渡和 reduced-motion；类型切换不重新挂载顶层 Context，不触发自动 API 请求。

## 6. 四种真实 API payload

继续调用 `POST /api/v1/changes/validate` 和 `POST /api/v1/projects/analyze`。

每次使用原始同一 `File` 构建新的 FormData：`file`、`change`（以下 JSON 字符串）、`expected_fingerprint`（当前 Inspect 的原始 ZIP SHA-256）。浏览器负责 Content-Type boundary；API Client 和 Vite `/api` 代理不变。

### 6.1 新增必填参数

```json
{
  "change_type": "add_required_parameter",
  "target_symbol_id": "utils.format_date",
  "added_parameter": {
    "name": "timezone",
    "kind": "positional_or_keyword"
  }
}
```

可选 `insert_before` 仅属于新增。缺省为当前参数类型组末尾；若 resulting signature 非法，后端拒绝，不自动改位置。旧请求省略 `change_type` 仍按 add 解析，后端无需改动。浏览器不发送 `required`、源码默认值、annotation 或完整签名。

### 6.2 删除参数

```json
{
  "change_type": "remove_parameter",
  "target_symbol_id": "utils.format_date",
  "parameter_name": "timezone"
}
```

### 6.3 参数重命名

```json
{
  "change_type": "rename_parameter",
  "target_symbol_id": "utils.f",
  "parameter_name": "timeout",
  "new_parameter_name": "delay"
}
```

### 6.4 改为必填参数

```json
{
  "change_type": "make_parameter_required",
  "target_symbol_id": "utils.connect",
  "parameter_name": "timeout"
}
```

后三类只发送以上字段；不携带 `added_parameter`、`insert_before`、`parameterKind` 或上一类型的其他字段。HTTP 简化 JSON 与 Core 的完整 ChangeSpec 是两种现有契约，不把内部 `operation` 对象作为新表单字段发送。

### 6.5 成功与错误处理

- Validate 成功：读取 `project_fingerprint`、`change_spec`、`validation`、`coverage`、`diagnostics`。检查当前目标、类型与 operation；rename / make-required 按后端规范名字处理，避免合法归一化被当作响应错误。
- Analyze 成功：读取 Core 报告的 `change`，与当前已校验 Change 的 canonical before / after / operation 对应；保留既有 revision 检查。Analyze 没有顶层 `project_fingerprint`，不新增或要求该字段。
- 旧 add 响应可能只有 `added_parameter`，没有 `operation`。仅该已识别旧类型可按旧结构读取；不能把未知类型或 operation 缺失的非 add 响应解释成新增。
- 422：保留 `validation.valid=false` 与真实 diagnostics，禁止 Analyze。参数不存在、重名、非法新名、已经必填、不支持 kind、非法 after 等均按现有诊断展示。
- 409：使用现有 fingerprint mismatch 重置，保留 File，要求重新 Inspect。
- ZIP / 网络 / 500：继续使用现有安全错误处理；不切换 Mock，不构造零报告。
- partial：允许查看已确定结果，持续说明覆盖不完整；0/0/0 不能等同全项目无影响。

## 7. Report 的最小泛化

只调整顶部 Change 展示与操作文案，不重新匹配影响、Evidence、Explanation，也不按前端草稿重算统计。

| 实际类型 | 报告标题与细节来源 |
| --- | --- |
| add_required_parameter | “新增必填参数”：`operation.added_parameter` 如存在，兼容现有 `change.added_parameter` |
| remove_parameter | “删除参数”：`operation.parameter_name`；原 kind / 默认值取 `change.before` 中对应参数 |
| rename_parameter | “参数重命名”：`operation.parameter_name → operation.new_parameter_name` |
| make_parameter_required | “改为必填参数”：参数名与 `change.before` 的 `has_default/default_source`，例如 `timeout=30 → timeout` |

所有类型的 Before / After 都读取本次 `report.change.before/after`；非 add 的 `added_parameter=null` 是正常响应。缺少操作字段时保留实际签名并提示操作信息不可用，不显示虚构的新参数。

Direct 继续表示 before compatible → after incompatible。Indirect 继续展示 Direct 上游需检查的代表路径。规则与具体失败原因、源码、哈希和中文解释使用本次后端结果；不在前端把 `rule/reason` 统一改写成“新增参数”。

保留 `reportData.js` 的原始索引及 metadata 匹配、unavailable 降级、manual review / pre-existing / unresolved 分区、统计单位和报告替换时的选中项重置。中文解释仍使用现有“中文辅助解释”，不凭配置或 HTTP 200 宣称 DeepSeek 成功。

固定离线 Demo 保留原 add 样例：演示模式明确限制到该配置，其他类型禁用并说明需上传实际项目。四类型真实 E2E 使用后端现有 examples 制作 ZIP，不增加四份伪造的固定分析结果。

## 8. Step 2 测试矩阵

### 8.1 六条真实浏览器主案例

每个项目从实际选择 ZIP 开始，完整执行 Inspect → 选择 Symbol → 类型与配置 → Validate → Analyze → 查看 Evidence / Explanation。真实后端使用 `OPENIMPACT_LLM_PROVIDER=rule`；通过现有 Vite 代理，前端 `http://127.0.0.1:5173`，后端 `http://127.0.0.1:8000`。

| 案例 | 真实 fixture | 目标与操作 | 预期 Direct / 1-hop / 2-hop | Coverage |
| --- | --- | --- | --- | --- |
| A | `examples/signature_change` | `utils.format_date` 新增 timezone | 1 / 1 / 1 | complete |
| B | `examples/parameter_removal` | `utils.format_date` 删除 timezone | 1 / 1 / 1 | complete |
| C | `examples/parameter_rename_keyword` | `utils.f`，timeout → delay | 1 / 1 / 1 | complete |
| D | `examples/parameter_required_missing` | `utils.connect`，timeout 移除默认值 | 1 / 1 / 1 | complete |
| E | `examples/parameter_rename_positional` | 同一 rename，调用纯位置传参 | 0 / 0 / 0 | complete |
| F | `examples/parameter_required_explicit` | 同一 make-required，调用显式传值 | 0 / 0 / 0 | complete |

四个 1/1/1 案例必须查看三条真实证据、相应路径与解释，且操作文字、rule、reason 对应当前类型。E / F 不得带入前一个案例的统计、证据、解释或选中项。fixture 路径与配置已核对；本轮没有执行尚未实现的多类型浏览器流程。

### 8.2 状态与契约测试

| 层级 | 新增覆盖 | 继续保留的关键检查 |
| --- | --- | --- |
| 草稿 / 参数选择 | 四类初始字段；kind 支持矩阵；None / False / 0 / 空字符串；无合格参数；未知类型拒绝 | target 来自真实 Inspect，同名 Symbol 不串线 |
| payload | 四种允许字段精确相等；旧 add 缺省兼容；切类型不混入旧字段 | FormData 原 File、指纹、signal；不设置 multipart Content-Type |
| 草稿预览 | 四类结构化差异；空函数；`/` 与 `*`；保留注解/default 文本；源对象不变；非法位置不自动修复 | 草稿不能解锁 Analyze；Validated After 只来自当前成功响应 |
| reducer / actions | 12 个不同类型之间的有向切换；Symbol 切换重置配置；全部四类 Validate / Analyze 的晚返成功和错误 | cancellation + revision、重复点击、换 ZIP、409、health 独立 |
| 响应一致性 | 同目标但错误 change_type / operation 拒绝；canonical Validate 与 Analyze 一致；合法 NFKC 归一化 | Analyze 不依赖不存在的 fingerprint 字段 |
| 渲染 / 报告 | 四类型标题与 null added_parameter；legacy add；实际 0/0/0；默认值展示；不支持项可见原因 | 安全源码文本、同序 Evidence 匹配、unavailable、计数不重算 |
| Motion / 浏览器 | 切类型或改字段时旧报告退出画面立即失效；快速切换无过期配置；键盘、触控、reduced-motion | 顶层 Context 不重挂、File 不丢失、无重复 API、手机诊断不隐藏 |

异常矩阵还须覆盖参数不存在、rename 同名 / 冲突 / keyword、新增重名、make-required 已必填、`f(a=1,b=2)` 仅改变 b 的非法顺序，以及 positional-only 混合与 keyword-only 合法情况。后端拒绝是预期结果，不能为通过测试更换参数或重排签名。

跨类型结果都回归 partial、star-call manual_review、unresolved、Evidence / Explanation unavailable、422、409、无效 ZIP、网络恢复和安全 500。manual review 与既有问题继续不计入确定 Direct。

Step 2 完成后运行集成工作树中的完整 pytest、`npm run check`、`npm run build`、`git diff --check`；Python 运行时确认 import 指向该工作树，避免 editable install 误测原 main。浏览器结果与受控异常注入分别记录。

## 9. 安全 Git 整合方案

**推荐独立 `integration/multi-change-web`，从审核时最新的 `origin/main` 创建，使用独立工作树。** 不在当前 UI 或 backend feature 工作区直接叠加另一条分支。

按以下顺序，均待负责人审核后执行：

1. 分别审核、提交各自现有未提交成果：backend Phase 6.4；UI 的 Motion、重影修复、统计区。不要把两边内容混进一次提交，也不覆盖当前工作区。
2. fetch 最新 main，记录两个 feature 的最终 HEAD 及干净状态。如果 feature 已通过 PR 进入 main，使用包含该成果的新 main 基线，无需重复合并。
3. 检查目标分支和目录未占用，创建 `integration/multi-change-web` 独立工作树，以最新 main 为基线；原 main 与两条 feature 保留。
4. 优先正常 merge `feature/change-types`，保留历史，使四类型契约、示例与后端回归先成为整合依据。确认四种类型都已包含。
5. 再正常 merge `feature/ui-redesign`，保留已验收 Tracework 展示与业务保护；运行前端基线和后端回归。
6. 在集成分支实施本设计的前端接入；执行六个真实浏览器案例和完整回归后准备 PR，base 为 main，compare 为 integration/multi-change-web。

当前两个已提交分支及未提交文件没有同路径修改交集，文本冲突风险较低。仍存在明确的语义差异：UI 仍按 add 构造请求，而后端已经支持四类型；正常 merge 不会自动完成这项接入。此判断基于当前文件范围，没有执行试合并，不承诺未来 main 更新后零冲突。

如最新 main 引入重叠变更，先列冲突文件及逐段方案，保留后端接口与 Tracework 状态保护，不使用整文件 ours/theirs。源码和示例的换行、SHA-256 基线继续沿用已有跨平台测试；不在此阶段混入历史 `.venv` 清理。

## 10. Step 2 预计修改文件与边界

| 文件 | 预计最小职责 |
| --- | --- |
| 新增 `frontend/src/state/changeDraft.js` | 四分支草稿工厂、参数选择、精确 payload 构造及展示用 draft preview；不分析调用 |
| `frontend/src/state/workflow.js` | 接入草稿工厂与类型切换 / Symbol 重置；保留 File、fingerprint、revision 和已有 formatter |
| `frontend/src/state/actions.js` | 类型切换复用取消入口；Validate / Analyze 的 canonical Change 一致性保护 |
| `frontend/src/pages/ChangePage.jsx` | 统一类型选择与配置、草稿 / 已校验签名与真实诊断 |
| `frontend/src/components/workflow/WorkflowParts.jsx`、`workflow-pages.css` | 安全参数差异展示、类型选择与参数禁用视觉；可按实际复杂度抽取一个纯展示配置组件 |
| `frontend/src/pages/ReportPage.jsx` | ChangeOverview 根据实际 operation 泛化；可抽取纯 `ChangeSummary` 展示，保留 ReportResults |
| `frontend/src/pages/UploadPage.jsx`、`components/AppShell.jsx` | 仅更新支持范围说明，不改导航 / Motion / 上传逻辑 |
| `frontend/tests/changeDraft.test.js`（新增）及既有 workflow / actions / API Client / rendering / motion 测试 | 覆盖本矩阵，保留旧安全断言 |
| `frontend/DESIGN.md`、`frontend/README.md`、`docs/frontend-handoff.md` | 同步本次已审核四类型 UX、启动与验收范围；必要时澄清 api-contract 中遗漏类型的概括句 |

不需要为本次增加依赖、四套页面、四个 Provider、独立 endpoint、四份 Mock 报告或可视化图算法。`api/client.js`、`WorkflowContext.jsx`、`reportData.js`、后端 Core / 公共 API 字段与算法保持原样。

实现允许的状态改动仅服务统一 Change Draft 与失效规则；原始 ZIP、fingerprint、AbortController / revision、Inspect / Validate / Analyze 协议和 Evidence 对应机制继续使用现有能力。历史 UI 改版的状态保护边界继续保留，不借本次接入重写这些能力。

本轮唯一新增文件为本文。React、多类型浏览器实现、分支整合均等待 Step 2 审核。
