# Tracework Motion System

Step 2.5 延续 DESIGN.md 的视觉体系。动态阅读顺序为 Change → Trace → Evidence；动画帮助辨认状态与关系，所有名称、调用边、源码与解释继续来自实际响应。

## 动态语言与技术

| 位置 | 行为 | 依据 |
| --- | --- | --- |
| 页面 | `wait` 顺序切换：旧页仅淡出，新页从微小纵向偏移进入；前进 / 后退偏移反向。首次加载与功能范围页保持中性 | 四个真实流程步骤；同一时刻只显示一页 |
| 导航与影响索引 | 单个选中标记从当前位置移动到新选择；再次操作立即取消并重定向 | 当前页面 / 当前影响索引 |
| ZIP 与表单 | 拖拽区边界与文件标记回应拖入；按钮有轻微按压反馈；非空参数以铜色标记草稿 | 原有 dragging、File、输入状态 |
| 校验与分析 | 只在真实 busy 时显示活动标记；校验通过短暂强调状态 | 后端 loading / validation |
| Trace | 保留 caller → callee 的关系方向，从实际变更目标向 Direct 调用方和上游依次强调节点与连线 | 当前记录的真实路径；只强调已有节点 |
| Evidence | 源码区域一次性淡化背景高亮；证据与解释作为同一组立即替换 | 原有对应关系校验后的同序证据槽位 |

页面使用 Motion for React **14.0.0** 的 LazyMotion / AnimatePresence（`mode="wait"`）。选中标记使用 Web Animations API；路径、表单和源码强调使用 CSS。采用 domAnimation，未增加拖动、弹簧或图形布局库。原生 View Transitions 在连续点击验收中出现下一次点击丢失，因此未保留在最终实现。

## Token

Token 定义于 `src/tokens.css`，CSS 与 JavaScript 读取同一来源。

| Token | 值 | 用途 |
| --- | --- | --- |
| `--oi-motion-feedback` | 140ms | 控件与选中标记 |
| `--oi-motion-enter` / `--oi-motion-exit` | 220ms / 90ms | 页面顺序进入 / 退出 |
| `--oi-motion-reading` | 180ms | 选中证据组仅淡入，无子元素位移 |
| `--oi-motion-trace` | 260ms | 节点单次强调 |
| `--oi-motion-trace-step` | 65ms，手机 35ms | 有限路径间隔，最多三个间隔 |
| `--oi-motion-evidence` | 380ms | 源码背景强调 |
| `--oi-motion-travel` | 6px，手机 3px | 新页纵向位移 |
| `--oi-ease-page` | `cubic-bezier(.22,1,.36,1)` | 页面进入的自然减速 |
| `--oi-ease-arrive` / `--oi-ease-depart` | `cubic-bezier(.16,1,.3,1)` / `cubic-bezier(.7,0,.84,0)` | 到达减速 / 更快退出 |

## 生命周期与可访问性

- WorkflowProvider 始终位于页面过渡外；页面动画不调用 API、不复制 File 或另存报告，仅只读记录版本引用以移除失效页面。
- 退出页面立即 inert、aria-hidden，不参加键盘与鼠标操作。`wait` 在退出完成后才挂载新页；快速导航仅接受最新目标，不排队展示中间目标。
- revision、Inspect 或 Report 失效时立即隐藏退出内容并以 0ms 完成退出；保留 Motion 的注册节点直至通知完成，避免等待死锁。原始 File、fingerprint、取消请求与业务 reducer 均保持原样。
- 切换期间保留旧页测量高度，进入完成后解除；采用稳定滚动条槽位避免长短页面的横向宽度跳变。没有绝对定位页面层、动画高度、z-index 或裁切补丁。
- 路由切换将焦点置于持久的主内容区域；影响选择仍保留在原按钮或手机 select 上。
- 退出等待期间在 main 按 Tab，会中断该次过渡并将焦点交给新页首个可操作控件。Shift+Tab 保持浏览器默认行为；监听在卸载时清理。
- Evidence、Trace 与 Explanation 用同一次 render 更新。报告内部不保留退出中的旧证据。unavailable 与诊断不等待揭示动画。
- reduced-motion 下移除页面位移、退出保留、路径延迟、源码强调及旋转。选中标记、中文 loading、成功/错误文字与静态忙碌标记保留。
- 页面通过 `useSyncExternalStore` 监听偏好变化；标记有独立 MediaQuery 监听与清理，CSS 自动跟随偏好。无需刷新工作台。
- 不逐字动画源码，不监听滚动更新 React 状态，不使用永久 will-change，不播放持续路径流光，不制造进度百分比。

