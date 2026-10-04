# Tracework 字体

本目录仅包含界面和代码所用的五个 IBM Plex WOFF2 文件，随前端构建本地加载，无运行时第三方字体请求。

- 来源：[IBM/plex](https://github.com/IBM/plex)，`packages/plex-sans/fonts/complete/woff2/` 与 `packages/plex-mono/fonts/complete/woff2/`。
- 字重：IBM Plex Sans 400 / 500 / 600；IBM Plex Mono 400 / 500。
- 许可：随附原项目 [LICENSE.txt](LICENSE.txt)，SIL Open Font License 1.1；相同许可通过 [public/licenses/IBM-Plex.txt](../../../public/licenses/IBM-Plex.txt) 一并进入构建产物。
- 中文：使用 `tokens.css` 中的思源黑体及系统黑体回退链，未打包中文字体；具体显示随本机安装字体变化。

字体加载失败时仍使用系统回退。以后更新字体须同时保留许可证，不能用仅包含 Demo 汉字的子集替代通用中文回退。
