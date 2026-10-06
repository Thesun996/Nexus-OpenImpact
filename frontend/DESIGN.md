# OpenImpact 视觉规范：Tracework

## 当前版本：黑紫入口与工作台

用户已确认新的黑、紫、白方向。当前运行页面以本节和 `src/tokens.css` 为准；下方原 Phase 1 提案保留作历史记录，其中日间配色、初版功能范围和当时的实施状态不再代表当前版本。

| 角色 | 当前值 | 使用原则 |
| --- | --- | --- |
| 工作底色 | `#09070E` | 黑色画布，业务内容周围保留空间 |
| 阅读面 | `#141019` | 纯色表单、源码、证据面板 |
| 正文 | `#F5F1FF` | 浅白文字，保留原 IBM Plex 字体与中文回退 |
| 控件边界 | `#81728F` | 输入边界与必要结构线 |
| 交互与传播 | `#AC86FF` | 紫色操作、焦点、选中与上游路径 |
| 变更与错误 | `#F2B5EA` | 淡紫粉改动标记，同时保留类型文字与边界形状 |
| 品牌渐变 | `#7134C6` | 登录左侧由白、紫过渡到黑；工作台仅用低强度渐变与细顶边 |

源码与长正文不叠在强渐变上。按相对亮度公式计算：正文/阅读面 16.91:1、交互紫/阅读面 6.81:1、变更色/阅读面 11.25:1、控件边界/阅读面 4.24:1、次级文字/阅读面 9.98:1。选中、错误和 Direct/Indirect 不仅靠颜色区分。

入口顺序：项目名逐字出现 → 短暂停留 → 字符轻微散开并消失 → 演示登录 → 上传页。Anime.js 固定为 3.2.2，通过构建打包，不在运行时依赖 CDN；MIT 原文保留在 `public/licenses/Animejs.txt`。开场约 2.5 秒、单次播放，可随时跳过；登录整体轻淡入，不给每个表单元素单独入场。

登录只用于当前前端体验，不验证、发送或保存账号密码；字段可留空。页面明确标为演示登录，不提供未实现的第三方登录、注册或密码找回。刷新后重新显示入口，业务页之间切换不再出现开场或登录。

`EntryGate` 仅持有入口展示状态。登录后 WorkflowProvider 挂载一次并持续保留，不修改 ZIP、指纹、请求取消、Validate、Analyze、Report 和现有页面动效。开场时间线在跳过、卸载和 StrictMode 重播时清理，旧完成回调不得改变已进入的业务状态。

减少动态效果偏好下直接显示登录并取消开场，CSS 同时取消登录淡入。登录显示后聚焦标题，Tab 进入表单；登录提交后聚焦业务主内容。手机采用上下布局，省去入口的三步说明重复列表，保留演示说明和主操作；业务页关键诊断照常展示。

本轮实际使用 frontend-design 的单一开场、产品内容与层级原则；运行 UI UX Pro Max 的对比度、键盘焦点和 reduced-motion 规范搜索；按 ponytail 复用原业务状态和现有响应式结构。黑紫渐变为用户指定的方向，优先于外部 Skill 的默认风格建议。

---

## 原 Phase 1 设计提案（历史记录）

状态：UI Redesign Phase 1 设计提案，等待项目负责人审核。尚未应用到运行页面。

基线：2026-10-04，`origin/main` 的 `3a5a582`（Web MVP 合并后）；设计分支 `feature/ui-redesign`。本轮只新增本文件，不修改 React、CSS、业务状态、后端或公开契约。

## 1. 设计任务与主导方法

OpenImpact 的用户是正在学习参与真实开源项目的开发者。一次操作的目标是理解：计划新增一个必填参数后，哪些调用确定失去兼容性，哪些上游函数需要检查，以及每项判断对应的源码事实。

整体艺术方向由用户指定的 [Anthropic frontend-design 原文](https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md)主导。已完整读取，采用先规划颜色、字体、布局，再对照产品任务自审的方法；本轮停在设计规范阶段。显著的视觉表达集中在真实调用路径与证据的联动，其他区域保持安静。

辅助参考的职责限定如下：

