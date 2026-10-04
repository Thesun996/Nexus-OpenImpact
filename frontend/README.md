# OpenImpact Web

React + Vite 前端。Phase 4.2 Step 2 接入 Backend v1，默认实际项目模式使用用户选择的 ZIP，执行 Inspect → Validate → Analyze。只有主动点击“打开演示项目”才使用保存的样例响应。

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

状态结构、错误处理、报告语义及本轮实际验收记录见 [前后端交接文档](./前后端交接文档.md)。
