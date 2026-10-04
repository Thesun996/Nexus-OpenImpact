# Phase 6.6：Benchmark 接入核查与缺口清单

核查日期：2026-10-04。分析基线：`integration/multi-change-web@1cd8480a7e37049956060556b912abe963f89486`。

**结论：当前可见仓库没有成员 B 的可核验独立评测交付。本轮完成评测契约、交付缺口及实际回归记录，独立 Benchmark 评测待真实成果。** 未创建人工标签、未运行独立 Evaluation Runner，所有 Benchmark 指标为未测量。

评测要求见 [evaluation-contract.md](evaluation-contract.md)；本次机器可读状态见 [phase6.6-evaluation-readiness.json](phase6.6-evaluation-readiness.json)。

## 1. 成员 B 成果审计

在基线工作区干净的前提下完成 `git fetch origin --prune`；当前远程 main 仍为 `3a5a582`，未切换、合并或改写任何分支。

审计所有可见本地/远程 refs 的文件树、内容及 Git 历史：

| 分支或引用 | 当前 commit |
| --- | --- |
| main / origin/main | 3a5a582 |
| feature/change-types | 327248e |
| feature/ui-redesign | f34d243 |
| integration/frontend-react / origin/integration/frontend-react | 9ab08fc |
| integration/multi-change-web | 1cd8480 |
| origin/frontend | 9c81e07 |

检索覆盖 benchmark、evaluation、ground_truth、metrics、precision、recall、人工标注/评测等路径和文字。未找到 Benchmark 样本集、人工 Ground Truth、Runner、指标计算脚本或实际评测结果。该结论仅限本次可见仓库，不能据此断言成员个人尚未完成，或没有在其他位置交付。

现有相关资产的用途与来源：

| 资产 | 来源与判断 |
| --- | --- |
| `examples/signature_change/` | 975dc03 加入的生产 Demo |
| `examples/parameter_removal/`、两个 rename Demo | 101d838 加入的功能示例 |
| 两个 make-required Demo | 327248e 加入的功能示例 |
| `tests/analysis/` 等 | Core、CLI、API 和边界回归测试 |
| `frontend/tests/fixtures/change-specs.json` | 1cd8480 中六个 CLI Demo 的真实结果，用于前端契约回归；不能计为独立人工答案 |
| `scripts/deepseek_live_check.py` | 模型联调辅助，与独立分析评测无关，本轮未调用 |

`PROJECT.md` 的“测试与评测”仅描述 Golden Set 和指标计划；`docs/frontend-handoff.md` 的 Evaluation 行仍为历史待交付记录。不能从这些计划推断评测已实施。

## 2. 成员 B 交付缺口

| 待交付项 | 最低要求 | 当前状态 |
| --- | --- | --- |
| 来源定位 | Git branch/commit 或本地交付目录；数据集/脚本版本与复现说明 | 待提供 |
| 独立样本 | 24–30 个案例；建议 28 个、每 Change Type 7 个；源码与来源/许可 | 未找到 |
| Change 文件 | 与当前四类 Core 契约一致的完整结构化 before/after/operation | 未找到独立评测输入 |
| 人工 Ground Truth | 调用点、兼容性分类、有限传播路径、manual/unresolved、coverage、人工依据 | 未找到 |
| 人工复核记录 | 实际标注者/复核者、冻结版本、争议处理，独立于 analyzer 输出 | 未找到 |
| Runner / 指标脚本 | 使用现有入口，精确位置匹配、空分母 null、分类隔离、保留失败和耗时 | 未找到 |
| 评测结果 | 原始逐案例差异、FP/FN、错误路径、分类型指标、环境和计数单位 | 未生成 |

已向负责人询问实际交付分支/目录。本轮继续完成不依赖标签的工作，不代造人工 Ground Truth。数据到位后先核查格式、哈希和标注来源，再复用成员 B 的实现；如确无 Runner，再按契约补充薄编排层，不改 Core。

## 3. 样本分布与指标状态

| Change Type | 建议案例数 | 可见独立交付 | 已核验人工标签 | 已完成独立评测 |
| --- | ---: | ---: | ---: | ---: |
| add_required_parameter | 7 | 0 | 0 | 0 |
| remove_parameter | 7 | 0 | 0 | 0 |
| rename_parameter | 7 | 0 | 0 | 0 |
| make_parameter_required | 7 | 0 | 0 | 0 |
| 总计 | 28（计划） | 0 | 0 | 0 |

实际覆盖情况均待交付，不能用生产测试的场景分布代替独立样本覆盖。