| 参考 | 本轮使用方式 | 不采用的自动默认 |
| --- | --- | --- |
| [Taste Skill](https://github.com/Leonxlnx/taste-skill) | 已读取相关布局、排版、质感与状态章节，用于检查同权卡片、模板装饰和缺乏意义的数字 | 通用营销 Hero、强制套用外部组件系统、滚动劫持与默认高动效 |
| [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 已读取 SKILL.md 和 React 参考，用于核对可读性、键盘、触控、表单及响应式规则 | 自动生成整套主题、为设计重写现有 Context/reducer、未经测量的性能抽象 |
| [Impeccable](https://github.com/pbakaus/impeccable) | 参考 critique 的任务层次、audit 的技术检查、polish 的全流程一致性；实际命令留到后续阶段 | 本轮启动安装器、执行审查工具、写入额外技能上下文或开展页面实现 |

未运行这些仓库的远程脚本，也未新增依赖。规范冲突时，按项目需求与 Anthropic frontend-design 决定。已有产品和接口事实以 [PROJECT.md](../PROJECT.md)、[API 契约](../docs/api-contract.md)、[前端交接说明](../docs/frontend-handoff.md)为准。

## 2. 现有 UI 审查

审查基于当前 React/CSS 源码，并对照之前 Step 4 的真实报告截图。以下属于源码与现状审查，不宣称已完成改版后的浏览器验收。

| 现状 | 对用户的影响 | 改版处理 | 源码依据 |
| --- | --- | --- | --- |
| 13px 基准、宋体 UI、大量 800–900 字重 | 中文解释密集，标题、标签、值和代码层次相近 | 提高正文可读性，限制粗体，分开界面与代码字体 | [styles.css](styles.css) 的根字体与各组件字重 |
| 7 个导航入口中 4 个指向规划页，顶栏有禁用的全项目搜索 | 学生难以识别当前真正可完成的任务 | 只突出四个实际工作步骤；规划功能从主导航移出 | [AppShell.jsx](src/components/AppShell.jsx) |
| 顶部模式条和每页 ModeNotice 重复解释技术流程 | 首屏被过程说明占用，核心操作出现较晚 | 保留模式区别，把 ZIP 重传和指纹细节归入可展开说明 | [AppShell.jsx](src/components/AppShell.jsx)、[PageParts.jsx](src/pages/PageParts.jsx) |
| 步骤、摘要、统计、列表、详情均套相近圆角和阴影 | 视觉层级被压平，像通用后台布局 | 用空间和分区建立层次，容器只在需要边界时出现 | [styles.css](styles.css) |
| 报告先展示 5 张等权统计卡 | 数量占据注意力，用户仍需往下找“为什么” | 紧凑计数行，随后直接进入追踪和源码 | [ReportPage.jsx](src/pages/ReportPage.jsx) |
| 报告源码栏仅约 330–390px，路径藏在较后元数据中 | 长 Symbol 和中文解释频繁换行，传播依据不易发现 | 证据作为宽主区域，选中项的调用路径前置 | [styles.css](styles.css) 的 `.report-grid`、[ReportPage.jsx](src/pages/ReportPage.jsx) |
| 列表项、静态原因、解释、元数据重复长段内容 | 阅读成本高，重要结论被淹没 | 摘要、真实证据、辅助说明、审计元数据分层呈现 | [ReportPage.jsx](src/pages/ReportPage.jsx) |
| Direct 使用 `high` 样式，未解析调用也有红色标记 | 易混淆兼容性退化、业务风险和解析状态 | 改用影响类型和证据状态的视觉语义；unknown 保持中性 | [ReportPage.jsx](src/pages/ReportPage.jsx)、[styles.css](styles.css) |
| 文件已选择就出现绿色强调 | 可能误读为项目已被检查 | 明确区分已选文件、正在读取、已读取三个状态 | [UploadPage.jsx](src/pages/UploadPage.jsx) |
| 参数 kind 以英文直接作为表单主标签 | 新贡献者较难判断参数规则 | 中文含义为主，保留 Python kind 作为次标签和值 | [ChangePage.jsx](src/pages/ChangePage.jsx) |
| 1120px 附近多区域直接变单列，项目上下文减少 | 平板布局变长；手机函数表仍可能被裁切 | 给桌面、平板、手机独立布局，局部处理溢出 | [styles.css](styles.css) 的媒体查询与 `.function-table` |
| glyph 风格不一，隐藏上传 input 的焦点不够明显 | 视觉质感和键盘操作反馈不一致 | 统一图形尺度；上传区增加可见 focus-within | [AppShell.jsx](src/components/AppShell.jsx)、[styles.css](styles.css) |

保留已有优点：真实 ZIP 流程、状态失效清理、请求竞态保护、键盘按钮、普通文本源码渲染、零结果与 partial 的正确语义，以及 Evidence/Explanation 严格对应。设计不把这些成熟逻辑换成新的实现。

## 3. 整体视觉概念与方案自审

**Tracework / 代码影响追踪工作台。** 将一次分析组织成一条可以核查的推理线：计划变更、已知调用、源码依据、中文理解。

视觉材料来自代码审查工作本身：行号边栏、函数签名、调用方向、改动标记、证据位置。背景采用冷色工作底板，阅读面采用白色。保持日间阅读模式，不增加暗色主题切换或新的设置功能。

核心特征是“追踪带”：显示当前选中影响已有的调用节点和调用位置，末端标出修改目标；其下立即展示该项真正对应的源码。看见路径后可以核对代码，再阅读解释。只有这一处承担较强的品牌表现，外围不加入装饰图、营销数字、发光渐变或循环动画。

### 3.1 探索与取舍

| 候选方案 | 简图 | 判断 |
| --- | --- | --- |
| 大图总览 | `Change / full-project graph / side panel` | 当前 API 不提供完整项目图，容易把缺失关系画成事实；舍弃 |
| 等宽三栏 | `Finding / Source / Explanation` | 路径成为附属信息，较窄屏幕三栏同时挤压；舍弃 |
| 选中项追踪工作台 | `Index / [Trace above Source + Explanation]` | 路径有明确数据边界，源码为主，解释可随宽度下移；采用 |

第一轮设想中的大号指标与多色风险块已收束为一行计数和文字状态。最初的任意节点源码预览也移除，因为报告仅带当前 Evidence 的片段。方案自审以这些事实约束保证产品辨识度。

### 3.2 独特选择

- 新增参数的改动标记同时出现在计划签名和路径末端，使 Change 有具体落点。
- 调用路径连接的是实际 Symbol 和调用点；标记、连线与编号均编码现有事实。
- Direct 的单位是调用点，Indirect 的单位是上游函数，界面保留不同单位。
- 中文解释与源码同处一个阅读任务中，静态判断原因先于辅助解释。
- 一份没有影响的报告依然提供完整覆盖说明，空白不会被 Demo 内容填充。
- 代码中的英文字标和中文说明采用不同阅读节奏，整个产品保持代码审查工具的气质。

## 4. 六色基础 Token

| Token | 名称 | Hex | 使用范围 |
| --- | --- | --- | --- |
| `--oi-canvas` | 工作底板 | `#E8F0F3` | 页面底色、静态背景 |
| `--oi-surface` | 阅读面 | `#FFFFFF` | 表单、源码、说明的主要阅读区域 |
| `--oi-ink` | 文字墨 | `#18343D` | 正文、标题、代码、未解析和 unknown 的中性文字 |
| `--oi-rule` | 结构线 | `#7B949C` | 分区、白底控件边界；不用于小字号正文 |
| `--oi-trace` | 轨道青 | `#006D77` | 主操作、当前选中、已知路径、读取或校验成功 |
| `--oi-change` | 改动铜 | `#A8432D` | 新增参数、Direct 兼容性退化、错误重点 |

六色为唯一基础色来源。次级文本、轻底色和淡分隔线由这些色混合而来，不再逐页添加颜色。建议次级文本使用墨色 76% 与白色 24% 的混合；结构背景只用浅混合，正文依然使用可读的深色。

按 WCAG 相对亮度公式计算的规划对比度：墨/白 13.15:1，墨/底板 11.39:1，轨道青/白 6.08:1，改动铜/白 5.99:1，结构线/白 3.20:1；上述次级文本/白约 6.16:1。结构线用于白底输入边界时满足 3:1；在底板上只作装饰分隔，交互边界改用更深的墨或轨道青。实际实现仍需检查 hover、disabled、focus 与混合色。

正文对比度目标至少 4.5:1，必要的非文本交互标识目标至少 3:1；标准依据见 [WCAG 对比度说明](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)。

### 4.1 颜色与证据状态

| 状态 | 表达 | 语义约束 |
| --- | --- | --- |
| Direct | 改动铜细标记、实心端点、文字“调用从兼容变为不兼容” | 不推导业务风险为 high |
| 1-hop / 2-hop | 轨道青路径、空心上游节点、文字“建议检查” | 连线仍表示已解析的调用；节点空心表示影响需要检查 |
| manual_review | 中性边界、独立“需人工检查”标签与原因 | 不混入确定 Direct 和传播线 |
| unresolved | 中性文字、未知关系标记与原始表达式 | 不绘制猜测性连接 |
| partial | 顶部持续可见的“覆盖不完整”提示，附可查看诊断 | 不依赖颜色，不藏在折叠区内 |
| unknown 业务风险 | 中性文字“业务风险未知” | 不沿用 Direct 的改动色作为风险等级 |
| unavailable | 明确不可用标签、诊断与原静态结论 | 不隐藏影响或借用其他项填空 |

## 5. 中英文与代码字体

| 角色 | 方案 | 使用原则 |
| --- | --- | --- |
| 英文品牌与界面 | IBM Plex Sans，400/500/600 | OpenImpact 字标、标题、按钮和拉丁文本；不使用全大写装饰标签 |
| 中文阅读 | 思源黑体简体 Source Han Sans SC，400/500/600 | 中文正文、说明、表单；回退 PingFang SC、Microsoft YaHei、Noto Sans CJK SC、sans-serif |
| 源码与 Symbol | IBM Plex Mono，400/500 | 源码、函数签名、Symbol ID、文件位置、哈希与规则 ID；中文回退至中文阅读字体 |

字体选择意图是把工程字标、中文阅读和代码核对区分开。避免把整页 UI 都设成等宽字体，也避免用宋体承载密集控件。

[IBM Plex](https://github.com/IBM/plex) 和[思源黑体](https://github.com/adobe-fonts/source-han-sans)为开源字体项目。后续实施时核对具体字体文件及许可证，保留许可说明；本轮没有下载或新增字体资产。中文字体先用系统回退保证离线演示，若打包 Web 字体，只加载必要字重和合法分片，不能只覆盖固定 Demo 汉字。缺字、字体未加载时界面必须仍可用。

### 5.1 字号、行长和权重

| 用途 | 桌面字号 / 行高 | 手机 | 权重 |
| --- | --- | --- | --- |
| 产品字标 | 22px / 1.15 | 20px | 600 |
| 页面标题 | 28px / 1.3 | 24px | 600 |
| 区域标题 | 18px / 1.4 | 18px | 600 |
| 中文正文与主要输入 | 16px / 1.65 | 16px | 400 |
| 按钮、列表主项、标签 | 14px / 1.5 | 14–16px | 500 |
| 代码与签名 | 14px / 1.65 | 14px | 400 |
| 元数据 | 13px / 1.5 | 13px | 400 |
| 紧凑统计值 | 20px / 1.2 | 20px | 600 |

所有字号通过 rem 建立，尊重浏览器缩放。800/900 不进入常规权重表。解释区每行约 28–38 个汉字，英文段落不超过约 70–80 字符；文字左对齐，不两端对齐。长 Symbol 在合适的分隔点换行，完整值始终可见；代码保留原格式，仅代码视口允许横向滚动。未知的默认参数值继续显示 `…`，不臆造源码值。

## 6. 间距、边界与组件层次

- 间距：4、8、12、16、24、32、48px。标签到输入 8px，字段间 16–24px，独立区域间 24–32px。只在图标与细线对齐时使用 1–2px 修正。
- 容器：普通内容用空白分区；输入控件 6px 圆角，源码/证据阅读面 8px，菜单或独立浮层 10px。药丸形只用于短状态，不套用于段落或所有按钮。
- 边界：普通结构线 1px，选中标记 3px，键盘焦点 3px 并留 2px offset。不用整页反复加粗框，也不用每张卡片同一阴影。
- 高度：输入和主要按钮 44px；函数可选行至少 56px；手机影响行至少 64px。点击区域有完整文字和焦点。
- 层次：页面底板 → 主要阅读面 → 当前选中 → 临时浮层。阴影仅用于实际叠层，底板和普通内容保持平面。
- 图形：统一 16/20px 线性图标和相同线宽；装饰图标 aria-hidden，独立图标按钮有完整名称。路径连线由 CSS/SVG 表达已有关系，无需引入图形布局库。
- CSS：统一 `oi-` 前缀与 Token，组件范围内控制选择器。迁移页面不靠全局 `.card`、`.section` 或不断追加 `!important` 覆盖旧样式。

## 7. 整体页面布局

桌面采用紧凑工作栏、当前项目条与任务内容。四个工作步骤是实际过程，允许使用步骤号；Change/Trace/Evidence 三个阅读概念不另加装饰编号。

```text
OpenImpact       current project / original ZIP       mode / connection / new project
----------------------------------------------------------------------------------
Upload  ->  Select function  ->  Configure change  ->  Read report
----------------------------------------------------------------------------------
Page task / coverage / contextual action

Task-specific content
```

桌面侧边工作栏建议宽 72px，必须保留可见文字或展开标签，不能变成只靠图标猜测。整体内容最大宽约 1600px；桌面横向留白 24–32px，手机 16px。顶栏建议高 56–64px。四步进度压成一条，不继续占据整组大卡片。

全局保留：当前项目与文件、明确的演示模式标识、连接检查、新项目操作。已选但未读取的 ZIP 不能冒充已确认项目。演示标识必须持续可见；真实项目状态仅给简短会话提示，细节可在说明中展开。

主导航不展示全项目搜索、历史、依赖分析等未实现能力。已有 planned 页面可保留原路径，入口降到范围说明。没有将“文档”按钮跳到真正资料页前，不把它包装成已完成能力。

## 8. 四个业务页面

### 8.1 上传项目：建立可信的项目起点

左侧为主上传区，右侧为简短边界说明和独立演示入口；不把演示做成与真实上传同等的主按钮。

主操作保持“选择 ZIP → 读取项目”。文件选中后展示真实名称、体积和“尚未读取”；Inspect 中展示阶段反馈，成功后展示可选择的函数数量与 coverage。项目指纹显示短摘要，完整值作为项目详情保留。上传按钮支持键盘，拖放区有 focus-within，不能只支持拖拽。

```text
Upload Python project
------------------------------------+-----------------------------
Choose / drop ZIP                   | Python / module functions
Selected filename / size / status   | Add required parameter
Read project                       | Explicit demo entry
------------------------------------+-----------------------------
Contextual error or parsing coverage
```

把刷新后重新选择、换 ZIP 清空旧结果的提醒放在文件状态附近。不得改 `actions.selectFile` 和原始 File 的存储位置。

### 8.2 选择函数：识别一个准确的 Symbol

主区域直接进入已有函数搜索与列表；项目名、文件数量、函数数量、coverage 压成摘要行。以完整 Symbol ID 作为主识别内容，以相对文件、行号和结构化签名补足上下文。同名函数不靠短名称区分。

列表保留当前 Inspect 的真实数据。选中状态显示清楚的轨道标记与参数预览；“配置变更”依然使用现有 selected 与 busy 条件。搜索无匹配和项目无可支持函数是两种不同空状态。

手机采用可选行：Symbol 一行，文件位置与参数在下方；不裁切桌面四列表格。重复显示同一 Symbol 不产生另一套选中状态。

### 8.3 配置变更：把计划与校验结果分开

当前目标和当前签名为上下文，新增参数表单为主操作，Validate 后签名对比作为明确结果。大屏可左右并排，小屏顺序为目标 → 输入 → 校验。

参数类型文案：普通位置或关键字参数 / `positional_or_keyword`；仅位置参数 / `positional_only`；仅关键字参数 / `keyword_only`。选项真实值不改。`insert_before` 继续为可选插入位置，未通过后端验证时不提前显示合法 after 签名。

签名对比只显示结构化事实：before 来自当前目标或已验证 ChangeSpec，after 来自 `validation.change_spec.after`。新增参数用改动铜与文字标识；这是计划签名，不标成已经修改的源码或 Git diff。无参函数继续显示 `page()`。

“校验变更”和“开始分析”是不同操作：只有真实 validation.valid=true 才允许分析。字段附近展示可定位的诊断；无法定位的诊断保持区域摘要，不在前端重新实现签名规则。

### 8.4 分析报告：Tracework 的主要展示场景

首屏顺序：当前变更 → coverage → 紧凑计数 → 当前影响的路径与源码。目标是让第一次观看比赛演示的人尽快看见真实代码依据。

```text
Change: current target / planned signature / added required parameter
Coverage notice, if incomplete
Direct call sites n | 1-hop symbols n | 2-hop symbols n | manual n | unresolved n
---------------------------------------------------------------------------------
Impact index        | Selected trace (only supplied, resolved call relationships)
                    | upstream -> upstream -> direct caller -> changed target
Direct call sites   |             each edge has its actual call location
1-hop symbols       +-----------------------------------+-------------------------
2-hop symbols       | Evidence                          | Chinese explanation
                    | relative file / line / column     | summary
Manual / existing   | actual source snippet             | why / suggested check
problems separately | static rule and reason            | unknown risk stays neutral
                    +-----------------------------------+-------------------------
                    | Collapsible evidence metadata / diagnostics
```

索引约 232–280px，证据区占剩余主宽度。足够宽时解释在源码右侧，空间不足时放在源码下方。列表采用紧凑记录，不为每项重新堆叠完整说明。当前项保持轨道标记，选中后联动路径、证据、静态原因和解释。

#### 8.4.1 追踪带的真实数据边界

- Direct 的 Evidence `propagation_path` 为空。可从当前 Finding 的 caller、target 和调用位置呈现一条确定调用边；不添加其他调用者。
- Indirect 使用对应 Evidence 已有的 `propagation_path[].symbols/call_sites/direct_evidence_reference`。原始 Finding 的 `sources[].propagation_path` 和 `direct_call` 是其依据，不能画出其他路径。
- 上游函数名称取 Finding 的 `impacted_symbol_id`；Evidence 的 `target_symbol` 仍是本次 Change 的修改目标，不能把两者混为同一节点。
- 调用方向保持 caller → callee。OpenImpact 从修改点向上寻找影响，视觉连线依然表达真实调用方向。
- 路径中最后一条 Direct 调用用改动标记；上游节点标明“建议检查”。这些标记不能声称上游一定运行失败。
- 1-hop/2-hop 标签来自 `impact_type`。当前 `graph_distance` 包含末端 Direct 边，实际为 2/3，不能直接作为 UI hop 数。
- 一个间接 Symbol 可关联多个 Direct 来源。展示已有的有限路径并说明代表性，不标“全部路径”。源码片段只有该项的最短代表调用位置，不能因查看另一路径就生成新源码或换用无关解释。
- 点击节点只定位已经展示的 Symbol/位置；有对应完整 Direct 记录时可选中该记录。无法唯一定位时保留位置文本，不提供任意函数源码加载、文件全文或全项目图浏览。

说明性 Demo 可使用真实链 `page.page → dashboard.dashboard → report.report → utils.format_date`。该链仅用于解释布局，正式页面一切节点、位置、统计和解释均读取本次报告。

#### 8.4.2 Evidence 与 Explanation 联动契约

设计继续调用 [reportData.js](src/pages/reportData.js) 已有的 `reportFindings`、`correspondingEvidence`、`correspondingExplanation` 与完整性诊断，不另写关联方法。

确定 Finding 顺序为 `[...direct_impacts, ...indirect_impacts]`。每项保留原始索引；分组、视觉布局或未来显示筛选均不得重新编号 Evidence/Explanation。Explanation 的内嵌 Evidence 必须是同索引的完整快照匹配。`evidence_reference` 可能由多项共用，不能作为所有影响的唯一关联键。

源码面板展示匹配 Evidence 的 `location`、`source_snippet`、`call_expression`。源码按普通文本渲染，保留原格式与真实行号；不能补造上下文行。行号从 1 开始，column 从 0 开始，源码列偏移不因排版被重新解释。

静态规则和原因来自 `rule/reason`，在中文辅助解释之前可见。解释使用 `summary/why_affected/suggested_check`；`risk_level`、`confidence` 放次层元信息，置信度不能显示成故障概率。完整 `source_hash`、`evidence_reference` 和位置细节进入可展开证据资料，哈希注明是完整源码文件原始字节的 SHA-256。

中文辅助解释不加聊天气泡、输入框、打字动画或模型头像。现有 API 没有 Provider 成功来源，不能标成 DeepSeek 已成功、模型正在思考或 fallback 已触发；Explanation 为空时保留可用源码和静态判断。

#### 8.4.3 统计与不确定性

| 展示内容 | 数据来源 | 规则 |
| --- | --- | --- |
| 变更目标与计划签名 | `report.change.target_symbol_id/before/after/added_parameter` | 不硬编码 Demo 目标 |
| Direct 数量与记录 | `summary.direct_impact_count`、`direct_impacts` | 调用点数量，保留同一 caller 的多个不同调用 |
| 1-hop / 2-hop | `summary.indirect_1hop_count/indirect_2hop_count`、`indirect_impacts` | 上游 Symbol 数量，不与 Direct 相加称为函数总数 |
| 人工检查 | `manual_reviews`、`summary.manual_review_count` | 独立展示 before/after 和原因，不占 Evidence 槽位 |
| 既有问题 | `pre_existing_problems` | 修改前已存在，不归因于本次变更 |
| 未解析调用 | `diagnostics.unresolved_calls`、`summary.unresolved_call_count` | 仅显示 expression、位置和原因，不猜 caller/callee |
| 覆盖范围 | `coverage.status/message` 与其他 coverage 字段 | complete 仅为支持范围完成；partial 持续提示 |
| 对应和解析诊断 | `diagnostics` 与已有报告完整性检查 | 保留原始计数，不补造结果修复展示 |

Analyze 没有 `project_fingerprint` 字段；项目指纹若显示，只能取当前已确认 Inspect 状态，不伪造报告字段。兼容调用、兼容性改善的完整列表没有返回，当前设计不增加这两种结果页。

## 9. 响应式、键盘与交互反馈

| 宽度 | 报告布局 | 其他页面 |
| --- | --- | --- |
| ≥1440px | 影响索引 + 宽证据区 + 解释侧区；路径横跨证据与解释上方 | 上传、选择、配置可并排上下文 |
| 1024–1439px | 索引 + 主阅读区；解释位于源码下方 | 摘要压缩，内容留宽；不把全部统计变成独立长卡 |
| 768–1023px | 顶部项目条和水平步骤；影响索引缩为紧凑列表，选中详情在其后 | 表单两区或单列，保留项目上下文 |
| <768px | 单列，路径按调用顺序竖排；选中项后立即出现详情 | 函数行改 label/value；按钮触控区至少44px |

以 360、390、768、1024、1440、1920px 及 200% 缩放作为后续检查尺寸。源码可局部横滚，页面不出现整体横向溢出。不能靠 body overflow-x:hidden 隐藏被裁切的内容。

桌面仅将紧凑项目/变更上下文和局部索引设为 sticky；内容正常滚动优先，避免同时制造三个独立长滚动区。手机不使用覆盖大部分屏幕的固定底栏，不隐藏 partial 和错误。点击影响后详情获得可识别标题和选中状态，键盘焦点不被强制移走；必要定位要尊重 reduced-motion。

按钮和可选行支持默认、hover、focus-visible、pressed、disabled、loading。焦点框清晰，不以 hover 作为唯一反馈；拖放区保留 file input 的键盘路径。触控目标以 44px 为产品目标，高于 [WCAG 2.2 最小目标尺寸](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)的 24px 基准及其例外条件。

动效仅回应用户操作：120–180ms 的选中边界/内容状态变化，不播放无限路径流光，不逐字生成解释，不给每块内容入场动画。`prefers-reduced-motion` 下即时显示新状态，文字反馈和焦点仍完整保留。Step 2.5 按已确认的动态交互任务引入 Motion for React，仅用于方向性的页面切换；其他效果使用 CSS 与 Web Animations API。节奏、生命周期保护与 Skill 应用记录见 [MOTION.md](MOTION.md)。

### 9.1 反馈与恢复状态

| 情况 | 展示及可操作方向 |
| --- | --- |
| 等待文件 | 主上传动作、Python/模块级函数/新增必填参数边界 |
| 已选 ZIP、尚未 Inspect | 文件名与体积，状态为已选择，允许读取；没有完成勾 |
| Inspect / Validate / Analyze 中 | 使用对应 loading 状态、忙碌名称和 aria-busy；禁用重复操作，不伪造百分比进度 |
| 无效 ZIP / 后端不可达 | 当前操作旁显示安全错误和恢复步骤，保留现有 File 行为；不加载 Mock |
| 无可支持函数 | 显示实际 coverage/diagnostics，停止后续动作，不默认选 Demo |
| 参数错误 | 保留输入，显示后端诊断，要求再次校验；不自动寻找插入位置 |
| fingerprint_mismatch | 提示项目版本不一致；按现有逻辑清空失效上下文，保留原 File，要求重新读取 |
| 0/0/0 + complete | “当前已解析范围内未发现本次变更造成的确定影响”；保留人工检查与诊断 |
| 0/0/0 + partial | 同时明确覆盖不完整，不能推断整个项目无影响 |
| Evidence unavailable | 保留影响、位置和计数；本项显示不可用原因，无代码替补 |
| Explanation unavailable | 可用证据继续显示，提供静态原因与解释诊断 |
| 新 ZIP / 新 Symbol / 新参数 | 原失效结果按现有逻辑消失，不能继续显示旧路径、代码、解释 |
| 刷新浏览器 | 按既有内存会话行为回到缺少 File 的状态，明确要求重新选择；不设计历史恢复 |

采用现有 ErrorNotice/coverage 判定和已有请求状态。静态提示可收束文案，但演示、partial、错误与不确定性信息不能降为不可发现的小字。常驻长说明归入展开区，错误恢复方向留在当下。

## 10. 后续实现范围与业务保护

以下为待审核的实施建议，本轮未执行。

| 范围 | 预计文件 | 调整内容 |
| --- | --- | --- |
| 视觉基础 | `styles.css`、`src/react.css`；可新增 `src/tokens.css` 并在 `src/main.jsx` 引入 | 六色、字体、尺度、网格、状态和响应式 |
| 工作台外壳 | `src/components/AppShell.jsx`、`WorkflowSteps.jsx`、`EmptyState.jsx` | 导航、项目上下文、步骤和空状态布局 |
| 共享呈现 | `src/pages/PageParts.jsx` | 提示层级、诊断折叠和焦点表达；保留判定条件 |
| 四页面 | `src/pages/UploadPage.jsx`、`FunctionSelectPage.jsx`、`ChangePage.jsx`、`ReportPage.jsx` | JSX 分区和呈现，不重写业务动作 |
| 报告纯呈现组件 | 可新增 `src/components/report/TraceStrip.jsx`、`EvidencePane.jsx`、`ExplanationPanel.jsx` | 只接收已匹配 Finding/Evidence/Explanation 与原索引；不请求数据、不绑定 Symbol |
| 回归 | `tests/reportRendering.test.js` 等已有前端测试 | 补视觉重排后的可用性和安全展示检查，保留既有语义断言 |

保护清单：`src/api/client.js`、`src/state/actions.js`、`src/state/workflow.js`、`src/state/WorkflowContext.jsx`、`src/pages/reportData.js`、演示 JSON/ZIP、后端 `src/openimpact/` 和公开 API 文档。API Client、ZIP File 生命周期、指纹、Inspect/Validate/Analyze、AbortController/revision、Evidence/Explanation 对应机制保持原样。

组件拆分不移动 WorkflowProvider，不重新保存 File，不因视觉页面切换触发业务请求。ReportResults 现有“新报告替换后重置选中项”的保护也保留。报告 UI 只持有选中/展开等局部呈现状态；能从当前响应导出的文本和路径不另存为跨项目全局状态。

## 11. 风险与下一阶段验收

| 风险 | 约束与验证 |
| --- | --- |
| JSX 分组后索引错配 | 保留原始 Finding 索引与现有匹配函数；同一行不同 column、多来源、缺失槽位逐项验证 |
| 视觉路径被误认成全项目图或运行失败保证 | 标注当前选中记录及代表路径；Direct/Indirect 文案和单位保持准确 |
| 改版重新挂载业务状态 | WorkflowProvider 与原 actions 保持；A → B、换 ZIP、改参数、409 和晚返请求继续回归 |
| 字体体积、缺字或离线加载 | 系统回退先可用；具体打包资产单独核验；中英文与长 Symbol 实测 |
| 新 CSS 与旧选择器抵消 | 逐区域迁移、专用前缀、统一 Token；不通过全局重要声明掩盖冲突 |
| 手机折叠隐藏关键事实 | coverage、模式和当前错误始终可发现；源码/解释降级不改变静态记录 |
| 风险/置信度误读 | unknown 中性，confidence 仅为解释字段；不产生高风险评分或模型来源标签 |

后续顺序：先实现外壳与尺度，再四页，最后实现报告追踪联动。每步只改呈现层并运行适当回归。完成后使用 Impeccable 的 critique/audit/polish 思路，分别核对产品层次、可用性与最后一致性；审查结论需基于实际页面，不能由静态规则分数代替。

实现验收必须重新运行 `npm run check`、`npm run build`，并在 rule 后端完成真实浏览器 A（utils.format_date + timezone，1/1/1、complete）与 B（page.page + zone，0/0/0、complete），检查旧证据和解释无残留。还需验证 partial、manual_review、unresolved、unavailable、409、离线恢复、键盘、触控目标与上述尺寸。受控故障注入和真实自然触发的结果分开记录。

本轮交付为设计方案，不宣称这些布局、字体或交互已经实现。负责人审核本规范后再进入 UI 实施；不自动 commit、push 或 merge。

## 12. 本轮参考原文位置

- 主导：[Anthropic frontend-design SKILL.md](https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md)，完整读取。
- 辅助：[Taste SKILL.md](https://raw.githubusercontent.com/Leonxlnx/taste-skill/main/skills/taste-skill/SKILL.md)，读取与本项目相关的视觉、布局和状态章节。
- 辅助：[UI UX Pro Max SKILL.md](https://raw.githubusercontent.com/nextlevelbuilder/ui-ux-pro-max-skill/main/.claude/skills/ui-ux-pro-max/SKILL.md)及其 [React 参考](https://raw.githubusercontent.com/nextlevelbuilder/ui-ux-pro-max-skill/main/.claude/skills/ui-ux-pro-max/data/stacks/react.csv)，未执行自动主题搜索；布局与颜色由本规范自行确定。
- 后续审查参考：[Impeccable](https://raw.githubusercontent.com/pbakaus/impeccable/main/.agents/skills/impeccable/SKILL.md)、[critique](https://raw.githubusercontent.com/pbakaus/impeccable/main/.agents/skills/impeccable/reference/critique.md)、[audit](https://raw.githubusercontent.com/pbakaus/impeccable/main/.agents/skills/impeccable/reference/audit.md)、[polish](https://raw.githubusercontent.com/pbakaus/impeccable/main/.agents/skills/impeccable/reference/polish.md)，本轮仅参考相关审查方法。

辅助仓库核验时 UI UX Pro Max main 为 `477bcb2`，Impeccable main 为 `e103efe`。这些链接是外部参考，不作为可执行项目配置；实现时若参考更新，仍以项目边界与主导设计方法为准。
