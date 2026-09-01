# 航班明细查询（皇帝版）开发规格

## 产品边界

`http-flight-detail-helper` 是独立的 IEB 纯 HTTP 本地工作台，只读取已登录门户的月度逐航班明细。工具不实现登录、验证码、浏览器自动化或任何生产写操作，服务只监听 `127.0.0.1`。

输入严格为四列：`员工号`、`姓名`、`开始年月`、`结束年月`。员工号按六位文本处理；月份支持 `YYYY/M` 和 `YYYY/MM`，按闭区间展开自然月。Excel 与粘贴输入使用相同表头和归一规则，重复员工号只保留首次记录并报告输入错误。

## 已确认接口

- 会话验证读取 `GET /newieb/flytime/showFlytimeManyQuery`，随后读取当前登录身份。
- 每名员工先调用 `POST /newieb/basics/flytimeList` 读取动态时间轴。
- 每个覆盖月份调用 `GET /newieb/flytime/showFlyDetail`，参数使用 `dateType=2`、`startStr=YYYY-MM`、空 `endStr`、员工号、页面姓名和时间轴动态机型。
- 月度明细表头为：序号、航班号、机型、日期、左座、右座、操纵、观察、离场、到达、飞行时间、夜航、飞行阶段、人工飞行时间、人工飞行方式。
- 主行通常有 14 个直接单元格，人工飞行方式可能在后续附加行；按下一条数字序号主行分组解析，不按固定行数切分。

## 执行和状态

按输入人员顺序、每人覆盖月份顺序严格串行。时间轴每人最多读取一次；普通请求、动态机型缺失和解析异常只标记当前人员/月失败并继续。登录失效停止后续派发，剩余人员/月标记未查询；用户终止只阻止请求边界后的新任务，不自动重试。

结果按人员/月事件逐步追加到常驻 Excel 工作簿，默认每 20 个人员/月批量原子落盘一次；完成、停止、会话失效或异常时强制收口并关闭工作簿。`航班明细` Sheet 首列为本地序号，之后是姓名、员工号及门户明细字段；`查询状态` Sheet 记录每个人员/月状态、错误说明和航班数量；输入错误单独记录。下载读取最近完整检查点，不在单次请求中重建历史全部结果。

## API

- `POST /api/session/verify`：验证 Cookie，并一次性返回当前页规范化凭据。
- `POST /api/check-data`：检查 Excel Base64 或粘贴的四列表格。
- `POST /api/run`：按当前有效会话开始批量查询。
- `GET /api/status`：读取脱敏会话、进度、计数、结果版本和日志，不返回航班明细行。
- `GET /api/results?kind=status|detail&offset=0&limit=50`：分页读取逐月状态或航班明细；`limit` 最大 200，前端默认状态 50 行、明细 100 行。
- `POST /api/stop`：停止后续人员/月请求。
- `GET /api/download/result`：下载最近检查点 Excel。


## 文件职责

- 共享 `ieb_protocol/flight_detail_contract.py`、`flight_detail.py`：真实时间轴、月度参数和多行表格契约。
- APP `input_data.py`、`portal_client.py`、`runner.py`、`exporter.py`、`manager.py`、`server.py`：输入、会话适配、编排、检查点、状态和 loopback 路由。
- `web/`：凭据、四列输入、运行状态、逐月状态、航班明细和日志。
