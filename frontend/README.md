# OpenImpact Web

React + Vite 前端。Phase 4.2 Step 3 完善动态报告与 Web MVP 验收，默认实际项目模式使用用户选择的 ZIP，执行 Inspect → Validate → Analyze。只有主动点击“打开演示项目”才使用保存的样例响应。

先在原后端工程启动 rule 模式服务：

```powershell
cd E:\编译\2026人工智能算法精英赛新赛道\Nexus-OpenImpact
$env:OPENIMPACT_LLM_PROVIDER = 'rule'
.\.venv\Scripts\python.exe -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd E:\编译\2026人工智能算法精英赛新赛道\Nexus-OpenImpact-frontend\frontend
npm install
npm run dev
```

开发地址：`http://127.0.0.1:5173`。本地 `/api` 代理到 `http://127.0.0.1:8000`，无需为开发页面修改后端 CORS。

```powershell
npm run check
```

统一 API Client 使用相对 `/api/v1/...` 地址和浏览器 `FormData`；原始 ZIP 保存在顶层，三个业务请求重复提交同一 `File`。校验和分析携带 Inspect 返回的指纹。更换文件或配置会清空旧结果，晚返回的请求不能覆盖当前状态；服务或业务失败不会切换为 Mock。

报告只读取当前 Analyze 响应。Direct、1-hop、2-hop、人工检查和未解析调用分别展示；点击影响记录查看其同序 Evidence 与中文辅助解释。证据或解释不可用时保留静态结果并显示诊断。partial 明确提示覆盖不完整，零影响不会被表述为全项目确定无影响。源码按普通文本渲染。

ZIP 和报告仅保留在当前页面会话内，刷新后需要重新选择文件。生产构建只生成静态资源；上线前需配置 `/api` 到后端的同源反向代理，或经确认的具体 Origin 白名单。`npm run preview` 没有开发代理，仅用于静态产物检查，不能代替真实 API 联调。

2026-10-04 本地验收：`npm run check` 的 68 项测试通过，`npm run build` 通过；原 main rule 后端的真实浏览器案例 A 得到 1/1/1、complete，案例 B 得到 0/0/0、complete 且没有旧证据。异常、partial 与受控不可用状态记录见交接文档。当前本地技术验收通过，等待负责人审核后整合分支。

状态结构、错误处理、报告语义及本轮实际验收记录见 [前后端交接文档](./前后端交接文档.md)。
