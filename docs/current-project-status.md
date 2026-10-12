# Nexus OpenImpact 当前项目状态

> 更新日期：2026-10-12（Asia/Shanghai）  
> 当前分支：`main`  
> 本文用途：给项目负责人、前端、后端和后续接手同学快速判断“项目现在做到哪里、还能做什么、哪些还不能算完成”。

## 一句话结论

项目已经不是空壳：核心 Python 静态分析、FastAPI 接口和 React 前端工作台都已经存在。当前更准确的状态是：前端主流程可以打开并走通页面，后端接口也有实现；但还不是完整平台，没有数据库持久化、没有真实登录系统，也没有后台任务队列和历史报告中心。

## 当前已经具备的能力

- Python 项目 ZIP 上传后的 Inspect / Validate / Analyze 工作流。
- 选择函数、配置签名变化、校验变化、展示影响报告的前端闭环。
- 支持多种函数签名变化：新增必填参数、删除参数、重命名参数、可选参数改为必填。
- 后端提供 `/api/v1/...` 接口，前端开发环境通过 Vite 代理访问后端。
- 报告展示 Direct、1-hop、2-hop、人工检查、未解析调用、Evidence 和中文解释。
- 演示样例 ZIP：`frontend/public/samples/signature_change.zip`。
- 预留了登录、项目持久化、历史报告、后台任务等产品位置，但这些不应被描述为已完成后端能力。

## 当前还没有完成的能力

- 没有数据库落库：ZIP、报告和页面状态主要停留在当前浏览器会话。
- 登录页/用户入口只有前端表现，不代表已有真实认证、会话或权限系统。
- 没有后台任务队列；分析请求仍按当前接口请求/响应方式工作。
- 没有完整项目管理、历史报告持久化、团队协作权限或企业平台能力。
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

注意：直接用普通静态服务器打开 React/Vite 源码可能出现空白页；应使用 `npm run dev` 或构建后的静态产物。

## 当前检查结果

- 前端检查：`npm run check` 已通过。
- 前端测试数量：236 项通过。
- 前端构建：`npm run build` 已通过。
- 后端测试：已使用临时 Python 3.14 虚拟环境安装 `.[test]` 依赖并运行完整测试，结果为 `1039 passed, 1 skipped, 1 warning, 7 subtests passed`。

后端稳定性测试需要绑定本机 `127.0.0.1` 临时端口；在受限沙箱中会出现 `Operation not permitted`，需要在允许本地端口绑定的环境下运行。

## 当前本地未提交改动

- `.gitignore`：新增 `.DS_Store` 和 `.idea/` 忽略规则，避免 GitHub Desktop 把系统文件和 IDE 配置当成项目提交。
- `frontend/src/components/workspace/workspace.css`：调整右下角“项目源码”按钮位置，避免遮挡“开始分析”按钮。
- `docs/api-samples/inspect-response.json`、`docs/api-samples/validate-response.json`、`docs/frontend-handoff.md`：同步固定 demo ZIP 的当前 SHA-256 指纹，保持后端契约测试与文档样例一致。
- 本文档：记录当前项目状态和交接口径。

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

- 用样例 ZIP 做一次真实浏览器手工验收，截图记录上传、选择函数、校验、报告四步。
- 把前端工作流和后端接口字段逐项对齐，确认哪些字段是必填、哪些字段只用于展示。
- 清理提交内容，只保留项目相关文件，避免把 `.DS_Store`、`.idea/`、临时截图等混进提交。