## Skill 应用记录

| Skill / 实际阅读 | 可用性与实施方式 | 本轮采用 | 未采用及原因 |
| --- | --- | --- | --- |
| [Anthropic frontend-design SKILL.md](https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md)，本地同名 Skill | 本地指南加载；官方全文阅读，按设计流程实施 | 明确动态主旨；将最强动态集中在真实调用追踪；既有 Tracework 视觉与业务优先 | 未换用营销布局、聊天界面或重复卡片入场，本轮为已有工作台增量改造 |
| [Taste Skill SKILL.md](https://raw.githubusercontent.com/Leonxlnx/taste-skill/main/skills/taste-skill/SKILL.md)，§4.5–4.6、§5.D、§6 | 本地未安装；官方规范参考与等效实施，无 CLI 调用 | 真实 loading / empty / error / selected；触觉反馈；transform / opacity；限制布局重排与 bundle 成本；采用 motion/react | 未采用永久动态、默认深色主题与营销 Hero；DESIGN.md 规定浅色阅读工作台 |
| [UI UX Pro Max SKILL.md](https://raw.githubusercontent.com/nextlevelbuilder/ui-ux-pro-max-skill/main/.claude/skills/ui-ux-pro-max/SKILL.md)、references/quick-reference.md §1–3 与交互/动画规范、references/pro-rules.md、data/stacks/react.csv 相关状态/Effect/a11y 条目 | 本地未安装；官方规范参考与等效实施，未运行搜索 CLI | 快反馈与较短退出；可中断；44px 控件；路由焦点；Effect 清理；减少动态效果与手机位移 | 未新增 TypeScript、主题切换、虚拟列表或替换 Context；均超出本轮保护边界 |
| [Impeccable SKILL.md](https://raw.githubusercontent.com/pbakaus/impeccable/main/.agents/skills/impeccable/SKILL.md)、reference/audit.md、critique.md 的层级/认知负担/用户控制/一致性部分、polish.md、harden.md、animate.md、craft-floor.md | 本地未安装；context、audit、critique、polish、harden 命令均未运行。直接读取项目规范并执行等效浏览器检查 | Operate / Read 节奏；一处重点动态；整条路径审查；快速重复、失败、长内容、partial 与 unavailable；截图/录屏后收束 | 未采用未经测量的质量评分、付费 detector、重设计或沉重视觉特效；没有假称执行不可用工具 |

以上建议发生冲突时，采用用户任务、DESIGN.md 与 Anthropic frontend-design 的顺序。辅助指南中要求另开代理或额外审批的流程未调用；本轮由同一助手完成已授权范围。

## 验收与限制

真实 rule 后端位于 `127.0.0.1:8000`，正式前端位于 `127.0.0.1:5174`，通过既有 `/api` 代理访问。验收素材与临时故障代理存放于 Git 忽略的 `.local/ui-step2.5`。

- signature_change ZIP：utils.format_date + timezone 为 1/1/1、complete；page.page + zone 为 0/0/0、complete。案例切换无旧证据、旧解释或旧选中状态。
- 连续导航保持 File 与项目上下文；导航不会增加 Inspect / Validate / Analyze 请求。
- 持有真实 Inspect 响应期间更换 ZIP，随后释放旧响应，旧项目没有恢复。
- 无效 ZIP、空函数、重名参数、partial / manual_review / unresolved、指纹不一致及网络断开/恢复已检查。Evidence unavailable 使用仅在临时代理中的受控故障，分析数据来自真实后端。
- 1440、1280、768、390px 布局已检查；手机保留 partial 与诊断。reduced-motion 用隔离测试页面强制 MediaQuery 与对应 CSS 分支验证，未更改系统设置。
- 另用受控 MediaQuery change 事件检查打开页面后的偏好切换：启用后 active=1、exiting=0、opacity=1、transform=none；恢复后出现方向过渡。监听清理另有自动测试。
- 实际浏览器逐帧截图按采集时间编码 GIF，无插值或伪造动画帧。桌面路径与页面切换录制分别约 7.5 秒、6.7 秒。
- 本轮没有运行性能压力测试或真机测试。系统文件拖放、低性能真机与其他浏览器内核仍可在最终人工验收补测。

Step 2.5 当时的 `npm run check`：94 passed、0 failed（原有 86 项加 8 项动效回归）。生产构建成功；JS gzip 116.45 kB，相比此前 88.52 kB 增加约 27.93 kB。未报告未经测量的帧率或性能分数。

## 修改文件

- `DESIGN.md`、`MOTION.md`：动效规范、Skill 应用和验收记录。
- `package.json`、`package-lock.json`：固定 Motion 版本与依赖锁定。
- `src/App.jsx`、`src/main.jsx`、`src/tokens.css`：路由展示方向、统一样式入口与 Motion Token。
- `src/components/AppShell.jsx`、`src/components/report/ImpactIndex.jsx`：持久选中标记。
- `src/components/report/TraceView.jsx`、`src/pages/ReportPage.jsx`：真实路径顺序强调与原子更新的证据/解释展示。
- `src/motion/WorkflowPages.jsx`、`MovingMarker.jsx`、`pageTransition.js`、`reducedMotion.js`、`motion.css`：过渡、标记、退出保护、实时偏好监听和微交互。
- `tests/motion.test.js`：方向、退出失效、CSS 曲线转换、减少动态效果和监听生命周期回归。

验收 GIF：`.local/ui-step2.5/trace-evidence.gif`、`workflow-navigation.gif`。截图：`final-desktop-viewport.jpg`、`mobile-report.jpg`。均为本地忽略文件，未进入提交范围。

## Step 2.5.1：文字重叠修订

本轮只改动 `src/motion/WorkflowPages.jsx`、`src/motion/motion.css`、`src/tokens.css` 与本文件；继承 Step 2.5 的未提交修改，不覆盖已有成果。

### 实际定位

旧实现 `popLayout` 把退出页移为 absolute，进入页同时在同一顶部布局。真实浏览器第 1 帧采样中，上传页与函数页的顶部均约 143.32px，透明度分别约 0.98、0.98。标题、描述与部分卡片文字因此同时可见。页面 key 正常，AppShell 没有动效，没有 layout / layoutId 或独立标题动画。关键源码层面的问题是页面并行呈现与进入起始透明度 0.85。

另外，`usePresence` 的手动参与者原先没有在常规退出动画结束时调用 `safeToRemove`。改为 wait 后必须正确完成双方通知；失效路径也必须保留 Motion 参与者到 0ms 完成，不能先返回 null 造成等待停滞。这两个分支均通过真实 Inspect / Analyze 和快速切换复验。

### 修复与浏览器验收

- 正式页面 `127.0.0.1:5174`：旧页 opacity 1 → 0、90ms，无退出位移；新页 opacity 0 → 1、220ms，纵向 ±6px，手机 ±3px。标题、正文没有独立动画。Evidence 组保留淡入，移除其 3px 位移，避免父子位移叠加。
- 正式桌面 190 帧与手机 170 帧：逐页前进、逐页返回均无双页可见帧；容器高度未归零；main 顶部位置未发生变化。只存在预定的微小进入位移，没有观察到布局塌陷或标题重影。
- 受控快速输入：通过忽略目录中的辅助按钮逐帧触发真实导航 click，7 次约 81ms。160 帧无重叠；最终仅显示最后的上传页，项目及 ZIP 保留；请求日志前后均为 9 条，无新增 HTTP 请求。该辅助按钮未进入生产源码。
- 在退出等待期间真实按 Tab，先复现焦点落到 body；修复后焦点交给新页“调整变更”按钮，opacity=1、transform=none。普通导航仍将焦点放在 main。
- 手机端反复选择 Direct / 1-hop / 2-hop 六次：每次仅一组 Evidence / Explanation，源码与说明一致，阅读组 transform=none。未触及 reportData 匹配规则。
- reduced-motion 用独立验收页面模拟 MediaQuery 与 CSS 分支：实际上传 ZIP、Validate、Analyze 得到 1/1/1；六次页面切换均仅一页、opacity=1、transform=none，Trace animation=none。未改变系统偏好设置。
- 正式 rule 后端重新运行 A：utils.format_date + timezone，1/1/1、complete；B：page.page + zone，0/0/0、complete。B 中 Evidence 面板为 0，没有 timezone、旧调用源码或旧 Direct 引用。

本轮原始记录、GIF 及关键帧位于 Git 忽略的 `.local/ui-step2.5.1/`。`encode-recordings.py` 从原始 JPEG 与采集时间编码，没有合成中间动画帧，并断言无重叠、无高度塌陷及主内容顶部稳定。`keyframes.png` 是实际截图标题区域的带标注裁切对照，完整截图与逐帧记录同时保留。

本轮未进行帧率基准、性能压力或物理手机测试；没有将这些结果表述为已验收。

最终回归：`npm run check` 94 passed、0 failed；单独 `npm run build` 成功（JS gzip 116.91 kB）；`git diff --check` 通过。API Client、state、reportData、Core、公开契约差异为零。未改测试预期、未增加依赖、未执行 commit / push / merge。Step 2.5 的原有未提交改动均保留。
