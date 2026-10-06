# 黑紫主题与演示登录验收

开发基线：`8727026`；复用现有开发工作树，分支 `feature/brand-entry`。用户启动目录继续使用 `Nexus-OpenImpact`，不增加新的启动目录。

## 实现范围

- 单次 Anime.js 3.2.2 开场：Nexus OpenImpact 逐字出现、停留、轻微散去，随后显示登录。可跳过，不在业务页面之间重播。
- 参考用户图片实现桌面左右分栏、手机上下排列的演示登录。账号密码可留空，不校验、不上传、不保存；没有新增认证接口。
- 全局黑紫白配色；源码、解释和表单使用稳定纯色。现有布局、源码窗口、追问、领域选择与 Motion System 保留。
- 入口状态仅在 EntryGate；登录后原 WorkflowProvider 持续挂载。Core、API Client、Context/reducer、ZIP/fingerprint/AbortController、报告对应规则均无修改。

## 文件白名单

1. `frontend/DESIGN.md`
2. `frontend/index.html`
3. `frontend/package.json`
4. `frontend/package-lock.json`
5. `frontend/public/licenses/Animejs.txt`
6. `frontend/src/App.jsx`
7. `frontend/src/components/entry/EntryGate.jsx`
8. `frontend/src/components/entry/brandReveal.js`
9. `frontend/src/components/entry/entry.css`
10. `frontend/src/components/workspace/workspace.css`
11. `frontend/src/tokens.css`
12. `frontend/styles.css`
13. `frontend/tests/entry.test.js`
14. `docs/brand-entry-acceptance.md`

## 验收结果

- Frontend `npm run check`：233 passed（原 228 + 5 个入口与时间线生命周期测试），包含生产构建。
- 单独 `npm run build`：PASS；构建 JS gzip 148.89 kB，CSS gzip 13.71 kB。Anime.js 由 npm 精确锁定版本，运行时不使用 CDN，保留 MIT 原文。
- Backend 完整 pytest：1038 passed、2 skipped、7 subtests passed，保留原 Starlette 弃用提示。Windows CLI 子进程测试需要 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`；未设置时两个既有 CLI 测试因 GBK 解码失败，设置后完整回归通过，未改动旧测试或生产代码。
- `git diff --check`：PASS。
- 实际浏览器使用本工作树 Vite 5175 → `/api` → 本工作树 rule Backend 8001。没有调用真实模型。
- `utils.format_date + timezone`：1/1/1，完整；`page.page + zone`：0/0/0，完整，无旧源码或解释残留。
- `module_rename` 的 utils → formatting：1/1/1，完整；`symbol_rename` 的 MAX_RETRIES → RETRY_LIMIT：1/1/1，完整。全部执行真实上传、Inspect、Validate、Analyze、Report。
- 桌面与手机：登录、函数/模块/符号操作、报告、源码窗口可用；手机 Escape 关闭源码后焦点回到打开按钮。登录 Tab 顺序为用户名 → 密码 → 登录，Enter 进入主内容；跳过动画可用。
- 快速上传/选择/配置/报告往返：保留原项目、已校验配置与报告，不重播入口；服务记录没有因导航重复 Inspect/Validate/Analyze。
- 1440 / 1280 / 768 / 390px 登录与报告检查：无页面横向溢出。浏览器警告与错误日志为空。
- 受控浏览器偏好测试：以测试页面的 matchMedia 替身检查初始 reduce=true 直接显示登录、动画中偏好改变会取消开场、进入工作台后改变偏好不会退回入口。测试页面只在 `.local`，不提交；该结果不代表 Windows 原生系统验收。
- **native reduced-motion verification = pending**，仍由负责人进行系统级补验。

实际截图、开场逐帧 JPG、时间戳与 GIF 留在开发工作树 `.local/brand-entry/`，不纳入版本库。关键帧核对了出现、完整标题、散去和登录阶段，没有新旧页面文字叠影。录制是实际浏览器截图序列按采样时间组成 GIF，网站本身只播放一次。

## Skill 应用

- frontend-design：完整读取，采用单个开场、真实产品步骤、少量字体与清晰阅读面。按用户指定黑紫渐变方向实施。
- UI UX Pro Max：读取 SKILL.md，实际运行本地规范搜索；采用对比度、焦点可见、触控区、减少动态效果与避免过量动画规则。未运行自动生成整套设计系统。
- ponytail：复用既有业务 Provider、路由与响应式结构；仅新增入口组件和一条可取消时间线，不引入认证体系或持久化账户。

演示登录没有访问控制能力；接入真正账号体系需要独立设计后端认证与会话，当前页面不宣称具备该能力。
