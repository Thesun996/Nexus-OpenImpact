# GitHub Desktop 提交清单

本文用于把当前本地开发成果提交到远端仓库。它不是业务功能说明。

## 当前建议

- 如果组长明确让你直接更新 `main`，可以在 `main` 上提交并 Push。
- 如果没有明确授权，建议先建分支再发 Pull Request；这能让组长审核，也避免把 `main` 弄坏。
- 当前仓库已经忽略 `.openimpact/`、`.venv/`、`frontend/node_modules/`、`frontend/dist/`、`.DS_Store`、`.idea/` 等本地文件，这些不应该提交。

## GitHub Desktop 操作

1. 确认左上角仓库是 `Nexus-OpenImpact`。
2. 确认 Current Branch 是你要提交的分支。
   - 直接交主分支：选择 `main`。
   - 走审核流程：新建类似 `frontend-report-history` 的分支。
3. 在 Changes 页面只保留项目代码、测试、文档文件。
4. Summary 建议填写：`feat: add local report history persistence`。
5. Description 可写：`Add SQLite report persistence, history UI, and report deletion.`。
6. 点击 Commit。
7. 点击 Push origin。若是新分支，按钮可能显示 Publish branch。
8. 如果走 Pull Request，Push 后在 GitHub Desktop 或网页上创建 PR，目标分支选 `main`。

## 提交前确认

本轮应提交的文件类型：

- `src/openimpact/...` 后端代码。
- `frontend/src/...` 前端代码。
- `frontend/styles.css` 前端样式。
- `tests/...` 测试。
- `docs/...` 文档。
- `.gitignore`。

不应提交的文件类型：

- `.openimpact/` 本地 SQLite 数据库。
- `.venv/`、`.venv-mac/` 虚拟环境。
- `frontend/node_modules/`。
- `frontend/dist/`。
- `.DS_Store`。
- `.idea/`。
- 临时截图、录屏、浏览器缓存。

## 上传后的判断

Push 之后，GitHub 网页上的对应分支才会更新。本地文件改了但没有 Commit + Push，GitHub 不会自动变。

如果直接 Push 到 `main`，远端 `main` 会更新；如果 Push 到其他分支，需要合并 PR 后 `main` 才会更新。
