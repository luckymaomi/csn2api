# 运行资质人员名册规格

## 产品边界

`http-qualification-roster-helper` 是 IEB 技术资料组合筛选的只读工作台。它按当前门户动态筛选字段和运行资格列表查询人员，不执行门户写操作。每个选中的运行资格单独执行一次人员查询和一次普通人员清单导出，再把员工号、姓名和本次资格代码追加到同一张 Excel。

## 输入

- Cookie 接受完整 IEB Copy as cURL 或 Cookie Header，必须包含 `JSESSIONID` 和 `iebJSid`。
- 验证后读取技术资料页面的注册基地、运行基地、技术基地、执飞机型、是否混飞、技术等级、是否帮飞、检查员/教员、在职状态、分部选项。
- 执飞机型默认选择当前动态页面中值为 `777` 的项；在职状态默认选择当前页面的 `ZAIZHI`、`WAIBU`、`TUIXIU`、`LIZHI`。
- 运行资格由 `/showChooseOperQualificationList` 动态读取。默认选择当前返回中存在的 `RAMA`、`REUO`、`RWAS`、`RSEA`、`EAMA`、`EEUO`、`EWAS`、`ESEA`、`RANC`、`RORD`、`RJFK`、`RLAX`、`RNLU`；缺失代码不伪造。

## 请求与归属

- `showEmpProfileCompositeResult` 的 `operQualArray` 每次只发送一个资格代码。门户多个代码查询是 OR，不能用一次多选结果推断人员对应的单项资格。
- `activeStatusArray` 和多选机型/技术等级按重复 Query 参数发送；未选择的 `qualTypeArray` 省略，不能补空值。
- 每项先记录查询总人数，再调用 `/createEmpProfileCompositeExcel`。普通导出响应虽可能命名为 `.xls`，实际按 OOXML ZIP 验证；worksheet 的 dimension 错误不能作为空文件依据，读取前重置维度。
- 员工号和姓名从普通导出表头按名称定位。员工号在 Excel 和前端按文本处理；普通导出返回的每一行都保留，跨资格同一员工保留多行，不做名单去重。

## 执行与状态

- 选中资格严格按页面顺序串行执行，不开并发入口，不自动重试。
- 行级 HTTP、解析、动态数据缺失或人数核对失败只标记当前资格失败并继续；只有会话失效停止后续资格。
- 用户停止只阻止下一资格，已发出的请求返回后保留已完成关系和 Excel。
- 每个资格完成后原子更新 Excel，避免整批结束前丢失结果。

## 输出

Excel 单 Sheet `运行资质人员名册` 固定四列：`序号`、`员工号`、`姓名`、`资质类别`。序号按合并结果连续；资格类别只写当前逐项查询代码。

页面显示每项人数、完成/成功/失败、人员资质明细数、逐项结果和活动日志。结果区固定高度并支持横纵向滚动，用户向上滚动后暂停自动跟随。

## 会话

验证成功解析当前登录人并启动 30-60 秒随机间隔只读保活。保活与查询共享 Session 请求锁但不混入 runner；会话失效时清除身份和当前页 Cookie，并停止后续资格。

## 文件职责

- `ieb_protocol/base.py`：IEB Cookie、Session、身份和会话失效。
- `ieb_protocol/roster_models.py`、`roster_contract.py`：动态筛选、资格、人员关系、重复参数和 OOXML 契约。
- `ieb_protocol/qualification_roster.py`：页面、资格列表、查询和普通人员导出生产请求。
- `portal_client.py`：共享 core 的 APP 会话、元数据和保活适配。
- `exporter.py`：四列 Excel 的增量原子写入。
- `runner.py`：逐资格串行、人数核对、失败继续和会话停止边界。
- `manager.py`：内存会话、状态、进度、日志和下载路径。
- `server.py`：loopback API 和静态资源。
- `web/`：标准主题、保活、筛选、结果表和滚动交互。
