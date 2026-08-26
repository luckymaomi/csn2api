# 锁班皇帝（新）开发规格

## 1. 定位

`http-lock-entry-helper` 是独立本地 Python APP。它使用用户提供的 IEB 已登录会话，通过 `requests.Session` 按输入顺序逐条调用非生产任务 HTTP 接口，不实现登录、不启动浏览器，也不依赖其他本地仓库。

页面名称为“锁班皇帝（新）”，唯一入口为 `startapp.py`，只监听 `127.0.0.1` 的随机端口。

## 2. 会话与动态类型

工作台接受浏览器 Network 面板的 Copy as cURL 文本或完整 Cookie Header，只提取 `JSESSIONID` 和 `iebJSid`。粘贴内容不作为命令执行，凭据只保存在当前 Python 进程内存和当前页面生命周期。

验证阶段请求：

```text
GET /newieb/nonproductionTask/showNonproductionTaskImportPage
GET /index/index
```

录入页必须包含 `#nonproductionTaskImportForm` 与 `#lockType`。每次验证从 `option[value]` 动态读取类型代码、名称、`class` 和 `id`；首页读取当前登录员工号与姓名。验证成功后页面显示身份、类型数量、类型版本和当前页可复制凭据。

验证成功后独立保活线程每 30–60 秒只读检查录入页。保活与批次请求共用请求锁；会话失效时清除身份和凭据，并停止派发后续记录。

## 3. 操作流程

页面提供四个独立动作：

1. 验证凭据。
2. 数据健康检查。
3. 开始录入。
4. 终止当前批次。

检查只提示有效数、无效数和逐条原因。开始录入时重新解析当前输入，只处理有效记录。批次完成或终止后保留当前有效 Session，可继续处理下一批。

“提交成功后直接通过并锁班”默认不勾选。勾选后每条记录仍按“提交并即时保存待审批结果 -> 通过 -> 查询确认已锁且不再待审批”串行执行；通过失败单独记录，保留已经生成的待审批结果。

## 4. 输入

Excel 使用活动 sheet，按表头名读取。必需表头：

```text
员工号（或工号）
姓名
锁班类型（或请假类型）
开始日期
结束日期
```

可选表头：

```text
时间模式（或锁班时间类型）
开始时间
结束时间
月份（或锁班月份）
锁班日期（或日期列表）
备注（或锁班原因）
```

员工号按六位文本归一。日期支持 Excel Date、Excel serial、`YYYYMMDD` 和明确的 `YYYY-M-D`、`YYYY/M/D`、`YYYY.M.D`；时间使用分钟粒度 `HH:mm`。

锁班类型支持代码、`代码-名称` 或门户完整标签，最终必须唯一匹配当前动态类型。程序不改写输入类型，每条记录按匹配后的当前 code 生成一个提交请求。Excel 姓名用于一致性提示，提交姓名和部门来自员工校验响应。

每行备注优先于统一备注；两者为空时使用录入页当前默认原因模板。原因最长 60 个字符。

## 5. 时间模式

模式 1 按连续时间段提交：

```text
lockTimeType=1
startDt=YYYY-MM-DD HH:mm
endDt=YYYY-MM-DD HH:mm
lockDays=<连续自然日数>
```

模式 2 按月份提交，多个 `lockDaysNum` 使用重复同名字段：

```text
lockTimeType=2
lockYearAndMonth=YYYY-MM
lockDaysNum=<日号>
lockStartHourAndMinute=HH:mm
lockEndHourAndMinute=HH:mm
```

`class="1"` 的类型、`ALV_FD` 和 `CRM` 使用模式 1。CRM 默认时间为 `08:30-16:30`，其他类型默认 `08:59-19:59`。

## 6. 单条执行

每条有效记录依次执行：

1. 从当前动态类型元数据取得 code、描述、时间限制和 `dateSplitFlag`。
2. `POST /newieb/nonproductionTask/vaildStaffNum` 校验员工并读取门户姓名、部门。
3. 构造一个结构化表单 Body。
4. `POST /newieb/nonproductionTask/showNonproductionTaskImportResultPage` 一次。
5. 同时解析普通结果区与冲突结果区；冲突区按当前序号、锁班结果、员工号、姓名、部门、开始日期、结束日期、锁班天数、锁班类型、锁班原因和冲突表头读取，并按员工、姓名、类型和完整日期时间精确归属。
6. 立即写入结果 Excel，再处理下一条。

门户的 `showNonproductionHolidayRulesTips` 是选定人员和类型后展示年度额度的独立只读请求，额度值不进入锁班提交 Body。工作台按输入类型原样提交，不根据额度切换类型或拆分记录。

HTTP 200、第一行数据和提示文字均不能单独证明业务成功。普通结果精确归属后记录成功；冲突结果记录冲突，并把门户“冲突”字段保存为独立冲突原因；存在冲突数据行但缺少“冲突”表头、登录页、缺表、其他契约变化或无法归属时记录当前行失败。普通失败和冲突继续后续行；会话失效停止；每条锁班提交最多一次。

## 7. 状态与结果

manager 维护等待凭据、验证中、凭据有效、检查数据、数据已检查、运行中、终止中、已终止、已完成、会话失效和失败阶段。

每批创建 `results/<runId>/HTTP锁班结果_<runId>.xlsx`。结果按产生顺序原子保存，包含来源行、员工号、输入/门户姓名、输入/实际类型、输入/实际日期时间、时间模式、处理状态、门户结果、冲突原因、备注、说明和记录时间。冲突原因保存门户业务说明，通用说明保存请求、解析、归属和后续动作信息。

页面显示同源逐条结果、进度和日志。结果区与日志区默认跟随最新内容，用户滚动离开底部后保持当前位置。

## 8. 本地 API

```text
POST /api/session/verify
POST /api/check-data
POST /api/run
POST /api/stop
GET  /api/status
GET  /api/download/result
POST /api/start
```

`/api/start` 可串联凭据验证、数据检查和开始录入，也可复用进程内已验证 Session。前端人工路径保持分步操作。

## 9. 模块职责

| 模块 | 职责 |
|---|---|
| `credentials.py` | cURL/Cookie 解析与规范化 |
| `metadata.py` | 动态类型、默认原因模板和类型归一 |
| `input_data.py` | Excel/粘贴、日期时间和输入检查 |
| `portal_client.py` | Session、员工校验、提交、查询和直接通过 |
| `result_store.py` | 原子即时结果 Excel |
| `runner.py` | 单片段严格串行执行与中断边界 |
| `manager.py` | Session、批次线程、状态和下载 |
| `server.py` | loopback API 与静态页面 |
| `web/` | 人工分步、结果、进度、日志和保活展示 |

## 10. 验证边界

仓库测试使用虚构人员和脱敏 HTML/JSON，覆盖动态类型、Excel 日期、员工校验、两种时间模式、年假/疗养原样单次提交、普通结果、冲突、直接通过、会话失效、逐条保存和 loopback 服务。

真实写验证需要 owner 对当前人员、日期、时间、类型、备注和动作逐项授权。Cookie、身份、记录 ID、响应和结果文件不得进入仓库。
