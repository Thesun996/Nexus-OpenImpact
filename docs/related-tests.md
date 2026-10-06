# 相关测试定位与检查理由

本轮针对函数签名变更，回答“哪些真实测试值得先检查，依据在哪”。复用原 Direct / Indirect 结果，不改变兼容性判断、调用图或传播算法。没有执行、导入、收集上传项目的测试，不由 LLM 猜测测试名称或决定关联。

## 使用

上传包含测试源码的原始 ZIP，完成 Inspect → Validate → Analyze，在函数报告下方查看“相关测试与检查理由”。点击调用位置旁的“打开完整源码”可打开同一 ZIP 中的文件与行号。切换项目或变更后沿用既有报告失效规则；无独立候选缓存。

每个候选给出模块级测试函数的定义位置、检查理由、一条或多条已有代表性路径，以及每条路径上的真实调用源码、整个文件的 SHA-256 和原始 Direct 引用。多个 Direct 来源按测试函数去重，仍保留每个来源的路径。候选优先展示含直接不兼容调用的测试，其次是较近的上游测试；这只是检查顺序，不是风险评分。

## 可选报告字段

函数 JSON 报告 `schema_version=1` 保持，现有字段不改。只有扫描到 `test_*.py` 或 `*_test.py` 时追加 `related_tests`；因此旧的无测试 Demo 与冻结 JSON 样例保持逐字段相同。原 Inspect / Validate / Analyze 路径、multipart 请求和 ZIP 指纹规则不变。Module / Symbol 报告暂不追加此字段。

`related_tests` 包含：

| 字段 | 含义 |
| --- | --- |
| status | available：定位流程可用，候选可为空；unavailable：定位失败，保留原影响报告 |
| scope / max_upstream_hops | pytest_named_module_functions / 2：只使用已有范围内的路径 |
| test_file_count / indexed_test_count | 命名匹配的源码文件数 / 进入原 Symbol Index 的模块级测试函数数，均不代表实际 pytest 收集数量 |
| candidates | 唯一测试函数列表；无关联候选时为 [] |
| limitations / diagnostics | 中文范围提示和安全诊断；失败时不泄露内部异常 |

每个 candidate 包含 `test_symbol_id,file,line,node_id,relationship,reason,paths`。`line` 指向函数定义；`node_id` 是 `相对文件::函数名` 形式的候选运行定位，未验证真实收集配置。`relationship` 为 direct / upstream；两类都属于待检查的测试候选，不保证运行时失败。

每条 path 包含 `direct_evidence_reference,impact_type,status,call_sites`；每个 call_site 包含原图中的 `caller_symbol_id,callee_symbol_id,file,line,column` 及 `source_snippet,source_hash,status,diagnostics`。路径从候选测试到原始 Direct 调用，最多三条调用边。列号沿用 AST 的零起始 UTF-8 字节列号。源码缺失、位置或表达式不匹配时对应片段为 null、status=unavailable，不借用旧片段。整个定位层失败时只返回 unavailable 与安全诊断，旧影响结果不变。

## 范围与可靠性

命名采用 [pytest 官方默认发现规则](https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery) 的模块级函数子集：文件名为 `test_*.py` / `*_test.py`，函数名以 `test` 开头。这只是静态候选筛选；项目可能改变配置、忽略函数、使用插件或跳过标记。

- 只从确定 Direct 来源及原两层上游结果生成候选；manual_review、unresolved、pre-existing 和 compatibility_improved 不作为来源。名字相似、目录相同不构成关联依据。
- 不扩大类方法、fixture、动态调用或重导出解析；不处理自定义测试框架与运行参数，不执行配置文件、conftest.py 或装饰器。源码中的条件和测试标记可能改变执行路径。
- 原图之外、更深的测试和业务断言不会被穷尽；上游关联不保证测试执行到该位置。partial 下定位也不完整。
- 原始报告不含测试字段、空候选或所有建议测试通过，都不能证明项目无需测试或改动安全。当前功能没有独立的测试推荐准确率或召回率评测。
- 默认 DeepSeek Prompt 不接收这些候选作为新的事实；报告追问仍只引用原 Evidence。以后如加入模型解释，应先补齐候选引用契约，不允许模型编造测试。

## 验证记录

日期：2026-10-06（Asia/Shanghai）。

- 完整后端：956 passed、2 skipped、7 subtests passed；两个跳过项均因本机没有创建符号链接的权限。保留既有 Starlette TestClient 弃用提示。
- 前端：212 passed；生产构建成功；git diff --check 通过。
- 用旧 main 与当前实现分析同一份源码字节，15 个既有 Demo 报告逐字段相同，包括 Evidence 哈希。使用同一快照避免 Windows 不同工作树的换行字节影响比较；未改源码或哈希规则。
- 真实 rule HTTP 与浏览器：标准 format_date + timezone 为 1/1/1 complete，page.page + zone 为 0/0/0 complete；未保留旧证据或测试候选。
- 上传另一个含真实测试源码的项目：影响为 2/2/1 complete，候选为直接测试、1 层上游测试和 2 层上游测试共 3 个。测试源码本身也进入原有调用图，因此不应强行沿用无测试 Demo 的 1/1/1。
- 同一测试项目加入语法错误文件后为 partial，保留 3 个已确认候选并明确提示范围不完整；改为无人调用的函数后为 0/0/0、空候选，仍保留 partial 提示。
- 浏览器核对源码跳转、Esc 关闭与焦点恢复、手机 390px 无页面横向溢出、源码普通文本阅读，控制台无错误。源码缺失/变化、定位层异常、保守调用边界和清理通过自动化专项测试；未制造浏览器中的源码丢失。

验收仅使用 rule，不调用外部模型，不执行上传测试，不声称独立准确率。Windows 系统级 reduced-motion 与独立 Benchmark 尾项继续 pending。
