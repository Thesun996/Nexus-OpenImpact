# Nexus OpenImpact 当前项目状态

> 更新日期：2026-10-24（Asia/Shanghai）
> 整合状态：项目库、任务及报告历史已经通过 PR #2 合并 main；本文随当前源码维护。
> 本文记录当前代码能力及可复核验收结果；设计草案不代表已实现功能。

## 当前状态

项目具备 Python 静态影响分析、React 工作台、本地 SQLite 报告历史、可复用的项目快照库和本地分析任务基础。已接通“保存 ZIP → 刷新后从项目库打开 → 选择目标 → 校验 → 创建分析任务 → 查看任务进度 → 查看证据报告”的真实业务流程。

当前仍是本机工作台：登录是演示入口，版面保留但不做真实认证；没有真实用户表或账号隔离。项目库快照和直接上传 ZIP 的分析都会使用本地任务创建与轮询；直接上传的 ZIP 会在开始分析时自动保存为本机快照。任务已由独立本机 Worker 领取和执行，但仍不是生产级分布式队列。

## 已具备能力

- Python ZIP 的安全导入、AST 解析、明确符号/调用关系及覆盖诊断，不执行上传源码。
- 函数参数新增、删除、重命名、可选改必填；已有模块及公开符号变更能力保持原范围。
- Direct、1-hop、2-hop 影响、人工检查、未解析调用、源码位置、证据及中文解释。
- 代码关系图：基于 Python AST、符号索引和显式调用关系展示项目函数节点、调用边、文件位置及未解析调用诊断；不把无法证明的动态调用画成确定关系。
- 上传页“保存并读取项目”：保存项目和 ZIP 快照，进入目标选择。
- 未提前保存的 ZIP 在点击“开始分析”时会自动保存为本机快照，再创建分析任务；分析完成后可从项目库和任务页继续查看。
- 项目库“使用此快照分析”：直接使用已保存快照，刷新后无需重新上传 ZIP。
- 同名项目重复保存会追加为新的快照版本，项目库显示最新快照并保留旧版本列表。
- 项目库支持删除本机项目和单个快照；未被其他记录引用的 ZIP 快照文件会随之清理。
- 非默认源码根目录随快照保存并复用；每次读取核对大小、文件位置和指纹。
- 快照模式下的源码查看、报告追问及报告保存；追问遵循已有模型配置和规则回退。
- 本机报告历史保存、读取、筛选、分页和删除；快照来源 ID 保存在完整报告中。
- 历史报告可通过“打开来源项目”重新读取对应快照；旧报告无来源信息时不猜测关联项目。
- 当前报告和历史报告详情均可下载完整 JSON，便于交接、留档和复核证据。
- 本地分析任务基础：可基于已保存快照创建任务、记录 queued/running/succeeded/failed 状态，并在成功后保存报告 ID。
- 独立本机 Worker：API 只创建 queued 任务；Worker 以 SQLite 租约原子领取任务，执行完成时只允许持有该租约的 Worker 写入结果，过期租约可被后续 Worker 恢复领取。
- 项目库快照“开始分析”会创建或复用当前任务、轮询状态、读取已保存报告，并避免重复点击创建多个任务。
- 任务页可查看任务列表、状态详情和成功任务对应的报告证据；支持按状态及目标、变更、任务 ID 筛选，失败任务保留后端诊断信息，并可手动重新执行为一项新的任务。
- 直接读取 ZIP 和独立演示流程继续可用。

## 尚未实现

- 真实登录、用户表、会话和账号级数据隔离。
- 通用知识图谱：当前关系图只覆盖 V1 范围内的 Python 模块级函数和静态可解析调用，不覆盖类、变量、运行时依赖或外部服务。
- 自动快照保留策略和账号级版本管理。
- 自动重试、生产级任务队列或多机部署。
- 真实 Benchmark 数据及人工 Ground Truth；当前已具备哈希校验的评测 Runner，等待独立标注数据接入。
- 团队权限、公开部署及生产代理配置。

