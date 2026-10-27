# 工具首页开发规格

工具首页直接展示 `src/tool/tools-data.ts` 当前登记的 HTTP 工具入口，不提供搜索或分类切换。

仓库和首页品牌为 `csn2api`。工具名称与目标业务系统名称独立维护；飞行门户 IEB 等应用名称不随仓库品牌改名。

src/tool/tools-data.ts 是首页工具内容和独立应用导出的唯一清单，保存名称、说明、入口、发布状态和可选的 homepageState。构建从该清单生成静态详情页、独立 ZIP 和 `runtime-tools.json`；系统归属复用 `scripts/protocol-cores.json`，新增工具不维护第二份局域网名单或专属详情页脚本。

首页保留顶部导航和图案门禁结构，门禁由 src/site-visibility.ts 控制且默认关闭。顶栏提供 API 文档、下载开发文档、白天/暗夜模式切换和 GitHub。首次访问默认白天模式，选择通过共享主题设置保存在浏览器本地。

页面使用全站共享主题：颜色、边框、阴影、状态和主题值由 public/theme.css 统一提供；首页 CSS 只维护首页布局和组件特判。每项显示工具名称、用途摘要、状态小字、只读开关和下载图标。

homepageState 只有 enabled、beta、cooling 三种状态。未填写或为 enabled 时显示“已启用”；beta 显示“Beta 测试”；cooling 显示“冷却中”。该状态只作用于首页入口，工具固定 URL 和构建产物保持可访问。

生产构建在 dist/exports/ 中按工具 entry 逐项生成 ZIP，导出数量始终等于当前工具清单数量。每个工具的详情入口提供对应 ZIP 下载；每个 ZIP 根目录包含 index.html、独立应用脚本、离线运行时、主题和页面实际需要的库、Python 文件及依赖说明，不包含其他工具、缓存或仓库开发文件。

工具登记同时进入统一交付合同。合同从当前工具清单动态检查详情入口、ZIP、`csn2api-tool.json` 和包内页面资源闭包；Python 工作台还必须在包内加载 Bootstrap、公共主题和页面专属样式。新增工具不维护单独测试名单。

静态模式由 `start_index.py` 提供，卡片进入构建生成的说明与下载页。局域网模式由 `start_all.py` 注入运行标记，卡片直接进入 `/apps/<entry>/` 的真实工作台，API 文档进入 `/api-docs/`；两种模式消费同一首页渲染和工具清单。

“下载开发文档”在两种模式均指向同一构建静态文件 `downloads/csn2api-development-documentation.md`，保存名为 `csn2api开发者文档-YYYY-MM-DD.md`。正文合并全部可发布 spec Markdown 与同源 catalog 生成的 API 文档；日期在页面初始化和点击时取浏览器本地日历日。构建、标准测试和 CI 重新生成并检查，详见[文档维护与合并下载](../../system/documentation.md)。