| 必需结果 | 当前结论 |
| --- | --- |
| Direct Precision / Recall / F1 | 未测量，JSON 为 null |
| Indirect Symbol 与路径正确性/完整性 | 未测量，JSON 为 null |
| Coverage 分类正确性 | 未测量，JSON 为 null |
| 分 Change Type 指标 | 未测量，JSON 为 null |
| manual_review / unresolved 与其他边界分布 | 无独立样本，尚无分布数据 |
| Benchmark 平均 Core 分析耗时 | 未测量，JSON 为 null |
| FP / FN / 错误传播路径 | 尚未评测，列表为 null；不使用空列表宣称零缺陷 |

尚无可据独立数据确认的新 Core 缺陷。597 项回归通过和六个 Demo 正常仅支持已有行为没有回归，不证明 Precision/Recall 为 100%。

## 4. 本轮实际回归

使用集成工作树的独立 Python 环境：Python 3.12.0、pytest 9.1.1；已确认 editable import 指向本工作树 `src/openimpact/`。执行进程清除 `PYTHONPATH`、模型 Key 和代理，`OPENIMPACT_LLM_PROVIDER=rule`，没有真实模型调用。

```text
python -m pytest
python -m openimpact analyze examples/<demo> --change examples/<demo>/change.json --format json
```

完整 pytest：**597 passed、1 skipped、1 warning，39.14 秒，退出码 0**。警告为现有 Starlette TestClient/httpx 弃用提示，未借本轮调整依赖。

六个实际 CLI JSON 结果：

| Demo | Change Type | Direct / 1-hop / 2-hop | Coverage | CLI 单次耗时 ms |
| --- | --- | --- | --- | ---: |
| signature_change | add_required_parameter | 1 / 1 / 1 | complete | 261.04 |
| parameter_removal | remove_parameter | 1 / 1 / 1 | complete | 271.41 |
| parameter_rename_keyword | rename_parameter | 1 / 1 / 1 | complete | 256.78 |
| parameter_rename_positional | rename_parameter | 0 / 0 / 0 | complete | 261.25 |
| parameter_required_missing | make_parameter_required | 1 / 1 / 1 | complete | 265.36 |
| parameter_required_explicit | make_parameter_required | 0 / 0 / 0 | complete | 268.88 |

六项均校验有效、退出码 0，manual_review / pre-existing / unresolved 为 0；输入源码快照前后相同。平均单次 CLI 观察为 264.12 ms，**包含 Python 启动、Report/Evidence/Rule 解释，不能作为 Benchmark 的平均 Core 分析耗时**。

原始日志、六份未改写的 CLI JSON 和回归摘要保留于忽略目录 `.local/phase6.6/`，不纳入提交，也不复制为 Ground Truth。上述摘要仅为可复核的回归记录。

## 5. 评测接入注意事项与能力边界

本次源码核查确认：

- Direct 需按相对文件、行列、caller、target 精确匹配，不能仅比较计数；同一行多个调用必须区分 column。
- 公开 JSON 没有全部 compatible/improved assessment；Runner 可读 `AnalysisRun.direct.assessments`，无需新增 API 字段。
- Indirect 按上游 Symbol 去重，保留每个 Direct seed 的最短代表路径；1-hop/2-hop 的 graph_distance 为 2/3，不能误判为 1/2。
- manual、既有问题、兼容性改善和 unresolved 不作为确定传播 seed；展开实参仍保守输出 manual_review。
- 外部库或动态目标未能解析时，项目可能标为 partial。partial 的零条结果不能表述为全项目无影响。
- 源文件 SHA-256 使用整个文件原始字节；CRLF/LF 会改变它。源码 hash、ZIP fingerprint 和 Ground Truth hash 分别保存。
- 仅支持限定模块级函数及四种签名变化；函数体行为、动态派发、复杂 import、reflection 和项目外调用者仍不在完整分析范围。

这些属于现有契约及已知能力边界，本轮未扩大支持范围或修改分析算法。

## 6. Phase 6.7 前置条件

生产回归基线通过。**Phase 6.6 的独立定量 Evaluation 尚未完成，当前不满足包含 Benchmark 验收的 Phase 6.7 前置条件。**

待负责人协调成员 B 提供真实成果后：

1. 冻结数据集与人工标签版本，确认每类实际案例数和支持边界。
2. 接入/运行 Runner，输出整体及分类型指标、FP/FN、错误路径、manual/unresolved 和耗时。
3. 人工复核全部差异，保留可复现 Case；生产代码继续冻结，不以改答案或改 Core 隐去问题。
4. 由负责人结合实际结果确定验收阈值与已知缺陷是否阻塞；本轮不自行设定高分目标。

本轮仅新增评测文档和机器可读接入状态；Core、API、React、依赖及原六个 Demo 未修改。未 commit、push 或 merge。
