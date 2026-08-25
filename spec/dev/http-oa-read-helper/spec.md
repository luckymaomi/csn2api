# OA 已阅助手（HTTP版）开发规格

## 1. 定位

`http-oa-read-helper` 是独立本地 Python APP。它复用用户自行提供的 OA 已登录 Cookie，通过 `requests.Session` 扫描全部待办，并只对已确认的公文模块逐条执行已阅。工作台不实现登录、不启动 Playwright、不依赖其他工具目录的运行时代码，只监听 `127.0.0.1` 随机端口。

当前为直接运行的预览 APP，不登记首页工具清单，不修改 README，不生成首页下载入口。

## 2. 凭据与页面生命周期

用户信息响应必须包含 `data.loginUserInfo.empId` 和 `data.loginUserInfo.empName`。页面显示“员工号 · 姓名”；身份只保存在内存 Session，不写日志或文件，主动清除、刷新清除或会话失效时与 Cookie 同步删除。

工作台接受浏览器 Network 面板的 Copy as cURL 文本、`Cookie: ...` Header 或 Cookie 键值串。凭据文本只被解析，不作为命令执行；所有 Cookie 键值进入 Python 后端的 `requests.Session`。完整 cURL 中的浏览器 User-Agent 经单字段白名单解析后复用于 Session，以对齐旧探针的浏览器会话上下文；Authorization、自定义头和其他 cURL 内容不会透传。纯 Cookie 输入继续使用本地默认 User-Agent。

页面验证成功后清空输入框，并只在验证成功的那一次响应中接收规范化 Cookie Header，显示当前页复制面板。页面不使用 localStorage、sessionStorage、IndexedDB 或文件保存凭据；刷新、重新打开、主动清除或会话失效后面板立即清空。页面首次加载调用 `POST /api/session/clear`，清除后端旧 Session；因此刷新或重新打开页面后需要重新粘贴并验证。运行中的批次拒绝清除 Session。

除验证成功响应的一次性顶层 `credentials` 外，状态 API、页面结果、日志和静态文件不返回 Cookie。页面完整显示 OA 标题和模块信息，不对授权账户内的业务标题做脱敏、截断或替换。

凭据验证接口：

```text
GET /oai/work/login/userInfo
```

HTTP 200 之外还必须满足 JSON 根节点为对象且业务码 `code` 为 `200`。验证使用 5 秒连接、10 秒读取超时；业务码 `301` 或重定向视为登录失效。验证不自动跟随 SSO 重定向，避免把最终登录页的 HTTP 200 误判为有效 Session。

验证和扫描只在修改 manager 内存状态时持有状态锁，等待 OA 网络响应期间允许 `/api/status` 继续读取“验证中”或“扫描中”。验证失败后清除旧 Session 并进入明确失败状态；验证或扫描进行中拒绝重复前台动作。

## 3. 人工分步与 Agent 入口

页面保留四个独立动作：

1. 验证凭据。
2. 扫描全部待办。
3. 开始已阅。
4. 终止当前批次。

验证成功后 Session 保留在当前 Python 进程，扫描与同一页面内的后续批次复用该 Session。每批结束、失败或终止后扫描结果失效，必须重新扫描，避免使用已变化的旧待办集合。

`POST /api/start` 是 agent 全链路入口，可提供凭据，也可复用当前已验证 Session；它依次执行凭据验证、全部扫描和开始已阅。

## 4. 待办扫描

待办列表接口：

```text
POST /oai/work/box/query/waiting
Content-Type: application/json
```

工作台从用户粘贴的 `waiting` 完整 cURL 动态读取当前页面 JSON 请求模板，只覆盖分页字段。若模板包含仪表盘筛选字段 `moduleMainCategoryId`，扫描时移除该字段以查询全部待办；其余动态字段保留。纯 Cookie 输入使用已确认的全量最小模板：

```json
{
  "offsetPageIndex": 0,
  "pageMode": "page",
  "resultCountPerPage": 100
}
```

`offsetPageIndex` 从 0 开始。客户端在动态 JSON 包装中识别已确认的记录字段 `resultMyBoxItems/resultList/rows/records/list/content/items` 和总数字段 `totalRecordCount/totalCount/total/recordsTotal/totalElements`；总数可以是非负整数或整数字符串。存在总数时按当前总数收敛，不存在总数时按空页、短页或不再出现新记录收敛；记录按 `fileId + stepItemId` 去重，不设置固定页数上限。记录缺少标题、内部标识或模块分类时停止，不猜测业务字段。

