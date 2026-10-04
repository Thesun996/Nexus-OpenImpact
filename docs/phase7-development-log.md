# Phase 7 开发记录

日期：2026-10-04（Asia/Shanghai）。新工作树：`Nexus-OpenImpact-multi-domain-changes`；分支：`feature/multi-domain-changes`。

## 基线与保护

- V1 Checkpoint：`1cd8480`，四种签名变化及完整 Tracework Web。
- 已授权文档 Checkpoint：`05cfbcc`（Phase 6.6 三份评测文档）、`a5bfb29`（Phase 7.0 架构审计）。精确暂存，无缓存、截图或环境文件。
- 新工作树从 `a5bfb29` 创建，原 main 和其他 feature 工作树保持不变。新业务成果不提交、不推送、不合并 main。
- 四种函数签名的 Operation / Direct / Indirect / Evidence / Report v1 保持。模块使用独立事实、虚拟布局与报告，不伪造签名。
- 模块首版目标与确定图参与者仅为根目录普通 `.py`；其他导入保留诊断/partial。分析不执行或修改用户源码。
- 安装初次受到宿主 SOCKS 代理缺依赖及共享 npm cache 权限影响；仅为当前安装进程清除代理变量、使用工作树 `.local/npm-cache`，不修改用户全局配置。

## 阶段状态

| 阶段 | 状态 | 测试 / 证据 |
| --- | --- | --- |
| 7.1 Foundation | 完成 | 新增 27 项模型测试；完整 Backend 624 passed、1 skipped、1 warning，7 subtests；44.38s |
| 7.2 Import / Graph | 完成 | 专项 88 passed；完整 Backend 646 passed、1 skipped、1 warning；48.08s。Frontend 141 passed，build 成功 |
| 7.3 Rename | 完成 | 专项 125 passed；完整 Backend 659 passed、1 skipped、1 warning；43.23s |
| 7.4 Remove | 完成 | 专项 75 passed；完整 Backend 672 passed、1 skipped、1 warning；48.82s |
| 7.5 API / React | 完成 | HTTP 专项 25 passed；Frontend 162 passed + build。后端完整 686 passed、1 skipped；随后发现并修复来源删除边界，专项 41 passed |
| 7.6 最终验收 | 已收束，真实 reduce 偏好待人工补验 | Backend 694 passed、1 skipped、1 warning，7 subtests；40.50s。Frontend 162 passed、build 成功。真实 HTTP / 浏览器结果见 phase7-acceptance.md |

## 契约决策

旧 Function 请求缺省域，保留原 schema_version=1 与字段。模块显式 `change_domain=module`，独立模块报告带 domain/version，不将导入数量填入函数调用字段。规则解释不调用外部模型。新域输出和消费者必须一起测试。

## 7.1 实施记录

新增 `analysis/module_facts.py`、`analysis/module_change.py`、`tests/analysis/test_module_change.py` 及本日志。模块目录从既有索引/Scanner 生成，限定根目录普通文件；记录相对路径、源码 SHA256、可选状态与原因。不可变 Rename/Remove Operation 及 ModuleChangeSpec 校验目标、名称、NFKC、标准库/特殊文件、冲突和快照；虚拟目录不改源码。

独立 Python 环境 editable install 成功，`openimpact.__file__` 指向新工作树；未设置 PYTHONPATH。六份原始函数报告完整保存为忽略目录 `.local/v1-report-baselines.json`，用于最终逐字段比较。Frontend 尚未修改；安装后发现 Rolldown Windows 可选原生依赖缺失，先修复安装环境，不改测试和锁文件。

## 评测

Phase 6.6 尚缺独立人工 Benchmark；本轮 Demo 和专项测试只证明功能，不能作为准确率或独立 Ground Truth。

## Skill 应用记录

