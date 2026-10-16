# OpenImpact Web

React + Vite 前端。实际项目模式使用用户选择的 ZIP，执行 Inspect → Validate → Analyze，支持新增必填参数、删除参数、重命名参数、可选参数改为必填。只有主动点击“打开演示项目”才使用保存的新增参数样例响应。

Windows 推荐从仓库根目录运行 `scripts/start-local.ps1`，统一启动 API、Worker 和前端，见 [启动与自检](../docs/local-start.md)。以下手工命令用于规则测试；DeepSeek 体验需确保 API 与 Worker 使用相同模型配置与 Key。

以下命令从本仓库根目录开始，该目录包含 `src/openimpact/` 和 `frontend/`。先按[根 README](../README.md)创建 Python 虚拟环境并完成 editable install；启动后端时使用已激活的该环境。

在 Windows PowerShell 中启动 rule 模式服务：

```powershell
$env:OPENIMPACT_LLM_PROVIDER = 'rule'
python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

Linux/macOS 在仓库根目录执行 `source .venv/bin/activate` 后启动：

```sh
OPENIMPACT_LLM_PROVIDER=rule python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

还需在同一仓库根目录另开终端启动 Worker。PowerShell 执行：

```powershell
$env:OPENIMPACT_LLM_PROVIDER = 'rule'
python -m openimpact.worker
```

Linux/macOS 使用 `OPENIMPACT_LLM_PROVIDER=rule python -m openimpact.worker`。API 与 Worker 必须使用相同数据库和快照目录；Worker 未运行时，分析任务会留在排队状态。

另开终端，从同一仓库根目录进入 `frontend/` 并启动前端。以下命令适用于 PowerShell 和 Linux/macOS shell：

```sh
cd frontend
npm install
npm run dev
```

开发地址：`http://127.0.0.1:5173`。本地 `/api` 代理到 `http://127.0.0.1:8000`，无需为开发页面修改后端 CORS。

macOS 也可从仓库根目录直接运行 `./scripts/run-local-frontend.sh`。它会检查 `node_modules`，并默认把 `/api` 代理到 `http://127.0.0.1:8000`；需改用其他后端端口时设置 `OPENIMPACT_API_TARGET`。

```powershell
npm run check
```

统一 API Client 使用相对 `/api/v1/...` 地址和浏览器 `FormData`；原始 ZIP 保存在顶层，三个业务请求重复提交同一 `File`。校验和分析携带 Inspect 返回的指纹。更换文件或配置会清空旧结果，晚返回的请求不能覆盖当前状态；服务或业务失败不会切换为 Mock。

报告只读取当前 Analyze 响应。Direct、1-hop、2-hop、人工检查和未解析调用分别展示；点击影响记录查看其同序 Evidence 与中文辅助解释。证据或解释不可用时保留静态结果并显示诊断。partial 明确提示覆盖不完整，零影响不会被表述为全项目确定无影响。源码按普通文本渲染。

ZIP 和报告仅保留在当前页面会话内，刷新后需要重新选择文件。生产构建只生成静态资源；上线前需配置 `/api` 到后端的同源反向代理，或经确认的具体 Origin 白名单。`npm run preview` 没有开发代理，仅用于静态产物检查，不能代替真实 API 联调。

2026-10-04 本地验收：`npm run check` 的 68 项测试通过，`npm run build` 通过；原 main rule 后端的真实浏览器案例 A 得到 1/1/1、complete，案例 B 得到 0/0/0、complete 且没有旧证据。异常、partial 与受控不可用状态记录见交接文档。当前本地技术验收通过，等待负责人审核后整合分支。

状态结构、错误处理、报告语义及本轮实际验收记录见 [前后端交接文档](./前后端交接文档.md)。

## 四种签名变更

Inspect 后选择目标函数，在配置页选择一种变更：

| 变更 | 配置方式 | 当前支持范围 |
|---|---|---|
| 新增必填参数 | 输入新名称、参数类型，可指定插入位置 | 三种普通参数 |
| 删除参数 | 选择现有参数 | 三种普通参数；不支持删除 *args / **kwargs |
| 重命名参数 | 选择现有参数，输入新名称 | 普通位置或关键字参数、仅关键字参数 |
| 可选参数改为必填 | 选择有默认值的普通参数 | None、False、0、空字符串也属于有默认值 |

禁用参数仍展示原因。候选 After 是待校验草稿，名称和 Python 参数顺序是否有效由后端 Validate 判断。只有当前配置校验成功后才能 Analyze；修改目标、类型或配置会取消旧请求并清除失效结果。浏览页面之间导航保留原始 ZIP 和有效校验。

报告摘要使用响应中的真实 operation，Before / After 使用后端签名。非新增类型允许 `added_parameter=null`。Direct 统计本次变更新引入的调用不兼容；Indirect 仍仅表示上游路径需要检查。

多类型实现与验收记录见 [集成设计文档](../docs/multi-change-frontend-design.md#step-2b-实施与验收记录)。
