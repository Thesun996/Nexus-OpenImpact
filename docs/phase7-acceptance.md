# OpenImpact V1.1：Phase 7.1～7.6 交付验收

## 交付状态与 Git

独立工作树 `Nexus-OpenImpact-multi-domain-changes`，分支 `feature/multi-domain-changes`，业务开发基线 `a5bfb29`。基线包含完整 V1 Web 集成与以下两次获授权的精确文档提交：

- `05cfbcc`：Phase 6.6 三份评测契约/缺口文档。
- `a5bfb29`：Phase 7.0 架构审计。

新业务实现、测试、样例与本验收文档全部保留为未提交修改；暂存区为空。未 Push、Merge main 或创建 PR。原 main / 已有 feature 工作树保持原 HEAD。评测文档和 Phase 7.0 文档内容没有被本轮覆盖。

7.1～7.5 已实现并通过阶段门槛，7.6 已完成自动化、真实 HTTP 和真实浏览器业务回归。当前浏览器工具未提供 reduced-motion 媒体偏好切换能力：该项已通过原自动化偏好/退出策略测试与 CSS 检查，真实浏览器“reduce 已开启”场景需负责人在系统/浏览器设置中补验。对此不宣称已经完成实测。

## Change Domain 与共用基础设施

Function 保留四类原 Operation、Before/After Signature、兼容性、调用图与传播算法。Module 使用独立不可变 `ModuleChangeSpec`、Rename/Remove Operation 与虚拟布局，不构造函数签名。

共享 Scanner、单次 AST 事实、SymbolIndex 文件视图和安全源码读取。Import Resolution、Module Dependency Graph、导入影响评估与投影为 Rename/Remove 共用。模块源码事实通过追加字段采集，原函数、调用与导入字段的处理规则保持。

## 支持范围和导入矩阵

| 场景 | 首版结论 |
| --- | --- |
| 根目录、唯一、名称合法普通 `.py` | 可作为目标和确定依赖参与者 |
| 顶层 `import utils` / `import utils as u` | 绑定唯一受支持项目模块 |
| 顶层 `from utils import f` / alias | f 是明确未重绑定模块级函数时绑定 |
| 包、嵌套、namespace、特殊入口、标准库同名 | 禁用目标或 manual_review/partial |
| 相对、dotted、wildcard、重导出/未知成员 | manual_review/partial，不生成确定边 |
| 条件、try/except、函数/class 内 import | manual_review/partial，不模拟执行 |
| 常见 importlib / `__import__`、exec/eval | 有真实位置的边界诊断，partial |
| 外部、不存在、歧义模块 | unresolved/partial，无确定传播 |

名称校验拒绝非法路径、keyword、Windows 保留名、非规范 Unicode、大小写等价冲突、超长文件名和所有已占用根路径。ZIP 未解压的非 Python 文件/目录以及 `.PY` 也参与目的路径冲突检查。未扩大 Scanner 原 `.py` 范围。

`complete` 限定 `project_root_static`；不证明 Python 任意运行时导入覆盖完整，也不证明初始化会成功。

## Direct / Indirect 与图

每个 Import 成员保留相对文件、起止行列、alias、原语句、scope、稳定引用 ID 与解析状态。模块边方向是 importer → target，与函数 caller → callee 图分开。

Direct 仅在 before 可唯一确认项目目标、after 因本次虚拟布局丢失旧项目模块名时产生，certainty 为 `definite_project_reference_break`。它证明受支持范围的项目引用断裂，不承诺运行时必然失败。原 unresolved/manual_review 和 resolution_improved 不成为种子。

反向传播从 Direct 来源模块最多两层。循环通过 visited 限制；每个 seed/上游留一条最短代表路径；上游模块按 Symbol 去重并保留多个 Direct 来源。Direct 来源优先，不重复计为 Indirect。路径末尾保留实际 Direct 引用。被拟删除的来源、自导入与删除来源的上游贡献排除，避免分析已不再存续的源码。

## Evidence、解释与报告契约

Import Evidence 来自真实相对源码位置，包含源码片段、原文件字节 SHA256、真实 import_expression、rule/reason、Direct 来源和路径。源码缺失、位置无效、哈希变化或解释异常返回 unavailable，保留报告主体。

模块解释只使用结构化证据和规则，风险 unknown；不调用 DeepSeek，也不让模型决定影响。

Function 的原 `schema_version=1` 报告保持。Module 单独使用 `(change_domain=module, report_kind=module_impact, schema_version=1)` 命名空间，不采用未经批准的全局 v2。

模块字段为 `import_assessments`、`import_impacts`、`module_indirect_impacts`、`evidences`、`explanations`、`summary`、`counting_units`、`coverage`、`diagnostics`。Direct 单位是 Import 引用，Indirect 单位是去重上游模块，不伪装为函数参数不兼容。

