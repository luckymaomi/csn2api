# CAAC 飞行员信息导出开发规格

## 产品边界

`http-caac-pilot-export-helper` 是独立本地 Python APP，只读访问 `fsop.caac.gov.cn` 人员管理接口。凭据只存在当前 Python 进程内存，结果写入 APP 本地 `results/<runId>/`。CAAC 会话与 IEB、OA、SOC 相互独立。

## 接口契约

- `POST /yzzzm/rygl/queryPilotByParamForPage?ajaxPrefilter=<timestamp>`：表单包含姓名、档案号和其他筛选项，以及 `page`、`rows`、`sort=archiveNo`、`order=asc`；响应为 `{total, rows}`。
- `POST /yzzzm/rygl/queryPilotDetails`：表单为 `pilotId`；响应顶层对象的 `pilotId` 与请求一致。
- 分页按响应 `total`、实际行数和唯一 `pilotId` 动态收敛。空页、重复 ID、批次内 total 变化和缺少 ID 属于响应契约错误。
- 详情响应包含基础标量、文件 URL、递归资质树和记录数组；字段按实际响应动态并集。已确认中文字段字典由 `field_mappings.py` 维护，未映射字段保留原始键名。

## 抓取模式

### 全量抓取

从无筛选列表第 1 页开始动态分页，取得当前会话范围内的全部列表记录，再按 `pilotId` 获取详情。

### 名单抓取

Excel 活动 Sheet 使用“姓名”必填列和“档案号”选填列。每个有效输入按姓名请求筛选列表，姓名必须精确一致；填写档案号时进一步按规范化档案号精确筛选。唯一候选的 `pilotId` 用于详情请求；无候选或多候选记录为该行失败。

缺姓名和重复输入记录为失败且不发起人员请求。名单结构错误阻止运行。模板由 `GET /api/template` 动态生成，不保存二进制模板文件。

## 执行与保存

详情严格串行，每个最终归属的 `pilotId` 请求一次。普通请求、匹配和解析异常记录失败并继续后续人员；登录失效停止后续请求；用户停止后等待当前请求结束并停止派发；不自动重试。

Excel 只有“飞行员信息”一个 Sheet。每完成一人，`ResultExporter` 将列表和详情转换为一行中文业务数据，并通过临时文件替换原子保存检查点。运行中首次出现的新字段立即加入列集合。

列顺序始终为“序号、动态业务字段、来源行、输入姓名、输入档案号、抓取状态、失败原因”。后续人员首次返回的新业务字段插入末尾五个追踪字段之前，已经保存的行随表头同步移动。

列表和详情同义字段合并，详情值优先。记录数组转换为单元格内逐条换行文本，资质树保留层级缩进；时间戳按本地业务日期转换。“执照备注”由语言等级、有效期和接口备注动态组合，同时保留各来源列。

## 本地 API

- `GET /api/status`：返回会话、保活、模式、检查、进度、下载状态和结果表版本。
- `GET /api/results?offset=<n>&limit=<n>`：分页返回当前 Excel 同源列和行，`limit` 最大 200。
- `GET /api/template`：下载人员名单模板。
- `GET /api/download`：下载当前检查点或最终 Excel。
- `POST /api/session/verify`：验证凭据并启动列表接口保活。
- `POST /api/check-data`：检查名单；全量模式返回当前接口人数摘要。
- `POST /api/run`：按 `mode=all|selected` 启动批次。
- `POST /api/stop`：停止派发后续请求。

## 页面行为

页面加载 Bootstrap、公共主题和页面布局 CSS。登录区提供凭据验证、当前页凭据复制、当前登录人占位和圆形保活倒计时。抓取区提供全量/名单分段控件、模板下载、Excel 上传和名单检查。状态区显示进度及总数、完成、成功、失败。

人员结果表消费 `/api/results`，动态展示与 Excel 相同的列；表头和首列固定，内容支持纵向和横向滚动及分页。单元格内容超过 100 个字符时，页面显示前 100 个字符和省略号，接口结果与 Excel 保留完整值。结果表和活动日志默认跟随最新内容，用户滚动离开底部后保持其当前位置。

## 工作台公共合同

仓库从 `public/tool/app/http-*-helper/web/index.html` 动态发现 Python HTTP 工作台。每个工作台加载 `theme.js`、Bootstrap、`theme.css` 和 `styles.css`，使用标准身份、当前页凭据、保活 DOM、日志滚动区及结果滚动区命名。

保活前端模块以 `public/tool/app/_shared/session_keepalive.mjs` 为标准来源。源码中的 APP 本地副本通过合同测试保持一致，构建阶段将标准模块复制到每个独立分发包。系统特判只保留在各 APP 的保活请求和会话判断中。

## 当前登录人

当前已确认 CAAC 入口页和业务 JSON 没有稳定可归属的当前登录人字段。已验证会话在页面显示“未识别”。
