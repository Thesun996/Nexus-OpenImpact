# Nexus OpenImpact 当前项目状态

> 更新日期：2026-10-13（Asia/Shanghai）
> 当前分支：`feature/refine-project`
> 本文用途：给项目负责人、前端、后端和后续接手同学快速判断“项目现在做到哪里、还能做什么、哪些还不能算完成”。

## 一句话结论

项目已经不是空壳：核心 Python 静态分析、FastAPI 接口、React 前端工作台和本地 SQLite 报告持久化基础都已经存在。当前更准确的状态是：前端主流程可以打开并走通页面，后端接口也有实现；但还不是完整平台，没有真实登录系统，也没有后台任务队列，历史报告也只是本机基础版。

## 当前已经具备的能力

- Python 项目 ZIP 上传后的 Inspect / Validate / Analyze 工作流。
- 选择函数、配置签名变化、校验变化、展示影响报告的前端闭环。
- 支持多种函数签名变化：新增必填参数、删除参数、重命名参数、可选参数改为必填。
- 后端提供 `/api/v1/...` 接口，前端开发环境通过 Vite 代理访问后端。
- 本地 SQLite 报告持久化基础：`POST /api/v1/reports` 可分析并保存报告，`GET /api/v1/reports` 和 `GET /api/v1/reports/{report_id}` 可分页读取历史记录，`DELETE /api/v1/reports/{report_id}` 可删除单条本机报告；前端报告页已提供“保存到历史”，侧边栏已提供“历史报告”读取页，并支持按项目、目标、变更类型等报告元数据筛选和加载更多。
- 报告展示 Direct、1-hop、2-hop、人工检查、未解析调用、Evidence 和中文解释。
- 演示样例 ZIP：`frontend/public/samples/signature_change.zip`。
- 预留了登录、项目持久化、历史报告、后台任务等产品位置，但这些不应被描述为已完成后端能力。

## 当前还没有完成的能力

- 没有项目源码数据库：上传 ZIP 不落库，页面状态主要停留在当前浏览器会话；当前只保存分析报告 JSON 和摘要元数据。
- 登录页/用户入口只有前端表现，不代表已有真实认证、会话或权限系统。
- 没有后台任务队列；分析请求仍按当前接口请求/响应方式工作。
- 没有完整项目管理、账号级历史报告中心、团队协作权限或企业平台能力。
- 生产部署前还需要明确 `/api` 的反向代理或 CORS 策略。

## 本地运行方式

后端需要在仓库根目录使用 Python 3.11+ 环境安装依赖后启动：

```sh
pip install -e ".[test]"
OPENIMPACT_LLM_PROVIDER=rule python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

前端在另一个终端启动：

```sh
cd frontend
npm install
npm run dev
```

浏览器打开：`http://127.0.0.1:5173/`

如果本机已有旧服务占用 8000 或 5173，可以换端口启动。例如本轮联调使用后端 8010、前端 5175：

```sh
cd frontend
OPENIMPACT_API_TARGET=http://127.0.0.1:8010 npm run dev -- --host 127.0.0.1 --port 5174
```

当 5174 也被占用时，Vite 会自动顺延到 5175；以后端健康检查和 Inspect 能通过为准。

注意：直接用普通静态服务器打开 React/Vite 源码可能出现空白页；应使用 `npm run dev` 或构建后的静态产物。

## 当前检查结果

- 前端测试：`npm run test` 已通过，241 项通过。
- 前端构建：`npm run build` 已通过。
- 数据库与报告历史测试：`tests/test_storage.py` 和 `tests/test_report_storage_api.py` 已通过，10 项通过；覆盖建表、保存、列表、读取、删除、元数据筛选和 `has_more` 分页边界。
- 当前本机联调：`http://127.0.0.1:5175/api/v1/health` 返回 `{"status":"ok","version":"0.1.0"}`；通过前端代理上传 `frontend/public/samples/signature_change.zip` 后，Inspect 返回 4 个 Python 文件、4 个函数、覆盖状态 complete；Validate 返回 `valid=true`；Analyze 返回 Direct=1、1-hop=1、2-hop=1；保存历史成功，历史报告页按 `format_date` 筛选可读取保存记录。
- 浏览器验收记录：已补充 [feature/refine-project 验收记录](feature-refine-acceptance.md)。
- 后端测试：已使用临时 Python 3.14 虚拟环境安装 `.[test]` 依赖并运行完整测试，结果为 `1039 passed, 1 skipped, 1 warning, 7 subtests passed`。

后端稳定性测试需要绑定本机 `127.0.0.1` 临时端口；在受限沙箱中会出现 `Operation not permitted`，需要在允许本地端口绑定的环境下运行。

## 本分支当前包含的本轮改动

- `.gitignore`：忽略 `.openimpact/` 本地数据库目录。
- `src/openimpact/storage.py`：新增 SQLite 建表、保存报告、列表和读取逻辑。
- `src/openimpact/api.py`：新增保存报告和历史报告读取接口；原 Analyze 接口保持无持久化。
- `frontend/src/api/client.js`、`frontend/src/pages/HistoryPage.jsx`、`frontend/src/pages/ReportPage.jsx`、`frontend/src/components/AppShell.jsx`、`frontend/styles.css`：前端接入保存历史、历史报告读取、删除、筛选和分页加载。
- `tests/test_storage.py`、`tests/test_report_storage_api.py`：新增数据库与 API 测试。
- `frontend/tests/historyPage.test.js`：新增历史报告摘要、筛选与分页去重测试。
- `docs/database.md`、`docs/api-contract.md`、`docs/feature-refine-acceptance.md`、本文档：记录数据库边界、路径、接口和本轮验收。

## 推荐测试样例

使用 `frontend/public/samples/signature_change.zip` 测试主流程：

1. 上传 ZIP。
2. 选择函数 `utils.format_date`。
3. 新增参数名填写 `timezone`。
4. 参数类型选择 `positional_or_keyword`。
5. 校验变更。
6. 开始分析。

预期报告应能看到：

- Direct Impact：`report.report -> utils.format_date`
- 1-hop Indirect：`dashboard.dashboard`
- 2-hop Indirect：`page.page`
- 覆盖状态：`complete`

## 下一步不用再讨论就可以做的事

- 提交前在 GitHub Desktop 中只勾选代码、测试和文档文件，确认不包含 `.openimpact/`、`.venv-mac/`、`frontend/dist/`、`frontend/node_modules/`、`.idea/`、`.DS_Store`。
- 提交后 Push 到 `feature/refine-project`，再由负责人决定是否发起 PR 或合并主分支。
- 后续若要推进真实登录、项目源码数据库或后台任务队列，需要先定数据模型和产品规则，不能直接作为当前 V1 收尾项。
