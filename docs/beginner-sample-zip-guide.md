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

