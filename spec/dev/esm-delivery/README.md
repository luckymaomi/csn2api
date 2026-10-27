# 构建交付说明

本仓库的生产构建由 scripts/build.mts 负责，输出首页、API 文档、当前登记的 HTTP 工具、公共主题和独立 ZIP。构建不依赖旧仓库的页面或工具清单。

隔离构建使用 `CSN2API_DIST_ROOT` 和 `csn2api-build-*` 临时目录；独立工具包内的清单为 `csn2api-tool.json`，格式标识为 `csn2api-standalone-tool`。

构建同时扫描可发布的 spec Markdown，并复用 API catalog 的同源 Markdown 生成器，输出 `dist/downloads/csn2api-development-documentation.md`。首页按下载当天日期保存为 `csn2api开发者文档-YYYY-MM-DD.md`；文档与 APP 在 CI 验证后一起发布。生成契约见[文档维护与合并下载](../../system/documentation.md)。