扫描结果按 `moduleMainCategoryCode/moduleSubCategoryCode` 分类，页面显示每类数量、模块名称、动作和完整示例标题。

## 5. 模块规则

当前唯一可执行模块：

```text
DOC/official-document
```

所有其他模块统一标记为“跳过”，不会进入已阅 runner，也不会调用公文接口。当前包括但不限于 ESMS、DI、Ehome、VCSA 和 OSMS；没有浏览器取证和唯一字段映射前，不把公文契约外推到这些模块。

## 6. 数量模式

指定数量模式由用户输入任意正整数，不设置最大值。实际执行数为：

```text
min(用户输入数, 当前扫描的同类公文数)
```

输入大于可处理数时不报错，自动处理全部可处理公文。页面在开始前显示实际目标数量。

无限模式是页面默认模式，忽略数量输入并处理本次扫描中的全部同类公文。它不轮询未来新增待办；本次扫描处理完即完成。不同模块仍然跳过，因此异类留在列表不阻止无限模式完成。

执行区只保留“无限模式”和“指定数量”两个模式。点击“开始已阅”即按当前选中模式执行。模式按钮始终显示圆形选择标记，选中项同时使用完整边框、状态背景和状态文字色。

## 7. 公文已阅

公文已阅接口：

```text
POST /oai/doc/pc/form/sw/haveRead
Content-Type: application/json
```

字段映射：

| 请求字段 | 待办记录字段 |
|---|---|
| `docId` | `fileId` |
| `docType` | `fileTypeId` |
| `flowStepId` | `stepItemId` |

`approveOpinionType` 和 `approveOpinionContent` 均提交 JSON null。

单条成功条件同时包括：

1. 已阅请求 HTTP 200。
2. JSON 根节点为对象且业务码为 `200`。

已阅请求每条最多提交一次。接口业务成功后立即记录成功并派发下一条，不额外查询待办、不等待记录消失，也不重复提交。

## 8. 执行顺序、停止与失败

runner 只维护一个执行线程，一条记录的已阅接口返回后才派发下一条，不提供并发参数或并发 API。

人工终止在当前 HTTP 请求完成后的记录边界生效。

只有登录会话失效时，本批进入失败状态并停止后续派发。已阅 HTTP 异常、响应结构异常、业务码异常及其他单条异常都只将当前记录标记为失败并继续下一条；本批结束后保留失败状态和失败计数。前端逐条显示完整标题、模块、状态和结果，日志显示当前业务进度，不记录 Cookie、内部记录 ID 或原始响应正文。

## 9. 状态与本地 API

manager 维护等待凭据、验证中、凭据有效、扫描中、扫描可用、运行中、终止中、已终止、已完成和失败阶段。状态只保存在 Python 内存，不生成业务结果文件。

本地 API：

```text
POST /api/session/clear
POST /api/session/verify
POST /api/scan
POST /api/run
POST /api/stop
POST /api/start
GET  /api/status
```

`/api/run` 和 `/api/start` 接受 `runMode=finite|all` 与 `maxCount`。`finite` 对应指定数量，`all` 对应无限模式并作为缺省值。

## 10. 模块职责

| 模块 | 职责 |
|---|---|
| `credentials.py` | cURL/Cookie 解析与无值摘要 |
| `models.py` | 待办、分类、扫描和批次模型 |
| `portal_client.py` | Session、动态分页、业务码和已阅 |
| `runner.py` | 逐条执行、停止边界和逐条事件 |
| `manager.py` | Session、扫描快照、批次线程和状态 |
| `server.py` | loopback API 与静态页面 |
| `web/` | 凭据、扫描、数量模式、完整标题、结果和日志 |

验证成功后，APP 内独立保活线程每 30-60 秒调用 OA 用户信息只读接口；保活与待办扫描、逐条已阅共用请求锁但职责分离，会话失效时停止后续请求。IEB 与 OA 不共享 Cookie、Session 或保活线程。前端保活展示模块采用可降级动态加载；模块加载失败时显示明确警告，但不得阻断凭据验证、扫描和已阅按钮的核心通信。

## 11. 验证边界

自动测试只使用虚构 Cookie、虚构标题和虚构内部标识。真实 Cookie、标题、人员、记录 ID、响应正文和探针契约文件不进入测试、静态源码或 Git。

真实验证已经确认公文模块的浏览器按钮接口、字段唯一映射、纯 HTTP 单条和逐条批处理。其他模块仅扫描展示并跳过，未验证其已阅接口。
