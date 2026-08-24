# SOC 随机置位 HTTP 接口事实

本文件记录截至 2026-08-24 从 SOC 随机置位申请页面真实 Network/cURL 和授权测试中确认的请求契约。查询/撤销接口仍未确认，不能根据 action 名称补造。

## 系统与页面

- 系统：SOC 运行信息网 2.0。
- 业务含义：“随机”指飞行人员随航班进行置位，即 positioning/deadhead travel，不表示随机选择。
- 基础地址：`https://soc.csair.com/opws-web/`。
- 捕获请求的外层页面：`pages/public/soc.jsp?f=2&s=11&t=1`。
- Network 中观察到的随机置位编辑页面：`pages/aircrew/querypages/KkTvlApply-saveByKkTvlApplyData.jsp`。
- `js/csair/My97DatePicker/calendar.js` 是静态 GET 资源，不是申请数据接口，也不能用于验证登录态。

## 会话事实

捕获的请求携带以下 Cookie 名称：

```text
languageValue
JSESSIONID
com.trs.idm.coSessionId
refreshedTimestamp
trsidssdssotoken
SERVERID
```

这只是当前观察到的完整 Cookie 集合，尚未逐项证明最小必要集合。常见请求头包括：

```text
Origin: https://soc.csair.com
Referer: https://soc.csair.com/opws-web/pages/public/soc.jsp?f=2&s=11&t=1
X-Requested-With: XMLHttpRequest
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

会话失效时，业务 action 返回 `302`，`Location` 指向 `http://soc.csair.com/opws-web/doSsoProxy`；继续跟随会进入 IAM 登录页。静态资源仍可能返回 200，因此必须用业务 action 验证会话。

一次实测中，16:47 左右捕获的 Cookie 到 16:57 已不能重放。这只能证明会话可能很短，不能据此断言固定十分钟过期。捕获后应立即验证和使用。

## 捕获方法

1. 在已登录的 SOC 随机置位页面打开 F12 Network。
2. 勾选 Preserve log 和 Disable cache，过滤 Fetch/XHR。
3. 修改日期、出发站或到达站，触发动态航班请求。
4. 对目标请求执行 `Copy as cURL (bash)`，保存到仓库外文本文件并立即交给探针解析。
5. 至少捕获 `getFltNumList`；首次还原契约时同时捕获 `getStaffValidate` 和 `addKkTvlApply`。

浏览器的“Copy all as cURL”也可以作为证据，但文件会包含大量静态资源。解析时只筛选 `aircrew-KkTvlApply-*` 请求，禁止直接执行整个文件。

## 站点建议

```http
POST /opws-web/flightinfo-FlightPlan-findSuggest.action
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

Form 字段：

```text
dataJson
```

响应为 JSON 对象，候选站点位于 `result` 数组。页面的 `commonlh.js` 在输入框为空时不调用该接口，而是展示内置的 19 个热门城市；输入拼音时调用服务端建议，例如 `zhengzhou` 返回唯一候选“郑州”，`guangzhou` 返回“广州”。中文直接作为查询词时可能返回空数组，因此应使用页面选中的实际站点值继续调用动态航班接口。

## 申请原因

```http
POST /opws-web/aircrew-KkTvlApply-getApplyReasons.action
```

请求没有 form body，响应返回 `rows` 数组。当前实时响应包含 20 条原因；页面显示“学习培训”时，当前业务类型 `KK` 使用的原因代码为 `6`，类型为 `KK`。其它原因代码必须从当前接口或页面动态取得，不能沿用历史样例猜测。

## 动态航班号

```http
POST /opws-web/aircrew-KkTvlApply-getFltNumList.action
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

Form 字段：

```text
kkTvlApplyVO.fltDt
kkTvlApplyVO.depArpCd
kkTvlApplyVO.arvArpCd
```

日期使用 `YYYY-MM-DD`，出发站和到达站使用页面中文值并按 UTF-8 form 编码。一次批量 cURL 文本中的这两个中文值出现过乱码，而后续 percent-encoded body 正常；客户端不得复制乱码字面量。

航班下拉项的 value 是复合业务值，不只是页面显示的 `CZxxxx`。已观察结构包含航班号、计划时间范围、内部航班 ID、多个日期时间、IATA 航线、机型和承运人代码。最终提交的 `kkTvlApplyVO.fltNr` 必须原样使用当前动态响应中用户选中的 option value，不能硬编码、拆后重组或仅提交显示文字。

## 人员与业务校验

```http
POST /opws-web/aircrew-KkTvlApply-getStaffValidate.action
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

已捕获字段：

```text
staffNums
depArpCd
arvArpCd
fltDt
depArpCd2
arvArpCd2
fltDt2
applyReasonCd
hasSecondFlt
fltRoute
```

- `fltRoute` 使用 IATA 航线代码。它应来自所选动态航班，不从中文站名通用推算。
- 单航段捕获值为 `hasSecondFlt=N`，第二航段站点为空；`fltDt2` 仍由页面提交日期值。第二航段业务尚未探测，不能套用单航段契约。
- 单员工校验成功时响应包含 `total`、`rows`，且 `failFeedback` 为空；非空 `failFeedback` 应视为业务拒绝。仍需区分 HTTP 200、登录页和业务拒绝。

## 最终提交

```http
POST /opws-web/aircrew-KkTvlApply-addKkTvlApply.action
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

已捕获字段：

```text
kkTvlStaffNum1
kkTvlStaffMobile1
kkTvlPassportNum1
kkTvlApplyVO.staffNum
kkTvlApplyVO.staffMobile
kkTvlApplyVO.passportNum
kkTvlApplyVO.fltDt
kkTvlApplyVO.depArpCd
kkTvlApplyVO.arvArpCd
kkTvlApplyVO.fltNr
kkTvlApplyVO.fltDt2
kkTvlApplyVO.depArpCd2
kkTvlApplyVO.arvArpCd2
kkTvlApplyVO.applyType
kkTvlApplyVO.applyReasonCd
kkTvlApplyVO.seatSelection
kkTvlApplyVO.applyComment
```

当前随机、单航段、页面默认座位状态的捕获值分别为：

```text
kkTvlApplyVO.applyType=KK
kkTvlApplyVO.seatSelection=N
```

手机号和护照号在该次页面操作中为空，但不能据此认定所有人员都允许为空。备注使用普通 UTF-8 form 字段。一次真实授权提交已返回 JSON `message=录入成功！`，这是当前确认的业务成功判据；HTTP 200 本身仍不足以证明成功。

## 已确认顺序

```text
验证有效会话
-> 获取当前申请原因
-> 按日期和站点获取动态航班
-> 保留所选航班完整 option value
-> 调用人员与业务校验
-> 在当前样例得到明确授权后提交一次
-> 检查业务响应（`message=录入成功！`）并通过查询或报表页面复核记录
```

若 cURL 文件本身包含一次历史 `addKkTvlApply`，先确认该申请未成功、已撤销或已不存在，再决定是否重放。提交请求发生超时后不能自动重发。
