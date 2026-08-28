# 工具首页用户手册

首页品牌为“csn2api”，目录直接展示当前已登记工具。每个工具卡片显示用途、状态、打开入口和下载图标，顶部保留 API 文档、主题切换和 GitHub。

通过 `start_index.py` 打开时，工具卡片进入说明和独立 ZIP 下载页。通过 `start_all.py` 打开时，工具卡片直接进入真实工作台，API 文档进入统一网关下的调试页。

点击工具卡片的下载图标会下载该工具自己的 ZIP。解压后打开根目录 index.html 即可使用；Python 文件和 requirements.txt 会一并保留。

局域网首页可以多人查看。第一位进入任一工作台的 IP 取得全部工具使用权，同一 IP 可以跨工具操作；其他 IP 进入工作台时会看到当前使用者 IP。状态条提供 Cookie 文件导入、导出和“结束使用”；任务运行时不能结束，默认无活动 3 分钟且无任务运行后才允许下一位接管。

维护者只需编辑 src/tool/tools-data.ts 管理首页目录；站点门禁配置位于 src/site-visibility.ts 的 homepage.patternGate。Skill 不直接生成首页卡片；SOC 随机置位批量助手与其他工具一样通过 tools-data.ts 登记，并使用独立的 SOC 会话和接口实现。
