# 入门样例 ZIP 测试指南

这个样例只有两个文件，适合第一次测试项目。

## 文件位置

上传这个文件：

```text
frontend/public/samples/beginner_greeting.zip
```

解压后可以看到：

```text
beginner_greeting/
  greeting.py
  main.py
```

代码的意思很简单：

- `greeting.py` 里的 `greet(name)` 负责生成问候语。
- `main.py` 里的 `show_welcome()` 调用 `greet("Alice")`。

## 测试步骤

在浏览器打开前端后，按下面填写。

1. 上传 `beginner_greeting.zip`。
2. 在函数列表选择 `greeting.greet`。
3. 选择“新增参数”。
4. 参数名填写 `punctuation`。
5. 参数类型选择 `positional_or_keyword`。
6. 点击“校验变更”。
7. 校验通过后，点击“开始分析”。

点击“开始分析”后，系统会自动把本次 ZIP 保存为本机快照，并创建一项分析任务。短暂显示 `queued` 或 `running` 属于正常反馈，完成后会自动显示报告。

## 在分析任务页复核

点击左侧的“分析任务”可以看到本机任务记录。对这次入门样例，正常情况下应看到：

- 目标是 `greeting.greet`。
- 变更显示为“新增必填参数 · punctuation”。
- 状态依次可能是“排队中”“分析中”，最终变为“已完成”。
- 已完成任务会显示报告编号；打开任务后可以直接阅读已保存的报告。

任务较多时，可在任务页按目标、参数名、任务 ID 搜索，也可以把状态切换为“失败”只查看需要处理的任务。失败任务保留诊断信息；确认配置或服务恢复后，可在详情中点击“重新执行”。重新执行会创建新任务，不会覆盖旧失败记录。

## 每一步应该看到什么

上传后：

- Python 文件数：`2`。
- 函数数量：`2`。
- 可选函数包括 `greeting.greet` 和 `main.show_welcome`。

校验后：

```text
修改前：greet(name)
修改后：greet(name, punctuation)
```

分析报告中：

- 直接影响：`1`。
- 1-hop 间接：`0`。
- 2-hop 间接：`0`。
- 直接影响的位置应在 `main.py`，并且代码证据应接近：

```python
return greet("Alice")
```

## 为什么会有这个结果

原来的 `greet` 只需要一个参数 `name`。

修改后，`greet` 还需要一个新的必填参数 `punctuation`。但 `main.py` 还是只传入 `"Alice"`，所以系统应报告这里需要检查或修改。

## 通过标准

只要报告明确指出 `main.py` 中的 `greet("Alice")` 少传了 `punctuation`，这个入门样例就算测试通过。

