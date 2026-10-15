# refine-project 修复记录

日期：2026-10-15（Asia/Shanghai）。起点：`a5e0550`。

按以下顺序修复，每项先复现再补实现；通过完整回归及浏览器验收前不合并 main。

| 顺序 | 问题 | 状态 |
| --- | --- | --- |
| 1 | R1：并发保存/删除共享 ZIP 导致快照文件丢失 | 已修复；2 个新回归用例从失败变为通过；存储/报告 API 专项 28 passed |
| 2 | R3：旧 Worker 发布重复报告 | 已修复；领取批次校验与报告/任务原子提交，3 个回归用例通过 |
| 3 | R2：删除报告后相同配置不能重新分析 | 已修复；API 删除/重试、前端显式重新分析均已验证 |
| 4 | R4：冻结源码清单不完整 | 已修复；新增/遗漏源码拒绝，沿用 Scanner 忽略规则 |
| 5 | R5：标签与真实 ChangeSpec 身份未校验 | 已修复；目标/类型交叉核对，未 locked 拒绝计分 |
| 6 | R6：零重合 F1 错误 | 已修复；18 项评测专项通过 |
| 7 | R7：Windows symlink 测试权限 | 已修复；19 passed、1 个无权限 symlink 用例跳过，其余安全断言保留 |
| 8 | 继承的契约样例 ZIP 指纹差异 | 已定位并修复；ZipInfo.create_system 默认取宿主系统，固定测试 ZIP 元数据为 3；6 项契约测试通过 |
| 9 | 文档格式与完整回归、浏览器验收 | 已完成；详见下文 |

## R1

共享 ZIP 的发布、快照引用建立、最后引用删除，统一使用同一 SQLite 数据库的 `BEGIN IMMEDIATE` 写事务串行化。没有增加依赖或修改分析规则。测试通过受控并发交错，分别验证旧快照删除和旧项目删除均会等待新引用提交，新快照仍能读取原始字节。

所有验收使用隔离数据库与受控样例；不修改人工 Ground Truth，不调用真实 DeepSeek。原生 Windows reduced-motion 与独立 Benchmark 的待办状态不变。

## R3 / R2

报告发布与任务完成共用同一事务，使用领取时的租约时间作为内部批次身份，不新增数据库 schema 或公开字段。旧批次和事务失败均不会遗留额外报告。报告删除会使关联任务明确失败并可显式重试；前端核对成功任务的新状态，兼容旧缺失结果的缓存清理。

## R4–R6

复用现有 Scanner 校验完整源码清单；在分析之前核对标签、Manifest 和真实 ChangeSpec。正式计分要求显式 locked，缺失时拒绝，不自动改写真实标签。零重合 F1 修正为 0；空分母继续 null。

## 平台与契约样例

原组合测试拆为始终执行的缺失/篡改用例和受权限约束的 symlink 用例。指纹差异根因已分别生成验证：相同源码及时间戳，create_system=0 得到 9ab9885b…，create_system=3 得到既有样例的 5f2bb406…。只固定测试 ZIP 的创建平台元数据，未修改生产指纹、样例答案或源码。

## 最终回归

- 后端完整 pytest：1112 passed、3 skipped、1 warning、7 subtests passed。跳过项为本机无 symlink 权限，不扩大业务 unsupported 范围。
- 前端 npm run check：274 passed，生产构建通过；含导航 CSS 修复后的最终复验。
- 14 个受控 Demo 通过保存快照→校验→Worker→报告；summary、coverage、evidences、explanations 与同步分析逐字段一致。
- 本次真实浏览器使用端口 5186→8016 的本分支服务和独立 Worker、隔离数据库：A 上传原始 ZIP 后完成 1/1/1 complete；删除隔离测试报告后，同配置再次分析成功；任务页显式重试成功；B page.page + zone 为 0/0/0 complete，无旧证据/解释。
- 浏览器控制台没有 error。额外发现并修复默认窄窗口的导航溢出，788px 视口从 scrollWidth=856 恢复为 788；1440、768、390px 视口检查页面宽度均未溢出（clientWidth 分别为 1425、753、375，保留滚动条宽度）。
- 使用 Ponytail 的最小改动原则；窄屏导航参考 UI UX Pro Max 的 Responsive / Horizontal Scroll 指南，仅自然换行，不隐藏入口。
- 截图和原始日志只放在忽略的 .local 中。源码 Core、AST、Call Graph、生产 Report schema、原八种 Operation 及真实人工标注均不改动。
- Worker 租约恢复允许重算，原子发布保证失效批次不写入重复报告；外部模型调用恰好一次不在本次保证范围。
- 原生 reduced-motion 验收与独立 Benchmark 仍为 pending。main 保持原样，待复审后再合并。

## 复审 P2 收束（2026-10-15）

复审基线 `8db722d`，新增两项缺陷，均已修复；不修改 Core、React、公开 API 字段、Report schema 或真实标注数据。

- RR1：多快照清理时，后一个 ZIP 删除失败会回滚数据库，前面已删除的文件无法恢复。现在先提交记录删除，再用独立写事务重新核对引用并清理；文件清理失败仅记录警告，保留无引用文件待重试。保存发生在两步之间时，新引用的文件受到保护。普通项目删除与单快照删除共用该路径。
- RR2：数组/对象等错误标签值进入集合后抛出未捕获 TypeError，导致整批 Runner 中断。现在在分析前校验匹配字段和 Coverage 的类型、取值，错误转换为逐案例 BenchmarkError。正常案例继续处理，CLI 保留完整结果并返回 2。未扩大异常吞噬范围，也未修改指标计算口径。
- 新增 23 个回归用例先在旧实现全部失败，修复后通过；包含已提交删除的可见性、清理失败后的重试、提交删除与清理间的新引用、错误标签矩阵和正常/错误/正常三案例 CLI 混合批次。
- 存储/评测/快照/任务/报告专项：97 passed、1 skipped。后端完整：1135 passed、3 skipped、1 warning、7 subtests passed。前端 npm run check：274 passed，Production Build 通过。
- Windows 原生 CreateFileW 文件锁及真实 API 复验：删除返回 200，快照记录为 0，保留 1 个被占用 ZIP；被删除快照请求返回 404。解除占用后，重试清理将剩余 ZIP 移除。该验证与原生 reduced-motion 无关，后者仍 pending。
- 14 个 Demo 的任务/同步分析结果继续逐字段一致；git diff --check 通过。原始日志在忽略的 .local/p2-*.log，不纳入提交。
- 当前限制：无引用文件清理没有自动重试队列，解除占用后需要维护清理；不会恢复出指向已删除 ZIP 的有效快照记录。独立 Benchmark 继续 pending。
