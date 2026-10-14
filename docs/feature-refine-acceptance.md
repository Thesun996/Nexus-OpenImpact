# feature/refine-project 验收记录

> 日期：2026-10-13（Asia/Shanghai）
> 分支：`feature/refine-project`
> 范围：本地报告历史持久化、筛选、分页加载与前端主流程回归。本文是早期验收记录；最新项目状态以 [current-project-status.md](current-project-status.md) 为准。

## 验收结论

当前分支在该验收时的可直接完成项已经完成到可提交状态：上传 ZIP、选择函数、配置变更、校验、分析、保存历史、筛选历史、分页读取历史报告均可用。后续已继续增加项目库快照复用、删除、本地分析任务基础和报告下载；最新范围见当前项目状态文档。历史报告仍是单机 SQLite 能力，不包含真实登录、用户隔离或团队空间。

## 自动化检查

- 前端：`npm run test`，241 项通过。
- 前端构建：`npm run build` 通过，仅保留 Vite chunk size 提醒。
- 后端报告历史测试：`.venv-mac/bin/python -m pytest tests/test_storage.py tests/test_report_storage_api.py`，10 项通过，1 个 Starlette/httpx 依赖弃用警告。
- Diff 空白检查：`git diff --check` 通过。

## 本机联调配置

- 后端：`OPENIMPACT_LLM_PROVIDER=rule .venv-mac/bin/python -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8010`
- 前端：`OPENIMPACT_API_TARGET=http://127.0.0.1:8010 npm run dev -- --host 127.0.0.1 --port 5175`
- 健康检查：`http://127.0.0.1:5175/api/v1/health` 返回 `{"status":"ok","version":"0.1.0"}`。

## 浏览器主流程

使用 `frontend/public/samples/signature_change.zip`：

1. 上传 ZIP 后 Inspect 返回 4 个 Python 文件、4 个函数，coverage 为 complete。
2. 选择 `utils.format_date`。
3. 新增参数名填写 `timezone`，参数类型为 `positional_or_keyword`。
4. Validate 返回 `valid=true`，页面展示 `format_date(date, timezone)`。
5. Analyze 返回 Direct=1、1-hop=1、2-hop=1、人工检查=0、未解析调用=0。
6. 报告证据展示 `report.py:5` 与 `return format_date(date)`。
7. “保存到历史”成功，页面显示已保存状态。
8. 历史报告页筛选 `format_date` 能读取到本机保存记录，详情仍显示同一份影响报告。

本机验收截图保存于临时文件 `/private/tmp/openimpact-history-verification.png`，不进入仓库提交。

## 当前边界

- 验收当时只保存报告 JSON 与摘要元数据；后续已新增项目/快照后端基础接口，见 [数据库说明](database.md)。
- 登录页仍是前端演示入口，没有真实认证、会话、用户表或权限。
- 该验收当时没有后台任务队列；后续已新增本地分析任务 API 基础，但前端主流程仍是同步请求，尚未接任务轮询和自动重试。
- 没有账号级历史中心、团队共享、项目空间或生产部署反向代理配置。
