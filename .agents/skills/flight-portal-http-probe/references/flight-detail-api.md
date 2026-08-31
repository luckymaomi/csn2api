# IEB 飞行航班明细接口事实

本 reference 只记录已通过真实只读探针确认、会影响实现决策的契约。人员、Cookie、原始响应和一次探测的数量快照不写入本文件。

## 正向链路

先请求：

```text
GET /newieb/flytime/showFlytimeManyQuery
```

最终 URL 不能进入 `/login`，页面必须存在 `#showflyTimeExperienceQueryForm`。

按员工读取动态时间轴：

```text
POST /newieb/basics/flytimeList
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

staffNum=<六位员工号>
currentStr=<防缓存值>
```

时间轴按钮的真实调用形状为：

```text
showflyTimeDetail('<dateType>','<staffNum>','<staffName>','<startStr>','<endStr>','<fleetCdArray>')
```

`fleetCdArray` 来自当前页面动态按钮；不能固定员工、年份或机型清单。若当前时间轴没有目标月份，调用方必须明确记录未观察到动态值，不得猜测历史机型。

## 月度明细请求

```text
GET /newieb/flytime/showFlyDetail
```

请求参数：

```text
startStr=YYYY-MM
endStr=
dateType=2
staffNum=<六位员工号>
staffName=<页面姓名>
fleetCdArray=<动态机型代码>
```

月度航班明细使用 `dateType=2` 和 `startStr=YYYY-MM`；查询月份必须按当前需求逐月发送，参数值沿用页面真实调用形状。

## 响应结构

月度响应包含一个月度汇总表和一个可选的航班明细表。航班明细表的当前表头为：

```text
序号、航班号、机型、日期、左座、右座、操纵、观察、离场、到达、飞行时间、夜航、飞行阶段、人工飞行时间、人工飞行方式
```

明细表不是普通的单行 table：

- 航班主行第一格是数字序号，主行通常只有 14 个直接单元格；
- 主行单元格可能带 `rowspan`；
- “人工飞行方式”可能在主行之后的单独单元格中，例如自动驾驶状态文本；
- 后续还可能有一个或多个空白行；
- 航班组行数是动态的，不能按固定 5 行切分；应以“下一条数字序号主行”作为边界，并从组内首个非空附加单元格提取人工飞行方式；
- 无数据响应仍可能保留明细表头，成功判定不能只看 HTTP 200 或 table 是否存在。

表头和每个主行必须通过结构化解析校验；单元格存在 `title` 时优先读取完整值。按员工号和输入姓名校验归属，登录页、归属不唯一、表头重复或列宽异常时停止当前记录。

## 请求与安全边界

请求使用已验证 IEB Session、`Referer: https://ieb.csair.com/index/index`、`X-Requested-With: XMLHttpRequest` 和 HTML `Accept`。当前探针未观察到 CSRF、动态签名或 Authorization，但门户升级后要重新探测，不能把“未观察到”扩展成永久假设。

修改前探针脚本和脱敏结果只放被忽略的临时位置或系统临时目录；正式实现前必须由 owner 审核确认，之后才能进入 spec、共享 core、API catalog、APP 和正式验收 Case。
