---
name: flight-portal-http-probe
description: 探测、复用或维护 IEB 飞行门户纯 HTTP 接口与本地 HTTP 工作台，包括 Cookie/cURL 会话、飞行经历、技术等级运行资格、资质监控按资质查询、原生 Excel 导出和非生产任务锁班状态动作。用户要求不使用 Playwright、分析 Network 请求、构造 requests/httpx 客户端或维护 HTTP 前缀 APP 时使用。
---

# 飞行门户 HTTP 接口探针

用于把已登录门户中的真实请求还原为结构化 HTTP 客户端。它统一技术方法，不合并业务授权：飞行经历是只读查询，锁班提交、通过、撤销、解锁和否决是写操作。

## Reference 路由

- 每次 HTTP 探测都先完整读取 [会话与探测方法](references/session-and-probing.md)。
- 非生产任务锁班接口、动态类型、时间模式、查询、通过、撤销、解锁或冲突恢复：读取 [锁班接口事实](references/lock-entry-api.md)。维护锁班本地 APP 时再读取 [锁班工作台约束](references/lock-entry-workbench.md)。
- 飞行时间、飞行经历、左座经历与起落数查询：读取 [飞行经历接口事实](references/flight-stats-api.md)。维护对应本地 APP 时再读取 [飞行经历工作台约束](references/flight-stats-workbench.md)。
- 飞行航班逐月明细、`flytimeList` 时间轴、`showFlyDetail` 多行表格或按月导出：读取 [飞行航班明细接口事实](references/flight-detail-api.md)。该路径只在真实探针确认后维护，不得用汇总接口或固定五行假设替代。
- 技术等级、运行资格和人员技术资料查询：读取 [技术等级与运行资格接口事实](references/qualification-query-api.md)。维护对应本地 APP 时再读取 `spec/dev/http-qualification-query-helper/spec.md`。
- 资质监控、按资质查询、三类动态子类、分页明细或门户原生 Excel 导出：读取 [资质监控按资质查询接口事实](references/qualification-monitor-api.md)。维护对应本地 APP 时再读取 `spec/dev/http-qualification-monitor-helper/spec.md`。
- 涉及 Excel 时同时使用 `excel-dev`；正式修改工具时同时使用 `csn2api-dev`，涉及页面时再使用 `ui-clarity`。

## 共同行为

1. 先确认当前会话有效，并区分登录页、HTTP 错误和业务失败；HTTP 200 不是成功证据。
2. 从真实页面 Network、用户提供的 Copy as cURL 或现有生产代码取得 URL、方法、Headers、Query、Body 和响应格式，不凭相邻接口猜字段。
3. cURL 只作为文本解析，不作为命令执行；请求用结构化 params/form/json API 构造，重复 key 使用 tuple 列表保留。
4. 检查 Cookie、CSRF、隐藏字段、动态签名、Referer、Origin、XHR Header 和页面初始化依赖，并区分已验证事实与当前未观察到。
5. 响应按 HTML/JSON 结构解析，按员工号、可选姓名、类型、日期时间和记录状态精确归属；不取第一行代替目标。
6. 只读接口先用一个小样本验证，再批量。执行顺序和并发边界以目标 spec 为准；没有真实证据与 owner 明确要求时不新增并发入口。
7. 状态变更只在 owner 对当前样例和动作明确授权时执行；动作前唯一定位，动作后重新查询确认状态。
8. 探针、Cookie、原始响应、真实人员和临时结果只放系统临时目录，结束后删除，不进入仓库。
9. 还原用户正向链路：页面先按姓名、员工号或动态字典查询，再取得内部 ID 或动态值时，客户端保持同样的解析与唯一归属，不把内部 ID 直接暴露为主要输入。
10. 实现前用真实 Session 记录请求和响应契约，实现后通过统一真实验收分别复验 API 文档与 APP；只调用 client 或只看到 HTTP 200 都不算入口验收完成。

## 新 APP 前置门禁

新增 APP 的工作顺序固定为：

1. 使用 owner 当次授权的真实 Session，以页面正向链路完成只读 HTTP 探针，确认 URL、方法、参数存在性、动态选项、响应结构、实体归属和异常边界。
2. 只把已经由探针确认、且会改变后续实现决策的经验写入本 skill 的相关 reference；一次响应的人员、数量、排序、Cookie、原始 HTML/JSON 不写入 skill。
3. 在仓库根目录创建被 `.gitignore` 忽略的临时探针脚本、合成样例输入和脱敏结果摘要，供 owner 审核。脚本不得内嵌 Cookie 或真实身份，结果不得包含原始响应、姓名、员工号、记录 ID 或截图。
4. owner 明确审核确认前，只能继续补充探针证据和修正规约，不得创建新的 APP 目录、工具登记、独立 ZIP、业务实现或正式真实验收 Case。
5. owner 确认后，先写目标 spec 和失败测试，再实现共享 core、API 文档、APP、测试和分发闭包；修改后仍需用同一真实链路复验 API 文档和 APP。

月度明细的已确认实现提示：`dateType=1` 年请求是月度汇总；`dateType=2` 且 `startStr=YYYY-MM` 返回航班明细。明细表的数字序号行后面可能跟人工飞行方式和空白行，必须按下一条数字序号边界解析，不能按固定行数切分。

## 维护边界

- HTTP 技术层只替换浏览器渲染和 DOM 操作，不擅自改变输入、类型、日期、额度、结果、冲突、导出或用户分步习惯。
- 登录由用户维护。工具不实现扫码、验证码或自动刷新，也不声称 `document.cookie` 能导出 HttpOnly Cookie。
- 凭据只存在监听 `127.0.0.1` 的本地后端内存，不写 localStorage、日志、状态 API、Excel、fixture、截图或 Git。API 文档本地执行器的当前页展示与刷新清理按 `api-docs-dev` 执行；其他工具不回显凭据。
- 门户结构变化、登录失效、表头缺失、归属不唯一或接口响应契约异常时停止当前记录，不通过旧字段、固定 ID 或无限重试掩盖变化。
- 门户动态字典、表头和分页必须在当前会话读取。静态代码只保存已确认且稳定的业务代码；当前数量、排序和一次响应快照不写死。
