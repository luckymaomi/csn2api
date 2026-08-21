# 工具首页用户手册

首页品牌为“csn2api”，目录直接展示当前已登记工具。每个工具卡片显示用途、状态、打开入口和下载图标，顶部保留 API 文档、主题切换和 GitHub。

点击 API 文档或任一 HTTP 工具会在新标签页打开对应页面。工具页可按各自用户手册启动本地 Python APP；页面不会自动替用户填写 Cookie，也不会执行未授权的生产操作。

点击工具卡片的下载图标会下载该工具自己的 ZIP。解压后打开根目录 index.html 即可使用；Python 文件和 requirements.txt 会一并保留。

维护者只需编辑 src/tool/tools-data.ts 管理首页目录；站点门禁配置位于 src/site-visibility.ts 的 homepage.patternGate。SOC 随机置位 skill 不属于首页工具。
