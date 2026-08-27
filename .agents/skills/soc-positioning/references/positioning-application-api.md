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

当前登录姓名可通过只读 `GET /opws-web/pages/public/soc.jsp?f=2&s=11&t=1` 取得。页面在 `#checkout_soc` 或 `#checkout` 中服务端渲染 `欢迎您，<姓名>`；一次真实会话确认该姓名与浏览器登录者一致。SOC 客户端只解析并显示该姓名，不维护登录员工号识别逻辑。

一次实测中，16:47 左右捕获的 Cookie 到 16:57 已不能重放。这只能证明会话可能很短，不能据此断言固定十分钟过期。捕获后应立即验证和使用。

同一 Cookie 在另一台电脑或操作系统重放失败，不能直接归因于 Windows/Linux 或本机时钟。应在相近时间用同一业务验证请求对照：原始 Cookie 字节是否被 Markdown/终端转义改变、最终 URL 是否进入 SSO、网络出口是否不同，以及负载均衡或 SSO 是否绑定当前会话。`refreshedTimestamp` 与 `SERVERID` 按服务端返回值原样携带，不由客户端用本机时间重算；没有受控对照时不声称某个字段或操作系统导致失效。

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

当前页面的申请原因下拉框可以使用以下静态字典，不需要依赖接口动态填充：

| 代码 | 原因 |
| ---: | --- |
| 26 | 要客保障 |
| 1 | 商务跟机 |
| 23 | 保卫跟机 |
| 29 | 特殊装卸 |
| 30 | 军事信使 |
| 28 | 货机押运 |
| 10 | 本场训练 |
| 5 | 其它 |
| 3 | 复训 |
| 4 | 体检 |
| 6 | 学习培训 |
| 8 | 调配飞行 |
| 9 | 调勤帮飞 |
| 15 | 执行航班 |
| 16 | 航班调整 |
| 2 | 模拟机 |
| 11 | 飞行改装 |
| 13 | 航线检查 |
| 25 | 安全监察 |
| 31 | 外籍休假 |

上述字典来自当前页面实际渲染的 20 个 option，`KK` 业务提交时直接使用代码。接口仍可用于只读探测或页面变更核对；若接口与字典不一致，应停止写操作并重新确认，不在运行时猜测新代码。

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

当前站点建议接口没有空值、`all` 或通配符全量查询。按 26 个拼音首字母聚合可得到约 744 个去重候选，包含热门城市之外的郑州、南京、南宁等；页面实现可以维护一份经过清洗的本地候选字典，并在用户输入拼音时调用建议接口补充。候选列表可能包含国际机场或特殊值，不能替代日期、航线和动态航班校验。

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
-> 使用申请原因静态字典（必要时只读核对接口）
-> 按日期和站点获取动态航班
-> 保留所选航班完整 option value
-> 调用人员与业务校验
-> 在当前样例得到明确授权后提交一次
-> 检查业务响应（`message=录入成功！`）并通过查询或报表页面复核记录
```

若 cURL 文件本身包含一次历史 `addKkTvlApply`，先确认该申请未成功、已撤销或已不存在，再决定是否重放。提交请求发生超时后不能自动重发。