项目库默认保存在 `.openimpact/openimpact.sqlite3` 和 `.openimpact/snapshots/`，不应提交到 GitHub。当前没有为报告表添加项目关联列；来源 ID 位于 report JSON。

## 本地启动

Windows 推荐统一入口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider deepseek -PromptKey
```

可用 `-Check` 只检查环境，规则测试使用 `-Provider rule`，自动启动探测后退出使用 `-SmokeTest`。默认端口为 8000 / 5173，实际模型模式、源码路径及 API / Worker 共用存储配置会明确显示。依赖准备、端口调整、日志及停止方法见 [Windows 统一启动说明](local-start.md)。以下分终端命令保留用于手工规则测试。

在仓库根目录启动后端（Python 3.11+，已安装项目依赖）：

```sh
OPENIMPACT_LLM_PROVIDER=rule python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

另开终端运行本机任务 Worker：

```sh
OPENIMPACT_LLM_PROVIDER=rule python -m openimpact.worker
```

两个进程必须使用相同的 `OPENIMPACT_DB_PATH`、`OPENIMPACT_SNAPSHOT_DIR`；不设置时都会使用 `.openimpact/`。Worker 可用 `--once` 只处理一项排队任务。

macOS 下可直接使用仓库脚本启动，避免误用 Conda Python：`./scripts/run-local-api.sh`、`./scripts/run-local-worker.sh` 与 `./scripts/run-local-frontend.sh`。前端默认代理到 API 的 `127.0.0.1:8000`。

另一个终端进入 `frontend`：

```sh
npm run dev -- --host 127.0.0.1 --port 5173
```

浏览器打开 `http://127.0.0.1:5173/`。Vite 使用 strictPort，端口被占用时会报错，不会自动换端口。

这些是本地开发服务，服务退出后需要重新启动。更新后端代码后需要重启后端，避免浏览器连接旧版本。不要用普通静态服务器直接打开 React/Vite 源码。

## 当前检查结果

2026-10-15 当前回归：

- 完整后端：`1135 passed, 3 skipped, 1 warning, 7 subtests passed`。真实 HTTP 测试在允许本地端口绑定的环境中运行通过。
- 前端：`npm run test`，274 项通过。
- 前端构建：`npm run check` 中的生产构建通过；本次产物未触发 500 kB chunk 提醒。
- 本地启动脚本：`run-local-api.sh`、`run-local-worker.sh`、`run-local-frontend.sh` 均可使用；前端脚本已在独立端口启动并返回 Vite 页面入口。
- 项目库、快照、报告存储和本地分析任务相关后端测试：针对性存储/API/Worker 复验 33 项通过；真实 HTTP 阻塞任务期间健康检查保持可用。
- 前端任务页：queued/running 状态明确说明本机 Worker 依赖；等待超时会保留任务并提供继续查询和任务页入口，不会重复提交分析。
- Benchmark Runner：正常人工标注样例、哈希不匹配拒绝、路径越界拒绝均通过；仓库未宣称已有独立人工 Benchmark 分数。
- Chromium 真实联调：显式保存后刷新，从项目库重新打开并分析、阅读源码、保存/读取历史通过。快照请求未重新上传 ZIP。
- 样例报告：Direct=1、1-hop=1、2-hop=1、coverage=complete，证据为 `report.py:5` 的 `return format_date(date)`。
- 桌面 1440 × 1000、手机 390 × 844 实测通过，无横向溢出或浏览器 JavaScript 异常。
- 历史报告增量验收：隔离数据库 22 条报告验证多关键词筛选、分页、删除后补页、迟到请求丢弃、读取失败清空旧详情及来源项目跳转；历史报告不再借用当前其他项目的源码入口。
- 报告下载验收：当前报告页和历史报告详情页提供完整 JSON 下载；浏览器实测 demo 报告下载文件可解析，目标函数为 `utils.format_date`，新增参数为 `timezone`。

