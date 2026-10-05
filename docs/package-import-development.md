# 普通包与源码根目录开发记录

基线：`ffaafae`，已收束中文化与真实项目审计。分支 `feature/package-imports`。

## 范围与决策

- 用户显式选择 `analysis_root`；缺省 `.` 保留原项目根映射。不执行构建脚本，也不自动猜测多根布局。
- 选定源码根目录与项目根共同建立项目内静态索引，其他文件如 tests 保留项目相对位置。相同模块出现于两个根时拒绝绑定。
- 仅为具有真实 `__init__.py` 的普通包绑定相对导入；namespace、越界、冲突、语法错误和 `__path__` 重绑定保守诊断。
- Module/Symbol 变更的 flat-root 范围不扩展。Signature 的兼容判定和传播算法复用现有实现。
- API 追加可选 multipart `analysis_root` 与非默认布局元数据；原字段、旧 payload 和旧报告保持。
- 明确记录被排除的类/嵌套/lambda 调用作用域，作为 coverage 诊断，不生成猜测的确定影响。
- Web 保留同一 ZIP、fingerprint、源码根目录和 revision；改变根目录清除所有过期结果并取消旧请求。

## 进展

- 已创建独立工作树；环境安装首次受系统 SOCKS/缓存配置影响，改用进程内空代理与独立 npm 缓存，不修改系统配置。
- 布局与解析：完成显式根目录、普通包相对导入、父包检查、双根冲突、包成员遮蔽和包上下文重绑定诊断。没有新增 Change Type，也没有改写兼容判定或传播算法。
- API/CLI：三个上传阶段与 CLI 共用目录校验；旧请求缺省仍为 `.`。验证非默认布局在三个领域中携带一致元数据，空目录、越界、重复字段和错误指纹明确拒绝。
- Web：完成源码目录输入、同一 File 重复上传、revision/AbortController 取消、校验快照和返回布局核对。同值输入不误取消在途请求。
- 专项与完整回归：最终完整 Backend `862 passed, 2 skipped, 1 warning, 7 subtests passed`；Frontend `199 passed`；production build PASS。两个 skip 为 Windows 环境无法创建符号链接的测试；warning 为既有 Starlette/httpx 弃用提示。
- 真实项目：固定 python-dotenv 源码复验通过，19 文件、96 函数、41 确定调用位置；源文件未变，HTTP 与本地报告一致，10 个临时目录全部清理。
- 浏览器：真实 rule 后端与当前前端完成旧 A/B 案例、新普通包案例、python-dotenv src 案例及目录改变后的状态清除。1440/768/390px 核查无横向溢出，无浏览器错误记录。

## 最终验收与保留边界

- 旧 14 个 Demo 与 `ffaafae` 下输出逐字段一致，仅将本机 checkout 不同造成的 `project_path` 统一为 `.` 后比较；未归一化源码哈希、计数或规则。
- 新普通包 Demo 为 1/1/1 complete；python-dotenv parse_stream 为 3/2/0 partial，parse_key 为 1/1/3 partial。它们是功能观测，不是独立 Benchmark 准确率。
- 原相对 import 测试只将已明确支持的普通包断言更新为 resolved，wildcard 拒绝断言保留；新增 namespace、重绑定、冲突等拒绝回归。
- 完整验收见 [package-import-acceptance.md](package-import-acceptance.md)，支持边界与操作见 [package-imports.md](package-imports.md)。
- native reduced-motion verification 与 independent Benchmark 仍保留原 pending，自动化模拟不等同系统人工补验。
