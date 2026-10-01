# Nexus OpenImpact Demo API 契约

Phase 2.1 只提供仓库内置 `examples/signature_change/` 的分析。服务调用现有 `load_change_spec()`、`analyze_project()` 和 `build_report()`；不接收项目路径、ChangeSpec 请求体或 ZIP。

## 本地启动

在仓库根目录安装项目后运行：

```powershell
pip install -e .
python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000
```

运行自动化测试时可安装 `pip install -e ".[test]"`；`httpx` 和 `pytest` 位于该可选依赖中。服务入口为 `openimpact.api:app`。目前 Demo 从当前源码仓库读取，运行服务时需保留 `examples/signature_change/`。

## `GET /api/v1/health`

无需请求体。成功响应为 HTTP 200：

```json
{"status": "ok", "version": "0.1.0"}
```

## `POST /api/v1/demo/analyze`

无需请求体或查询参数。例如：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/demo/analyze
```

成功响应为 HTTP 200，直接返回 Core CLI JSON 模式使用的 `build_report()` 结果。顶层字段保持为：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 当前为 `1` |
| `project_path` | 内置 Demo 的本地目录 |
| `change` | 结构化 ChangeSpec |
| `validation` | ChangeSpec 校验结论和诊断 |
| `coverage` | 覆盖状态、模块与解析计数 |
| `summary` | Direct、1-hop、2-hop、人工检查等计数 |
| `direct_impacts` | 本次变更确定造成的直接影响 |
| `indirect_impacts` | 上游待检查符号及原始调用路径 |
| `manual_reviews` | 静态证据不足的调用 |
| `pre_existing_problems` | 修改前已有的不兼容调用 |
| `diagnostics` | 解析错误、未解析调用与 import |

固定 Demo 的 `summary.direct_impact_count`、`summary.indirect_1hop_count`、`summary.indirect_2hop_count` 均为 `1`，`coverage.status` 为 `complete`。Indirect 表示建议检查的上游调用路径，不承诺运行时失败。

## 错误响应

本阶段由服务显式处理的错误使用以下 JSON 形状：

```json
{"error": {"code": "unsupported_input", "message": "Demo 接口不接受项目路径、查询参数或请求体。"}}
```

| HTTP 状态 | `error.code` | 场景 |
| --- | --- | --- |
| 400 | `unsupported_input` | Demo 请求包含查询参数或非空请求体 |
| 503 | `demo_unavailable` | 内置 Demo 文件缺失或无法读取 |
| 503 | `demo_invalid` | 内置 ChangeSpec 与项目源码校验失败 |

未知路径或 HTTP 方法仍由 FastAPI 返回标准 404 / 405 响应。当前接口无认证、持久化任务或任意项目分析能力，仅供本地 Demo 和外部应用集成验证。
