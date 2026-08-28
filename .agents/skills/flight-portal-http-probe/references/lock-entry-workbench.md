# HTTP 锁班工作台实现约束

## 产品定位

`http-lock-entry-helper` 是独立本地 APP。用户自行提供 IEB 已登录凭据，APP 按 Excel 或粘贴数据中的逐行类型、日期、时间和备注执行锁班录入。独立入口为 `start.py`，统一局域网入口由仓库根目录 `start_all.py` 动态接入。

工作台不提供整批类型选择器。每条记录在当前门户动态类型中归一后原样提交，不切换类型或拆分记录。

## 人工分步

前端保持四个独立动作：

1. 验证凭据并动态加载当前锁班类型。
2. 数据健康检查。
3. 开始录入。
4. 终止当前批次。

检查只提示，不作为确认门槛。开始录入时重新解析当前输入。批次结束后保留有效 Session，可继续下一批。

“提交成功后直接通过并锁班”默认不勾选。启用后按“提交并保存待审批结果 -> 通过 -> 查询确认已锁且不再待审批”执行；通过失败要保留第一步结果。

## 凭据与会话

接受 Chrome/Edge Copy as cURL 或完整 Cookie Header，只提取 `JSESSIONID` 和 `iebJSid`。凭据只存在当前后端进程内存和当前页面，不进入状态、日志、Excel 或静态文件。

验证请求为 `GET /newieb/nonproductionTask/showNonproductionTaskImportPage`，有效页面同时包含 `#nonproductionTaskImportForm` 与 `#lockType`。解析全部 `option[value]` 的 code、label、class 和 id；不得使用固定类型字典。首页身份请求提供当前登录员工号和姓名。

验证后使用录入页只读保活。登录失效会停止后续请求并清除当前凭据。

## 输入契约

必需字段为员工号、姓名、锁班类型、开始日期和结束日期。可选字段为时间模式、开始时间、结束时间、月份、锁班日期和备注。

- 员工号按六位文本归一。
- 日期在读取边界归一为业务日期，不使用 UTC 转换。
- 类型支持 code、`code-名称` 和门户完整标签，最终匹配当前动态元数据。
- CRM 默认 `08:30-16:30`，其他类型默认 `08:59-19:59`。
- 模式 2 保留重复 `lockDaysNum`。
- 每行备注优先于统一备注，两者为空时使用当前门户默认原因。
- Excel 姓名用于一致性提示，提交身份来自 `vaildStaffNum`。

## 单条执行

1. 取得当前输入类型的动态元数据。
2. 调用 `vaildStaffNum` 校验员工并读取姓名、部门。
3. 按当前类型和时间模式构造一个结构化表单 Body。
4. 调用 `showNonproductionTaskImportResultPage` 一次。
5. 分别解析普通结果和冲突结果。
6. 按员工、门户姓名、类型和完整日期时间精确归属。
7. 立即保存结果，再处理下一条。

`showNonproductionHolidayRulesTips` 是门户选定人员和类型后展示年度额度的只读请求，不参与 APP 类型归一和提交 Body。

普通失败和冲突记录当前行后继续；Session 失效停止；每条锁班提交最多一次。工作台不自动查询旧锁班、解锁或重提。

## 模块职责

| 模块 | 职责 |
|---|---|
| `ieb_protocol/base.py` | 共享 Cookie、Session、登录失效与当前身份协议 |
| `ieb_protocol/lock_*.py` | 共享动态类型、表单、结果、查询和状态动作协议 |
| `input_data.py` | Excel/粘贴归一和检查 |
| `portal_client.py` | APP 会话生命周期与共享协议的薄适配 |
| `runner.py` | 严格串行单次提交 |
| `result_store.py` | 逐条原子保存 |
| `manager.py` | Session、批次状态和下载 |
| `server.py` | loopback API 与静态页面 |
| `web/` | 分步交互、进度、结果、日志和保活 |

## 本地 API

```text
POST /api/session/verify
POST /api/check-data
POST /api/run
POST /api/stop
GET  /api/status
GET  /api/download/result
POST /api/start
```

服务只监听 `127.0.0.1`。`/api/start` 可携带凭据或复用进程内已验证 Session；前端人工路径不调用该组合入口。

## 结果与测试

每条结果立即写入 `results/<runId>/`。结果包含输入上下文、门户身份、实际类型和日期时间、状态、门户结果、冲突原因、备注与说明。门户“冲突”字段写入冲突原因，普通结果该列为空；缺少该表头时报告响应契约变化。

测试覆盖动态类型、新增类型、Excel 日期、两种时间模式、年假/疗养原样提交、普通结果、冲突不重试、直接通过、会话失效、逐条落盘和 Session 复用。真实写操作需要 owner 对当前对象和动作逐项授权。