2026-10-15 修复后在 Windows 隔离工作树完整复验：3 个跳过项均为当前用户无法创建符号链接的用例，文件缺失、存储路径篡改等安全断言仍执行。第三方 Starlette/httpx 弃用警告保留。此前 macOS 联调与沙箱端口限制记录属于历史阶段，不能代替本次实测。

## 相关文档

- [项目库快照分析与验收](snapshot-workflow.md)
- [数据库说明](database.md)
- [API 契约](api-contract.md)
- [GitHub Desktop 提交清单](github-desktop-submit-checklist.md)
- [入门样例 ZIP 使用指南](beginner-sample-zip-guide.md)
- [后续设计草案](next-stage-design.md)

## 提交说明

项目库与审核修复已通过 PR #2 合并 main，修复范围与逐项验证见 [修复记录](refine-project-fixes.md)。后续变更使用独立分支并经 PR 检查后合并。

提交源代码、测试和文档；忽略本地数据库、ZIP 快照存储、依赖目录、构建产物和临时验收截图。

## 2026-10-15 审核修复复验

已修复共享 ZIP 并发删除、旧 Worker 额外发布、报告删除后的恢复、评测冻结清单与标签身份校验、零重合 F1、Windows 测试权限，以及窄窗口新增导航的溢出。契约样例指纹差异仅固定测试 ZIP 创建平台元数据，生产指纹和既有样例 JSON 保持原样。

真实浏览器使用本分支 Vite /api 代理、独立 rule API 和 Worker、隔离数据库：直接上传→Inspect→Validate→任务→1/1/1 complete 报告；删除该隔离测试报告后，相同配置重新分析成功，任务页显式重新执行也成功；随后 page.page + zone 为 0/0/0 complete，无旧证据和解释。14 个受控 Demo 的新任务结果与同步路径逐字段一致。原生 Windows reduced-motion 与独立人工 Benchmark 均继续 pending；没有调用真实 DeepSeek。

## 2026-10-16 启动与自动检查增量

- 新增 PowerShell 统一入口及标准库启动器；使用固定仓库源码，API / Worker 共用存储和模型配置，前端不接收 DeepSeek Key。
- 19 项启动器专项随完整 pytest 通过；本地完整后端为 1154 passed、3 skipped、1 warning、7 subtests passed。前端仍为 274 passed，Production Build 通过。
- Windows PowerShell 5.1 实测环境自检、实际三服务启动/代理探测/自动退出、Ctrl+C 清理、占用端口拒绝及原服务保持可用。隔离数据库的真实 TCP 工作流经 Vite /api 与本次 Worker 得到 1/1/1 complete、0/0/0 complete。
- 隐藏输入已用测试值验证，终端不回显；缺少 Key 明确停止。DeepSeek 自检没有调用模型，不作为 Key 或外网可用性验收。
- 新增 Windows / Ubuntu PR 工作流，规则测试模式运行完整检查及启动探测；实际远程执行结果以 GitHub Checks 为准，添加 YAML 本身不记作 CI PASS。未修改分支保护。
- 未修改生产分析算法、React 业务状态或原 API；未锁定人工标签。native reduced-motion verification 与 independent Benchmark 继续 pending。

## 2026-10-24 代码关系图增量

- 新增项目关系图接口：上传 ZIP 使用 `/api/v1/projects/graph`，已保存快照使用 `/api/v1/snapshots/{snapshot_id}/graph`；两条路径都复用既有 ZIP 安全校验、指纹核对和静态索引。
- 图谱只输出已由 SymbolIndex 和 CallGraph 证明的函数节点与调用边；未解析调用、解析错误、模块/符号歧义和不支持范围进入 diagnostics，前端单独显示为“待人工检查”。
- 工作台新增“代码关系图”入口，报告页可进入图谱；完整项目图不可用时回退到当前报告中的证据关系，不生成前端猜测节点。
- 关系图页面支持节点选择、关系证据、定义位置、调用方向和未解析调用原因展示；不扩展真实登录、多语言、自动改代码或通用知识图谱范围。
