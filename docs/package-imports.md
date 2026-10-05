# 普通 Python 包与显式源码根目录

本轮补齐真实项目静态包路径，不扩大类方法、运行时导入或模块/变量变更范围。兼容性判断仍使用真实 Before/After 签名，上游传播复用原调用图算法。

## 操作

网页上传 ZIP 后，普通项目保留源码根目录 `.`。对于 `src/package_name/` 布局填写 `src`，再读取项目。目录应为 Python 包的父目录，相对于 ZIP 外包装剥离后的项目。

三个阶段重复提交同一原始 ZIP、原指纹及根目录。更改目录取消旧请求并清除旧函数选择、校验和报告；更换 ZIP 将目录恢复为 `.`。迟到响应不能覆盖新状态。同一 ZIP 可选择不同布局，SHA-256 仍相同；前端额外核对布局及校验快照。

CLI 可选 `--analysis-root src`；省略保留旧项目根映射。示例见 [package_signature_change](../examples/package_signature_change/README.md)。CLI 使用完整结构化 ChangeSpec，HTTP 使用既有简化配置，不改变变更字段。

## 能力矩阵

| 情况 | 当前策略 |
| --- | --- |
| 项目根普通模块的绝对 import / from import / alias | 保留 |
| src 包的明确绝对函数或子模块 import | 显式选择 src 后绑定；alias 可用于两段属性调用 |
| `from .utils import f as fd` | 完整普通包层级时绑定 |
| `from . import utils as u` | 明确唯一子模块时绑定 |
| `from ..utils import f` | 逐层核对 __init__.py，不允许越界 |
| 同名函数、两个根中同名模块 | 按完整模块隔离；冲突则 unresolved |
| tests 位于 src 之外 | 保留项目相对模块标识与文件位置，可明确导入 src 包 |
| namespace 相对导入 | unresolved，不推断运行环境 |
| 包初始化重导出、复杂副作用、搜索路径动态写入 | 不追踪重导出；已识别搜索路径重绑定时拒绝绑定 |
| 类、嵌套函数、lambda 内调用 | 不生成函数调用边；返回排除作用域诊断、partial |
| 外部依赖、动态导入、函数对象转发、复杂属性链 | 保留 unresolved / conservative 边界 |
| Module / Symbol 变更目标 | 仍仅支持项目根普通文件，src 内嵌套文件不可选 |

绝对导入静态映射假定用户声明的导入环境；不模拟安装器、sys.path、PYTHONPATH、namespace 搜索、所有初始化副作用或第三方包遮蔽。目录拒绝逃逸、绝对路径、链接及特殊文件。静态调用关系不保证运行时一定执行。

## API 兼容性

三个业务接口追加可选单一 multipart 文本字段 `analysis_root`，缺省 `.`，不进入 change JSON。schema_version、原 payload、旧字段和 fingerprint 规则保持。无效目录 HTTP 422 `invalid_analysis_root`；重复字段 400。安全 ZIP 检查、线程池、请求隔离和清理保持。

非默认布局返回追加元数据；默认布局省略，保留旧响应形状：

```json
{"analysis_layout":{"analysis_root":"src","mode":"explicit","import_roots":[".","src"]}}
```

`source_root` 仍表示剥离的 ZIP 外包装，不能当作源码根。文件路径及哈希基于整个项目实际原始文件。Evidence/Explanation 顺序和匹配规则不变。

有未支持调用作用域时，Inspect 和函数 Report 追加 `diagnostics.unsupported_scopes[]`：项目相对 file、line、column、scope、name、excluded_call_count、中文 message。这些区域不计入 Direct 或 manual_review 调用数；它们是范围缺口，coverage=partial。无记录时省略该字段。排除调用计数不等于目标的实际漏报数量。

## 真实项目复验

固定 python-dotenv v1.1.1、commit `16e660d384b942b11879b44500afbbe021650448`，只读取 19 个 Python 文件。

```sh
python scripts/audit_python_dotenv.py .local/real-project-audit/python-dotenv-v1.1.1 --analysis-root src --output .local/package-audit
```

脚本核对 pinned 源码、真实行号与 SHA-256，运行独立本地 HTTP rule 服务，结果仅写忽略目录。不执行 upstream setup.py、测试或导入模块。此为功能观测，不能替代独立人工 Ground Truth 或准确率评价。

| 目标；拟新增仅关键字必填 strict | Direct / 1层 / 2层 | Coverage |
| --- | --- | --- |
| dotenv.parser.parse_key | 1 / 1 / 3 | partial |
| dotenv.parser.parse_stream | 3 / 2 / 0 | partial |
| dotenv.main.find_dotenv | 2 / 3 / 0 | partial |
| dotenv.main.load_dotenv | 0 / 0 / 0 | partial，公开重导出尚未解析 |

parse_stream 的确定调用在 main.py:185、main.py:218、tests/test_parser.py:169。DotEnv.parse 方法调用仍明确排除。全部证据哈希正确；HTTP 与本地一致；10 个临时目录清理；错误指纹 409；嵌套 Module 操作 422。
