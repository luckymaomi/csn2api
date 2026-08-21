# 构建交付说明

本仓库的生产构建由 scripts/build.mts 负责，输出首页、API 文档、当前登记的 HTTP 工具、公共主题和独立 ZIP。构建不依赖旧仓库的页面或工具清单。

隔离构建使用 `CSN2API_DIST_ROOT` 和 `csn2api-build-*` 临时目录；独立工具包内的清单为 `csn2api-tool.json`，格式标识为 `csn2api-standalone-tool`。
