# Nexus OpenImpact 当前项目状态

> 更新日期：2026-10-14（Asia/Shanghai）
> 当前分支：`feature/refine-project`
> 本文记录当前代码能力及可复核验收结果；设计草案不代表已实现功能。

## 当前状态

项目具备 Python 静态影响分析、React 工作台、本地 SQLite 报告历史和可复用的项目快照库。已接通“保存 ZIP → 刷新后从项目库打开 → 选择目标 → 校验 → 分析 → 查看证据 → 保存历史”的真实业务流程。

当前仍是本机工作台：登录是演示入口，没有真实用户认证、账号隔离或后台任务队列。

## 已具备能力

- Python ZIP 的安全导入、AST 解析、明确符号/调用关系及覆盖诊断，不执行上传源码。
- 函数参数新增、删除、重命名、可选改必填；已有模块及公开符号变更能力保持原范围。
- Direct、1-hop、2-hop 影响、人工检查、未解析调用、源码位置、证据及中文解释。
- 上传页“保存并读取项目”：保存项目和 ZIP 快照，进入目标选择。
- 项目库“使用此快照分析”：直接使用已保存快照，刷新后无需重新上传 ZIP。
- 非默认源码根目录随快照保存并复用；每次读取核对大小、文件位置和指纹。
- 快照模式下的源码查看、报告追问及报告保存；追问遵循已有模型配置和规则回退。
- 本机报告历史保存、读取、筛选、分页和删除；快照来源 ID 保存在完整报告中。
- 直接读取 ZIP 和独立演示流程继续可用。

## 尚未实现

- 真实登录、用户表、会话和账号级数据隔离。
- 同一项目追加多个上传版本、项目删除及快照保留策略。
- 后台任务队列、自动重试。
- 团队权限、公开部署及生产代理配置。

项目库默认保存在 `.openimpact/openimpact.sqlite3` 和 `.openimpact/snapshots/`，不应提交到 GitHub。当前没有为报告表添加项目关联列；来源 ID 位于 report JSON。

## 本地启动

在仓库根目录启动后端（Python 3.11+，已安装项目依赖）：

```sh
OPENIMPACT_LLM_PROVIDER=rule python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

另一个终端进入 `frontend`：

```sh
npm run dev -- --host 127.0.0.1 --port 5173
```

浏览器打开 `http://127.0.0.1:5173/`。Vite 使用 strictPort，端口被占用时会报错，不会自动换端口。

本轮为避免干扰占用 8000 的旧后端，最新后端使用 8010；前端仍使用 5173，对应启动方式为：

```sh
OPENIMPACT_API_TARGET=http://127.0.0.1:8010 npm run dev -- --host 127.0.0.1 --port 5173
```

这些是本地开发服务，服务退出后需要重新启动。更新后端代码后需要重启后端，避免浏览器连接旧版本。不要用普通静态服务器直接打开 React/Vite 源码。

## 当前检查结果

2026-10-14 最终回归：

- 完整后端：`1071 passed, 1 skipped, 1 warning, 7 subtests passed`。真实 HTTP 测试在允许本地端口绑定的环境中运行通过。
- 前端：`npm run test`，251 项通过。
- 前端构建：`npm run build` 通过；仍有超过 500 kB 的 chunk 大小提示。
- 项目库、快照和报告存储相关后端测试：32 项通过。
- Chromium 真实联调：显式保存后刷新，从项目库重新打开并分析、阅读源码、保存/读取历史通过。快照请求未重新上传 ZIP。
- 样例报告：Direct=1、1-hop=1、2-hop=1、coverage=complete，证据为 `report.py:5` 的 `return format_date(date)`。
- 桌面 1440 × 1000、手机 390 × 844 实测通过，无横向溢出或浏览器 JavaScript 异常。

完整后端测试最初在受限沙箱下被本机端口绑定权限阻止；上述结果来自随后获准的完整复验。第三方 Starlette/httpx 弃用警告没有隐藏或转为通过断言。

## 相关文档

- [项目库快照分析与验收](snapshot-workflow.md)
- [数据库说明](database.md)
- [API 契约](api-contract.md)
- [GitHub Desktop 提交清单](github-desktop-submit-checklist.md)
- [后续设计草案](next-stage-design.md)

## 提交说明

本轮改动继续提交到 `feature/refine-project`；尚未自动 Commit、Push 或合并主分支。建议标题：

`feat: 支持项目库快照直接分析`

提交源代码、测试和文档；忽略本地数据库、ZIP 快照存储、依赖目录、构建产物和临时验收截图。
