# V1.1 模块变更：实现与接入契约

本能力分析拟定的模块布局变化，不执行源码，不真实重命名、删除文件。四种函数签名变更继续使用原 Function Report v1、兼容性算法与 API。

## 支持范围

项目根目录下、名称规范且可唯一识别的普通 `.py` 模块。特殊入口、`__init__.py`、包、嵌套或 namespace 模块、大小写/NFKC 歧义、标准库同名目标不提供确定性模块变更。未知外部依赖保持 unresolved，不按同名字符串推断项目归属。

| 导入形式 | 项目根内唯一普通模块 | 首版处理 |
| --- | --- | --- |
| `import utils` / `import utils as u` | 是 | 顶层直接语句可解析 |
| `from utils import format_date [as fd]` | 是，成员是明确且未重绑定的模块级函数 | 可解析，alias 不改变模块目标 |
| from import 常量、class、重导出或未知成员 | 不完整 | manual_review |
| 相对、dotted、包、wildcard 导入 | 不完整 | manual_review，partial |
| 条件、try/except、函数、class 中导入 | 不模拟执行环境 | manual_review，partial |
| `__import__`、常见 importlib 调用与别名、exec/eval | 不静态绑定目标字符串 | 源码位置诊断，partial |
| 外部/不存在/歧义目标 | 未确认 | unresolved，partial，无确定传播边 |

`complete` 仅指 `analysis_scope=project_root_static` 的受支持静态范围。无法证明运行时 `sys.path`、已安装第三方提供者、模块初始化成功、import hook 或任意反射行为。任意函数对象转发的动态导入不保证全部识别；不能把 complete 理解为全 Python 运行时覆盖。

## 架构与判定

- `ModuleInventory` 从 Scanner / 已解析索引得到相对路径、源码哈希、解析/可选状态；ZIP 未解压的目录和非 Python 根条目仍参与名称冲突检查。
- 不可变 `ModuleChangeSpec` 使用独立 Rename / Remove Operation。它没有函数签名，不复用 `added_parameter`。
- VirtualModuleLayout 保存虚拟名称到原源码身份的映射；前后使用同一份 AST 事实与解析器。移除来源自身的引用成为 `not_applicable/importer_removed`，不会生成 Direct 或作为上游传播模块。
- ImportReference 每个 import 成员保存真实文件、起止行列、语句/成员序号、alias、表达式、稳定 reference_id。独立 Module Dependency Graph 保存 `importer → target`。
- Direct：before 唯一绑定项目目标，after 因本次投影丢失旧模块名称。结果为 `definite_project_reference_break`，限定项目静态引用，不保证运行时一定失败。
- Indirect：从确定 Direct 的来源模块反向最多传播两层。每 seed/模块保留一条最短代表路径；上游模块去重，保留多个 seed 来源。Direct 来源模块优先，不重复计为 Indirect。循环有限遍历；删除的来源模块不参与传播。
- Pre-existing unresolved、resolution_improved、manual_review、dynamic 诊断不成为确定 seed。

## 现有 HTTP 工作流

端点与上传限制保持：`POST /api/v1/projects/inspect`、`POST /api/v1/changes/validate`、`POST /api/v1/projects/analyze`。multipart 文件字段 `file`；后两个端点另有 `change` JSON 文本和可选 `expected_fingerprint`。使用同一原始 ZIP 重复提交，指纹始终是上传完整原始字节的 SHA256。请求结束，包括失败，删除隔离临时目录。所有同步工作保留在线程池中完成。

Inspect 追加三个字段，原七字段与原 Function coverage/diagnostics 保留：

- `module_inventory`: `{analysis_scope, modules, occupied_names}`。候选项含 `module_id, file, source_hash, parse_status, selectable, reason, kind`。
- `module_coverage`: 模块领域覆盖与范围说明；与 Function coverage 分开。
- `module_diagnostics`: 解析失败、不支持模块、未解析/人工检查导入、动态语法诊断。

重命名配置：

```json
{"change_domain":"module","change_type":"rename_module","target_module_id":"utils","new_module_name":"formatting"}
```

删除配置：

```json
{"change_domain":"module","change_type":"remove_module","target_module_id":"utils"}
```

名称是单一 Python 标识符，不含扩展名、路径、keyword、Windows 保留名称或非规范 Unicode；拟定文件名 UTF-8 长度最多 255 字节。新旧名称须不同，拒绝仅大小写变化、文件/目录占用与标准库冲突；未分析的 `.PY` 条目也参与跨平台路径占用检查。未知字段、重复 JSON key、错误 domain 均拒绝。原 Function 请求不指定 change_domain 时默认 function；显式 function 也可用，四类原配置保持。

