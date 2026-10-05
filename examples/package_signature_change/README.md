# 普通包与相对导入 Demo

在仓库根目录运行：

```sh
python -m openimpact analyze examples/package_signature_change --analysis-root src --change examples/package_signature_change/change.json --format json
```

静态路径：`trace_demo.page.page → trace_demo.dashboard.dashboard → trace_demo.report.report → trace_demo.utils.format_date`。
拟新增仅关键字必填参数 timezone；预期直接影响、1 层、2 层各 1，当前支持范围内覆盖完整。不执行或修改这些 Python 文件。

Web：将整个 `package_signature_change` 文件夹压缩，保留外包装目录。上传后填写源码根目录 `src`，选择 `trace_demo.utils.format_date`，新增仅关键字必填参数 timezone，再校验、分析。
ZIP 入口按既有规则剥离一层非 Python 包的外包装。根目录相对于剥离后的项目；如只压缩 src 内部内容，通常保留默认 `.`。
