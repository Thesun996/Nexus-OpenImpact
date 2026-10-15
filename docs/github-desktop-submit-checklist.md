# GitHub Desktop 提交清单

本文用于把当前本地开发成果提交到远端仓库。它不是业务功能说明。

## 当前建议

- 按项目负责人的当前决定，使用 `feature/refine-project` 分支提交并 Push，暂不合并 `main`。
- 后续由项目负责人审核并决定是否发起 Pull Request、合并主分支。
- 当前仓库已经忽略 `.openimpact/`、`.venv/`、`frontend/node_modules/`、`frontend/dist/`、`.DS_Store`、`.idea/` 等本地文件，这些不应该提交。

## GitHub Desktop 操作

1. 确认左上角仓库是 `Nexus-OpenImpact`。
2. 确认 Current Branch 是 `feature/refine-project`。
3. 在 Changes 页面只保留项目代码、测试、文档文件。
4. Summary 填写：`feat: 支持项目库快照直接分析`。
5. Description 填写：`接通项目保存、刷新后打开快照、变更校验、影响分析、源码查看和报告保存；增加快照完整性校验、请求切换保护及回归测试，更新接口和验收文档。`。
6. 点击 Commit。
7. 点击 Push origin。若是新分支，按钮可能显示 Publish branch。
8. 如果走 Pull Request，Push 后在 GitHub Desktop 或网页上创建 PR，目标分支选 `main`。

## 提交前确认

本轮应提交的文件类型：

- `src/openimpact/...` 后端代码。
- `frontend/src/...` 前端代码。
- `frontend/styles.css` 前端样式。
- `tests/...` 测试。
- `frontend/tests/...` 前端测试。
- `docs/...` 文档。
- `README.md`，以及确有改动的 `.gitignore`。

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