- 已完整读取本地 `find-skills` 和 `frontend-design` 指南。按 find-skills 要求查阅 [skills.sh 目录](https://skills.sh/)，现有 frontend-design 足以覆盖本轮展示任务，未安装新 Skill 或声称执行外部 CLI。
- frontend-design 用于 7.5 的 Domain 控件、模块文件变化和 Import Evidence 阅读层次；沿用 DESIGN.md 的六色/字体/Tracework，不另建视觉主题或增加装饰动效。

## 7.2 实施记录

新增 `module_syntax.py`、`import_resolver.py`、`module_graph.py` 及 `test_module_imports.py`；在旧 models/ASTParser 中追加模块事实，不改变旧 functions/imports/calls。SymbolIndex 新增逐文件事实视图，保留歧义文件用于诊断。

引用按文件/语句序号/成员序号唯一标识，保留真实起止行列与表达式；直接顶层四种 import 形式按唯一根模块解析。条件/函数/class/相对/wildcard/package/未知成员保守处理；常见动态导入和 exec/eval 仅记录人工检查诊断。模块图只纳入确定项目边，不使用按函数图聚合。

首次专项测试 87 passed、1 failed：新 re-export 测试错误地以列表第二项代指 report.py，实际该项是 utils.py 的合法 import。已改为按真实所属文件选取，保留 manual_review 的原语义断言；没有放宽解析规则。

## 7.3 实施记录

新增 module_impact / module_pipeline / module_report / change_domain、Import Evidence、安全读取适配器和模块规则解释，新增 module_rename Demo。Rename/Remove 共用前后虚拟目录和导入解析，Direct 仅来自 before 明确项目目标→本次布局使其消失，其他状态不传播。反向 BFS 最多两层，每 seed 留最短真实路径，上游模块去重。

Module Report 使用独立的 `(change_domain=module, report_kind=module_impact, schema_version=1)` 命名空间。Function schema_version=1 完全保留；消费者必须先识别 domain/kind。未采用此前待批准的全局 v2 升级。模块报告使用 import_impacts / module_indirect_impacts / 独立统计单位，证据与规则解释按 finding ID 同序关联；Evidence 失败不会破坏报告。模块解释直接接收结构化 ImportEvidence 并复用 ExplanationResult，未为暂时没有模型接入的域创建 Provider 抽象。

首次专项测试 123 passed、2 failed，均为新 CLI 预读替换了旧错误文字。已恢复无法读取/无效 JSON 时由原 change_file loader 产生旧诊断；没有修改原测试或放宽错误处理。

## 7.4 实施记录

Remove 完全使用 7.3 的共享虚拟投影/导入 assessment/Graph/传播/Evidence，生产引擎无需新增删除分支。新增 `test_remove_module.py`，以及 module_removal / module_no_impact / module_partial Demo。后者含有刻意 SyntaxError、条件导入与未知外部目标，属于只读分析 fixture，不执行。

首次专项 74 passed、1 failed，发现显式 domain 的重复 JSON key 可将 module 覆盖为 function。已对所有显式 domain 配置进行重复字段拒绝；缺省旧 Function 请求仍保留原解析策略。此修复保留了原拒绝断言。

## 7.5 中间回归与语义复核

第一次完整 API 回归 683 passed、3 failed：两项新 CLI 测试的 UTF-8 解码与 Windows 子进程编码不一致，已显式使用 -X utf8；一项旧 Inspect 测试固定七个键，已在严格键集合中追加三个模块字段。旧七字段和旧样例逐项比较完全一致，原 fingerprint 断言及安全测试保持。复验 Backend 686 passed、1 skipped；Frontend 162 passed、build 成功。

真实 HTTP 新 Module 三步链路 1/1/1 complete，采集 docs/api-samples/module 与前端消费者 fixture。真实浏览器原六个函数案例全部符合基线，新模块重命名/删除/零影响/partial 与相对动态导入已实测。浏览器自动坐标点击在进入过渡中两次未触发 submit，状态没有错误请求；等待可见状态后鼠标或键盘 Enter 均完成，未修改原 Motion System。

循环审查发现新 Remove 结果会把拟删除的来源文件算为上游，且自导入也可能成为 Direct。已让共享虚拟布局返回 importer_removed/not_applicable，仅存续来源进入依赖图；没有新增独立删除分析引擎。原新增循环测试的单边计数覆盖不足，替换为真实存续 a/b 循环并显式断言被删除来源排除，另补自导入零结果测试。需复验后进入最终门槛。

## 7.6 最终收束（2026-10-05）

删除来源修复后完整 Backend 687 passed、1 skipped。随后补齐规范名称长度/保留名大小写和 Inventory 读取失败边界，完整 692 passed、1 skipped。最终检查发现未解压的 `.PY` 文件仍可能占用 Windows 目的路径：ModuleInventory 与 ZIP 已验证条目的占用名现在按扩展名大小写统一，只用于冲突检查，不扩大原 Scanner；增加本地和 API 回归两项。最终 Backend **694 passed、1 skipped、1 warning、7 subtests passed，40.50s**；Frontend **162 passed**，`npm run check` 和独立 `npm run build` 均成功。

新测试净增 Backend 97、Frontend 21。旧 Function 六份 Demo 报告与修改前基线逐字段一致，最终十个仓库 Demo CLI/HTTP 也逐字段一致。HTTP 均使用同一原始 ZIP 指纹三步提交，409 与危险 ZIP 拒绝保持，临时目录未残留；最终 `.PY` 冲突真实 HTTP 返回 422/module_name_conflict。临时验收脚本第一次误以为旧 Function Analyze 含 fingerprint 字段，已让脚本核对 Inspect/Validate 指纹及 Module Analyze 字段，未修改生产契约。

真实同树 rule 后端 8011 / Vite 5177 完成六 Function + Rename/Remove Module + 零影响 + partial + 相对/动态边界浏览器场景，另实测 422、真实指纹变化导致409、Domain 切换后报告清空。1440/768/390 宽度无页面横向溢出；手机配置/校验/分析可操作，证据与解释同步，应用控制台无 error。截图/HTTP 记录/转发器/录屏素材仅在 `.local/phase7-proof` 等忽略目录，未暂存。

原 reduced-motion 偏好订阅/退出策略测试与 CSS 规则均通过；当前 CUA 浏览器仅支持视口/可见性，没有媒体偏好模拟能力。无法执行真实 reduce 开启场景，已明确记录人工补验项，未更改用户系统设置或假称完成。

完整支持边界、契约、真实样例、文件清单与交付判断见 `module-changes.md` 和 `phase7-acceptance.md`。新业务成果不 Commit，待负责人统一审核。

最终 Git 审计：22 个原文件修改、51 个新文件；完整可解析 Diff 保存 `.local/phase7-final.diff`，覆盖全部未跟踪新文件。暂存区为空，其他五个工作树干净；新增差异未包含密钥或本机目录、环境/缓存/媒体。验收临时后端、Vite 与指纹故障转发器已停止，原有 8000/5173 服务未触碰。