Validate 成功保留 `project_name, project_fingerprint, coverage, change_spec, validation, diagnostics`，模块响应追加 `change_domain=module`。change_spec 含 domain/type/target/operation、before 模块身份、after 虚拟文件或 null、范围和 `modifies_source=false`。源码快照身份由 before.source_hash 保留。

| 错误 | 状态 / 结构 |
| --- | --- |
| 配置、目标、不支持布局、非法/冲突名称 | 422，`validation.valid=false` + code/message，change_spec 可为 null |
| JSON 无效/重复字段/domain 不支持 | 422，同既有配置错误格式 |
| 指纹不一致 | 409，`error:{code:"fingerprint_mismatch",message}`，不进入分析 |
| 非 ZIP / 危险路径 / 重复解压目标 | 400，原 ZIP error |
| 大小/数量/压缩比限制 | 413 |
| 不支持压缩 | 415 |
| 没有 Python 源码 | 422 |
| 部分解析失败 | 200 partial，有真实已确认结果与诊断；不宣称无其他影响 |
| 内部分析异常 | 500，`error:{code:"analysis_failed",message}`，不暴露堆栈或临时路径 |

## 独立 Module Report v1

首先检查 `change_domain="module"` 与 `report_kind="module_impact"`，再检查 `schema_version=1`。版本属于该领域命名空间；旧 Function schema_version=1 不改变，不使用未经批准的全局 v2。模块结果没有函数 `direct_impacts` / `indirect_impacts` 字段。

| 字段 | 语义 |
| --- | --- |
| change / validation | 完整模块操作、原快照/虚拟布局、有效性 |
| summary.direct_import_count | 确定受影响的真实 import 成员引用数量 |
| summary.indirect_1hop_module_count / indirect_2hop_module_count | 按最短距离分类并去重的上游模块数 |
| summary.manual_review_count / unresolved_import_count | 人工检查导入+动态语法诊断 / 未绑定引用数，不计 Direct |
| counting_units | Direct=import_reference；Indirect=unique_upstream_module |
| import_assessments | 同一引用的 before/after 解析状态、effect、reason |
| import_impacts | finding_id、目标/受影响模块、真实位置、前后解析、certainty/rule/reason |
| module_indirect_impacts | impacted_module_id、hop/distance、多个 source_direct_impacts 与路径 |
| evidences | 同序真实位置、import_expression、源码片段、文件原字节 SHA256、rule、reason、路径、status/diagnostics |
| explanations | 同序 evidence_reference、provider=rule、status、ExplanationResult 或 null |
| coverage / diagnostics | 范围与遗漏，不确定结果不可升级 |

证据顺序为 import_impacts 后接 module_indirect_impacts；前端再次检查 finding ID、target/type、源码位置、代表路径和 Direct seed 位置。元数据不匹配显示 unavailable；不能借用其他记录。源码按纯文本渲染。Evidence 或解释失败保留影响结果及 unavailable。模块解释目前只使用确定性规则，风险 unknown；不调用外部模型。

真实本地 HTTP 样例：[Inspect](api-samples/module/inspect-response.json)、[Validate](api-samples/module/validate-response.json)、[Analyze](api-samples/module/analyze-response.json)。这些样例不作为独立 Benchmark Ground Truth。

## Web 与命令行

上传后在目标选择页切换 Function / Module；模块候选保留 disabled 原因。变更页区分草稿布局与后端已校验布局。删除前需确认“只分析、不修改文件”。切换领域、目标、操作或输入会取消旧请求、增加 revision、清除 Validate/Analyze/Report；同一原始 File 和 Inspect fingerprint 保留。

```sh
python -m openimpact analyze examples/module_rename --change examples/module_rename/change.json --format json
python -m openimpact analyze examples/module_removal --change examples/module_removal/change.json
```

后端按既有方式启动并设置 `OPENIMPACT_LLM_PROVIDER=rule`。Vite 默认 `/api` 代理仍为 `http://127.0.0.1:8000`；可通过启动进程环境 `OPENIMPACT_API_TARGET` 指向独立本地验收端口。无需开放额外 CORS，未新增依赖。

## 后续评测

专项功能测试覆盖模型、导入、投影、Direct/Indirect、真实位置、HTTP、状态竞态与页面消费。独立模块 Benchmark 应由人工分别标注存续 Import sites、边界分类与静态路径，覆盖来源删除、自导入、同名、pkg、动态、cycle、多 seed 等；本轮不报告准确率，也不伪造独立人工标注。