证据顺序是 Direct 后接 Indirect；解释同序且带 evidence_reference。React 二次检查 ID、类型/目标、位置、真实路径与 Direct 末端；不匹配时显示 unavailable，不借用相邻项。

## API / React 接入

原 Inspect / Validate / Analyze 路径不变，ZIP 安全验证、指纹和临时目录清理保持。Inspect 追加 `module_inventory`、`module_coverage`、`module_diagnostics`，原七字段逐项保持。旧 Function 请求缺省仍可用；显式 function 也支持。

Module payload：

```json
{"change_domain":"module","change_type":"rename_module","target_module_id":"utils","new_module_name":"formatting"}
```

```json
{"change_domain":"module","change_type":"remove_module","target_module_id":"utils"}
```

Tracework 目标页新增领域与真实模块候选；不支持候选保留禁用原因。配置页提供重命名名称或删除分析确认，区分草稿与后端已确认布局。模块报告使用独立统计、路径、Evidence 和规则说明。

状态继续使用原 File、Inspect 指纹、revision、AbortController 和校验快照；切换领域/目标/操作/输入使旧 Validate、Analyze、Report 失效，晚响应不覆盖。API Client、原 changeDraft/reportData 匹配、Motion System 未修改。

## 真实验收

同一新工作树：独立 editable Python 环境、rule Uvicorn `127.0.0.1:8011`，Vite `127.0.0.1:5177` 代理到 8011。未使用已有 8000/5173 服务充当当前验收。最终服务均为本轮源码，未设置 PYTHONPATH。

| 实际浏览器完整流程 | Direct / 1-hop / 2-hop | Coverage |
| --- | --- | --- |
| add required：format_date + timezone | 1 / 1 / 1 | complete |
| remove parameter | 1 / 1 / 1 | complete |
| rename keyword | 1 / 1 / 1 | complete |
| make required，省略参数 | 1 / 1 / 1 | complete |
| rename positional | 0 / 0 / 0 | complete |
| make required，显式传值 | 0 / 0 / 0 | complete |
| rename module utils → formatting | 1 / 1 / 1 | complete |
| remove module utils | 1 / 1 / 1 | complete |
| module_no_impact | 0 / 0 / 0 | complete |
| module_partial，SyntaxError + 条件/未知导入 | 1 / 1 / 1 | partial |
| 相对 + 动态导入边界 | 0 / 0 / 0；人工检查 2 | partial |

浏览器已验证非法名称 422、409 后清空过期项目索引/报告、Domain 切换后空报告，原 ZIP 保留。409 浏览器场景使用忽略目录内的本地验收转发器只改变上传 ZIP 字节，真实 Backend 校验产生 409；没有 Mock 错误响应。正常业务全部直连 Vite 5177 → Backend 8011。

1440 / 768 / 390px 实际检查：报告、路径、证据和配置可操作，页面 scrollWidth 不超过视口；诊断不隐藏。当前验收 Tab 未发现应用 error 日志。真实 reduce 偏好切换的工具限制见交付状态。

最终真实 HTTP 重跑十个仓库 Demo：三步均成功，同原始 ZIP SHA256，错误 fingerprint 拒绝409；CLI 与 HTTP 报告逐字段一致，六个原函数 CLI 与预先保存基线逐字段一致。额外独立 HTTP 边界项目已测试；失败后无新增临时目录残留。安全 500 与并发隔离由完整回归测试覆盖。

## 测试、风险和后续

最终测试数字与文件清单见本文件末尾收束记录。没有新增生产依赖、删除安全测试或修改生产指纹规则。旧 Inspect 严格字段集合测试仅追加三个模块字段，原字段样例比较保持；其余原预期未改。

尚不分析包初始化、完整 re-export、任意运行时绑定、sys.path/import hook、第三方旧同名提供者、函数体执行和复杂动态导入。上游传播表示建议检查。模块 Evidence unavailable 和解释失败已测试，真实 UI 不通过 Mock 制造正式结果。

阶段复核发现并修复两类实际问题：删除来源/自导入误计，以及未解压 `.PY` 占用路径的 Windows 冲突。初次部分新测试失败属于错误测试定位/子进程编码或旧诊断兼容，均在开发日志说明，未放宽确定性。

Phase 6.6 仍缺成员 B 的独立人工 Benchmark，本轮只报告功能测试，不报告准确率。建议后续人工标注包/同名/来源删除/动态与多路径案例，再评估扩展支持；不直接从 Demo 输出生成 Ground Truth。

本实现具备 V1.1 本地交付与负责人代码审核条件。合并/发布前应补验真实 reduce 偏好；本轮停止开发，等待统一审核。

临时验收服务与转发器已停止；原有本地服务未触碰。实际截图、完整 Diff 和 HTTP 验收记录保留在忽略目录，可由负责人复查。

## 最终测试与文件清单

