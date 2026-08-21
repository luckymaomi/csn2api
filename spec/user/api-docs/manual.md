# API 文档用户手册

从工具首页顶栏打开“API 文档”。该入口不占用工具卡片；页面左侧按系统分组当前 catalog 中的接口，Cookie 管理统一展示 IEB 与 OA 的登录网址、建议抓取请求和获取步骤。

## Cookie

Cookie 管理右侧把 IEB 与 OA 两个完整区域从上到下排列，两套凭据互不共享。后续新增系统会继续向下追加；右侧区域可以独立滚动。

IEB：打开 `https://ieb.csair.com/index/index` 并登录，在 F12 Network 中选择任意 `ieb.csair.com` 已登录请求，右键 Copy as cURL 后粘贴验证。`JSESSIONID` 与 `iebJSid` 为 HttpOnly，普通 `document.cookie` 无法完整读取。

OA：打开 `https://work.csair.com/oaw/work/my-dealt-with/schedule-list?sourceType=wait` 并登录，确认待办列表已显示；在 F12 Network 筛选 `query/waiting`，选择 `POST https://work.csair.com/oai/work/box/query/waiting` 并 Copy as cURL。优先粘贴完整 cURL，使本地执行器同时取得 Cookie、User-Agent 和待办 JSON 模板。

验证成功后对应系统区域显示可复制的规范化 Cookie Header。刷新或重新打开会清除两套 Session；每个区域的“清除”只清该系统。页面不使用浏览器持久化存储保存凭据。

## 调试请求

选择接口，填写技术上必要的员工号、日期或锁班参数，点击发送请求。页面同时显示 HTTP 方法、最终 URL、状态码、响应 Headers、用户友好的表格/摘要以及原始 JSON 或 HTML。锁班接口仍是写操作，接口文档不会替你批量提交、自动通过、解锁或处理冲突；批量业务使用独立工作台。

飞行人员信息查询的培训记录接口在文档中按页单次调用；要读取全部分页，请使用“飞行人员信息查询（皇帝版）”工作台。

OA 提供“获取全部 OA 数量”和“按数量点击 OA 已阅”两个入口。前者扫描全部分页，显示 OA 总数、可处理公文数、跳过数和各模块数量。后者填写任意正整数：填 1 处理一条，填其他数处理对应数量，不设置最大值；输入数大于当前可处理公文数时自动处理全部可处理公文。

按数量点击开始后，页面先显示全量扫描状态；扫描完成后显示本次目标。执行器只处理 `DOC/official-document`，其他模块跳过，并按列表顺序逐条调用已阅。一条返回后，该条标题、模块、状态和结果立即追加到结果表，再发送下一条；不会等整个批次完成后一次性显示。结果表默认自动跟随到最底部；用鼠标、滚轮或触控向上滚动后会暂停自动跟随，重新滚到底部后恢复。失败后停止继续派发。

## Markdown 导出

点击“导出 Markdown”得到一个单文件文档，内容包括各系统认证网址和获取步骤、当前 catalog 模块、请求方法和地址、参数、响应契约、内部请求链路、技术说明及原始目录 JSON。导出不需要启动本地后端，也不包含粘贴的 Cookie、真实响应或人员数据，适合人类阅读和文本模型分析。
