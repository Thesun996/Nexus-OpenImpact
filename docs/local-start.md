# Windows 统一启动与环境自检

更新：2026-10-16（Asia/Shanghai）。固定使用现有 `Nexus-OpenImpact` 目录，不需要为每次更新更换目录。

## 常用启动

在仓库根目录的 PowerShell 中执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider deepseek -PromptKey
```

按提示隐藏输入 DeepSeek Key。Key 不写入文件、命令参数或启动输出，只传给本次 API 与 Worker，不传给前端 Node 进程。`ExecutionPolicy Bypass` 只对本次 PowerShell 进程生效，不修改系统策略。

若当前终端已经设置 `DEEPSEEK_API_KEY`，可以省略 `-PromptKey`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider deepseek
```

默认读取 `OPENIMPACT_LLM_PROVIDER`；未设置时选 DeepSeek。缺少 Key 会停止并提示，不会在启动器中静默改成规则模式。启动自检只检查 Key 是否存在，不验证余额、Key 有效性或外网连通性；运行时的模型失败继续遵守后端既有回退策略，实际来源以报告诊断为准。

启动成功后打开 `http://127.0.0.1:5173/`。终端会显示 API、Worker、前端 PID、实际模型模式、源码位置、共用数据库/快照目录及代理地址。保持终端打开；按 Ctrl+C 统一停止本次进程。已有任务仍由原任务租约规则处理，停止服务不删除任务、报告或项目数据。

## 只检查或快速探测

```powershell
# 不启动服务、不调用模型；仍会检查端口与目录可写性。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider deepseek -PromptKey -Check

# 规则测试：启动 API、Worker、Vite，验证页面、健康检查及代理后自动停止。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider rule -SmokeTest
```

`-Check` 与 `-SmokeTest` 互斥。SmokeTest 仅验证服务启动与代理，不能代替业务回归，也不会创建假分析结果。若数据库已有 queued 任务，启动的 Worker 会照常处理；验收时应使用独立数据库及快照目录。

端口被占用会明确停止，不结束已有服务、不自动换端口。可显式指定其他端口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider deepseek -PromptKey -ApiPort 8010 -FrontendPort 5174
```

此时打开 `http://127.0.0.1:5174/`，Vite `/api` 自动指向 `127.0.0.1:8010`。

## 环境和依赖

启动器依次寻找 `.local/python-env/Scripts/python.exe`、`.venv/Scripts/python.exe`、PATH 中的 `python.exe`。也可通过 `-Python "解释器完整路径"` 明确指定；不会把 Conda 或其他工作树中的 editable install 当作当前源码。

需要 Python 3.11+、满足 `frontend/package.json` engines 的 Node.js 与 npm。首次准备环境示例：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Push-Location frontend
npm ci
Pop-Location
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Python .\.venv\Scripts\python.exe -Provider deepseek -PromptKey
```

如果 `.local/python-env` 已存在，默认会优先使用它；依赖应安装到实际选用的环境中。启动器不自动安装依赖、不升级环境、不修改 editable install。它为 API 与 Worker 固定当前仓库 `src`，避免导入其他工作树的代码。

API 与 Worker 共用相同的绝对 `OPENIMPACT_DB_PATH` / `OPENIMPACT_SNAPSHOT_DIR`。未设置时使用仓库下 `.openimpact/openimpact.sqlite3`、`.openimpact/snapshots`；相对环境变量路径以仓库根目录解析。启动器覆盖子进程的 `OPENIMPACT_API_TARGET`，确保代理与本次 API 端口一致。

日志位于 `.local/run-local/<本次编号>/API.log`、`Worker.log`、`Frontend.log`，不应提交。启动过程中任一服务退出，会停止其余已启动服务并提示日志位置；运行期间也持续检查三个进程是否仍存活。日志可能包含本机路径或业务诊断，应在分享前检查。正常退出只处理本次启动的 PID；不按进程名称批量结束 Python 或 Node。强行结束启动器或断电后的恢复仍需人工检查。

## PR 自动检查

`.github/workflows/checks.yml` 在 main 的 PR、main Push 和手工触发时运行；Windows / Ubuntu 分别执行：

1. Python 3.12、Node.js 24 与项目依赖安装。
2. 完整 pytest、前端测试及生产构建。
3. 规则模式环境自检、实际启动 API / Worker / Vite 并验证代理后退出。
4. 合并变更的 whitespace 检查。

CI 使用临时数据库与快照目录，不读取真实 DeepSeek Key、不请求模型、不访问 A312。官方 Actions 固定到已核对的提交 SHA，权限为 `contents: read`，Checkout 不保留凭据。CI 检查配置与分支保护是两项独立设置；添加工作流不会自动禁止红灯合并。

进程管理参考 [Python subprocess 文档](https://docs.python.org/3/library/subprocess.html)；CI 参考 [GitHub Python 测试指南](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)、[官方 setup-node](https://github.com/actions/setup-node)、[官方 checkout](https://github.com/actions/checkout)。

## 当前边界

启动器检查 Worker 进程存活，尚无跨终端 Worker 心跳 API。它不证明队列没有积压、模型请求成功或真实项目完全可分析。不增加账号体系、自动修复或自动清理策略；原生 reduced-motion 与独立人工 Benchmark 仍待完成。
