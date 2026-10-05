# 普通 Python 包跨文件追踪验收

开发基线 `ffaafae`，分支 `feature/package-imports`。本轮保留三领域八种操作，新增显式源码根目录与普通包相对导入能力。未调用外部模型，验收使用 rule 模式。

## 实际结果

| 检查 | 结果 |
| --- | --- |
| 当前工作树独立 editable install | 成功，测试使用该工作树源码 |
| 完整 pytest | 862 passed、2 skipped、1 warning、7 subtests passed；50.08s |
| Frontend check | 199 passed、0 failed |
| Production build | 成功 |
| 原 14 个 Demo 报告 | 与基线逐字段一致，仅项目绝对路径统一为 `.` |
| 旧 Web format_date + timezone | 1/1/1，complete |
| 旧 Web page.page + zone | 0/0/0，complete；无旧证据与解释 |
| 新包内 Web trace_demo.utils.format_date + keyword-only timezone | 1/1/1，complete |
| 新包 Evidence | `src/trace_demo/report.py:5:11`，`return fd(date)` |
| 新包 2-hop 路径 | page → dashboard → report → format_date，完整模块标识均来自后端 |
| python-dotenv Web parse_stream + keyword-only strict | 3/2/0，partial；514 条未解析调用，范围缺口提示保留 |
| 改变源码根目录 | 原 ZIP 保留，旧 Inspect、选择、Validate 和报告清除 |
| 1440 / 768 / 390px | 页面无横向溢出，手机源码目录输入可操作 |
| 浏览器控制台 | 无 error / warn 记录 |

两项 skip 为本机符号链接创建权限限制，未删除对应测试。warning 为既有 Starlette/httpx 弃用提示。源码片段按文本显示，Evidence 与 Explanation 原匹配规则保持。

## 真实项目核查

python-dotenv v1.1.1 固定 commit `16e660d384b942b11879b44500afbbe021650448`。19 个 Python 文件、19 模块、96 模块级函数、41 确定调用位置。原布局审计为 22 个确定调用位置；本轮确认增加的跨文件追踪来自显式 src 根与相对导入，不能解释为准确率提升百分比。

三个 HTTP 阶段使用同一原始 ZIP、指纹和 `analysis_root=src`。四个目标与本地分析一致，证据源码哈希核对通过，10 个隔离目录全部清理；错误指纹返回 409，嵌套 Module 目标返回 422。全部 upstream 源码保持不变，没有执行它的安装脚本、模块或测试。

| 目标 | Direct / 1-hop / 2-hop | 范围 |
| --- | --- | --- |
| dotenv.parser.parse_key | 1 / 1 / 3 | partial |
| dotenv.parser.parse_stream | 3 / 2 / 0 | partial |
| dotenv.main.find_dotenv | 2 / 3 / 0 | partial |
| dotenv.main.load_dotenv | 0 / 0 / 0 | partial，公开 re-export 未解析，不可宣称无其他影响 |

这些结果为源码功能核查；没有生成、锁定或修改人工 Ground Truth，也没有运行正式准确率评估。

## 修改范围与兼容性

- 新增 `repository/layout.py`：严格项目相对目录校验与统一模块命名。
- `symbol_index.py`：普通包相对 import、父包检查、上下文重绑定与同名子模块遮蔽保护；Module/Symbol 目标仍限制物理项目根普通文件。
- AST 仅增加已排除作用域事实，不将类方法、嵌套函数或 lambda 纳入正式函数调用图。
- Pipeline、CLI、ZIP 和 API 传递可选根目录；默认布局不增加 analysis_layout 字段。原 schema_version、八种 payload、指纹算法不变。
- React 增加上传页面的目录设置及状态失效保护；不改动 Change Draft、报告 Evidence 匹配、Tracework 动效或公开端点。
- 新增普通包 Demo、后端与前端测试；维护 API/交接说明和真实项目审计脚本。

完整文件列表可用 `git show --name-status` 查看本轮提交；截图、实际 HTTP 输出和测试日志仅位于忽略的 `.local`，未纳入交付源码。Evaluation 工作树中的未提交评测材料保持原样。

## 保留限制

显式目录声明用户导入环境；不模拟 sys.path、安装器、多根自动发现、namespace 搜索、所有 package 初始化副作用或第三方遮蔽。重导出、类方法、动态导入、复杂属性链等继续保守处理。诊断中的排除调用数不等同目标函数的漏报数；上游路径提示检查，不保证运行失败。

- native reduced-motion verification = pending
- independent Benchmark = pending

下一步适合补充可独立标注的真实 package Benchmark，再按具体语义逐项扩展重导出支持。