- Backend：694 passed、1 skipped、1 warning、7 subtests passed，40.50s；净新增97项。
- Frontend：162 passed；净新增21项；npm run check / npm run build 成功。
- git diff --check 通过，暂存区为空；保护文件检查通过。
- 当前业务 Diff：22个原有文件修改，51个新文件。
- 其他五个工作树干净、原 main HEAD 为3a5a582；没有额外 .venv / 环境 / 媒体文件进入差异。
- 完整 Diff 和机器验收记录位于忽略目录 `.local/phase7-final.diff`、`.local/phase7-proof`，不进入提交。

| 状态 | 仓库相对文件 |
| --- | --- |
| M | `PROJECT.md` |
| M | `README.md` |
| M | `docs/api-contract.md` |
| M | `docs/api-samples/inspect-response.json` |
| M | `docs/frontend-handoff.md` |
| M | `frontend/src/components/AppShell.jsx` |
| M | `frontend/src/components/WorkflowSteps.jsx` |
| M | `frontend/src/components/report/report.css` |
| M | `frontend/src/pages/ChangePage.jsx` |
| M | `frontend/src/pages/FunctionSelectPage.jsx` |
| M | `frontend/src/pages/ReportPage.jsx` |
| M | `frontend/src/pages/UploadPage.jsx` |
| M | `frontend/src/state/actions.js` |
| M | `frontend/src/state/workflow.js` |
| M | `frontend/vite.config.js` |
| M | `src/openimpact/__main__.py` |
| M | `src/openimpact/analysis/ast_parser.py` |
| M | `src/openimpact/analysis/models.py` |
| M | `src/openimpact/analysis/symbol_index.py` |
| M | `src/openimpact/api.py` |
| M | `src/openimpact/repository/zip_inspector.py` |
| M | `tests/test_frontend_readiness.py` |
| ?? | `docs/api-samples/module/analyze-response.json` |
| ?? | `docs/api-samples/module/inspect-response.json` |
| ?? | `docs/api-samples/module/validate-response.json` |
| ?? | `docs/module-changes.md` |
| ?? | `docs/phase7-acceptance.md` |
| ?? | `docs/phase7-development-log.md` |
| ?? | `examples/module_no_impact/change.json` |
| ?? | `examples/module_no_impact/page.py` |
| ?? | `examples/module_no_impact/utils.py` |
| ?? | `examples/module_partial/broken.py` |
| ?? | `examples/module_partial/change.json` |
| ?? | `examples/module_partial/dashboard.py` |
| ?? | `examples/module_partial/page.py` |
| ?? | `examples/module_partial/report.py` |
| ?? | `examples/module_partial/utils.py` |
| ?? | `examples/module_removal/change.json` |
| ?? | `examples/module_removal/dashboard.py` |
| ?? | `examples/module_removal/page.py` |
| ?? | `examples/module_removal/report.py` |
| ?? | `examples/module_removal/utils.py` |
| ?? | `examples/module_rename/change.json` |
| ?? | `examples/module_rename/dashboard.py` |
| ?? | `examples/module_rename/page.py` |
| ?? | `examples/module_rename/report.py` |
| ?? | `examples/module_rename/utils.py` |
| ?? | `frontend/src/components/workflow/DomainSelector.jsx` |
| ?? | `frontend/src/pages/ModuleChangeView.jsx` |
| ?? | `frontend/src/pages/ModuleReportView.jsx` |
| ?? | `frontend/src/pages/ModuleSelectView.jsx` |
| ?? | `frontend/src/pages/moduleReportData.js` |
| ?? | `frontend/src/state/moduleDraft.js` |
| ?? | `frontend/tests/fixtures/module-responses.json` |
| ?? | `frontend/tests/moduleRendering.test.js` |
| ?? | `frontend/tests/moduleWorkflow.test.js` |
| ?? | `src/openimpact/analysis/change_domain.py` |
| ?? | `src/openimpact/analysis/import_resolver.py` |
| ?? | `src/openimpact/analysis/module_change.py` |
| ?? | `src/openimpact/analysis/module_facts.py` |
| ?? | `src/openimpact/analysis/module_graph.py` |
| ?? | `src/openimpact/analysis/module_impact.py` |
| ?? | `src/openimpact/analysis/module_pipeline.py` |
| ?? | `src/openimpact/analysis/module_report.py` |
| ?? | `src/openimpact/analysis/module_syntax.py` |
| ?? | `src/openimpact/explanation/module_fallback.py` |
| ?? | `src/openimpact/reporting/import_evidence.py` |
| ?? | `src/openimpact/reporting/source_reader.py` |
| ?? | `tests/analysis/test_module_change.py` |
| ?? | `tests/analysis/test_module_impact.py` |
| ?? | `tests/analysis/test_module_imports.py` |
| ?? | `tests/analysis/test_remove_module.py` |
| ?? | `tests/test_module_api.py` |
