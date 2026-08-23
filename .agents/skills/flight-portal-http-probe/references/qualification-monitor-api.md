# 资质监控按资质查询 HTTP 接口事实

本文件记录 IEB“资质监控 -> 按资质查询”的已验证只读请求契约。该模块同时提供分页 JSON 查询和门户原生 Excel 导出；两者的数据选择行为并不完全相同。

## 页面与会话

首页菜单加载业务页：

```text
GET https://ieb.csair.com/static/qualificationMonitorNew/searchByQualificationPage.html
```

该路径是静态页面，不能单独证明 Session 有效。会话验证继续按 [会话与探测方法](session-and-probing.md) 使用已确认的业务页标记；目标接口响应还必须排除 `/login`、`#scanLogin` 和非预期 HTML。

当前只需要 `JSESSIONID` 与 `iebJSid`。查询和导出复用同一个 `requests.Session`，不需要执行页面 JavaScript，当前未观察到 CSRF、`__VIEWSTATE`、动态签名或 Authorization。

## 分类树

```text
GET https://ieb.csair.com/newieb/qualification/alarm/new/queryQualificationTypeParent
```

响应为 JSON 数组。父项使用 `id`、`msgType`、`msgCode`，子项位于 `sonList`，按 `msgType` 展示名称、按 `msgCode` 作为 `qualType` 请求值。客户端应消费当前响应，不把 29 个子类数量当作永久常量；重复或缺失 `msgCode` 必须停止，不能覆盖同名文件。

当前已确认分类如下。

### 资质运行类 `ZZYX`

| 名称 | `msgCode` |
| --- | --- |
| 90天3起落 | `90D3F` |
| 新岗位120天100小时 | `120D100H` |
| 汉语4级 | `HY4` |
| 体检合格证 | `TJHG` |
| 复训 | `FX` |
| 熟练检查 | `SLJJ` |
| 执照有效期 | `ZZYY` |
| 危险品运输 | `WXPYS` |
| 机长年度 | `JZND` |
| 应急训练 | `YJXL` |
| 安保培训 | `ABPX` |
| 换季学习 | `HJXX` |
| 国际区域单飞 | `GJQYDF` |
| 国际区域英语通信 | `GJQYYYTX` |

### 资质资格类 `ZZZG`

| 名称 | `msgCode` |
| --- | --- |
| ICAO4级 | `ICAO4` |
| ICAO5级 | `ICAO5` |
| 汉语5级 | `HY5` |
| CAT二类/三类 | `CAT` |
| 无过站运行 | `WGZ` |
| 737NG/MAX资格 | `737NGMAX` |
| 特殊机场资格 | `TSJC` |
| EBT教员培训 | `EBTCAPT` |
| 型别教员TRI | `TRI` |
| A类飞行教员TRI更新检查 | `ATRI` |

### 资质特殊类 `ZZTS`

| 名称 | `msgCode` |
| --- | --- |
| 左座经历起落监控 | `ZZJLQL` |
| ILS PRM 进近 | `ILSPRM` |
| 汉语6级 | `HY6` |
| 检查员/委任代表 | `JCY` |
| 极地运行 | `JDYX` |

## 筛选选项

```text
GET https://ieb.csair.com/newieb/qualification/alarm/new/queryUserDataPower
GET https://ieb.csair.com/newieb/qualification/alarm/new/queryFleetCd
```

第一个响应提供 `primBaseList`、`baseList`、`fleetCdList`；第二个响应提供有效机型列表。状态选项由页面固定为：`3=失效`、`2=警告`、`1=注意`、`0=正常`。

## 分页查询

```text
GET https://ieb.csair.com/newieb/qualification/alarm/new/queryAlarmDetail
```

Query：

```text
qualType=<子类 msgCode>
staffNum=
alarmType=
primaryBase=
manyStaffNum=
manyAlarmType=
base=
fleetCd=
allClear=
effective=
effectiveModel=
pageNum=1
pageSize=20
```

页面默认每页 20 条，分页字段为 `pageNum`、`pageSize`。响应是 PageInfo JSON，对外至少确认 `list`、`total`、`pages`、`pageNum`、`pageSize`、`hasNextPage`；表格字段随 `qualType` 变化，公共字段包括员工号、姓名、状态、注册基地、运行基地和机队。空筛选值是“未筛选”，不是缺省业务值。

查询全部分页时严格串行；按 `total`、`pages` 和 `hasNextPage` 交叉收敛，任何页登录失效、JSON 契约变化或页码不前进都停止，不能无限重试。

## 门户原生导出

```text
GET https://ieb.csair.com/newieb/qualification/alarm/new/exportQualificationInfoExcel
```

Query 与分页查询使用相同筛选字段，但不传 `pageNum`、`pageSize`。门户页面通过 `postDownload` 封装以 GET 发送，`contentType=false`、`processData=false`；本地 HTTP 客户端直接使用结构化 Query 即可。

当前响应具有以下事实：

- HTTP 200 响应体是 OOXML ZIP，也就是 `.xlsx` 内容；门户页面虽然使用“资质表.xls”文件名，不能按扩展名或响应 `Content-Type` 判断格式。
- 响应应以 ZIP 魔数和必要 OOXML 部件验证；登录页、JSON 错误或缺少 workbook/worksheet 的响应不能保存为成功 Excel。
- 门户生成的 worksheet `dimension` 可能错误写成 `A1`，真实 `<row>` 仍完整存在。若只为下载，应原样保留字节；若用 openpyxl 检查，read-only 模式需要 `reset_dimensions()` 后再遍历。
- 当前 29 个子类均已返回可打开的 OOXML。27 个子类的原生导出数据行数与空筛选分页查询 `total` 一致。
- `GJQYDF` 与 `GJQYYYTX` 的原生导出排除 `allClear=Y` 的已解除警告记录；显式传 `allClear=Y` 仍只返回表头。这是门户原生导出行为，不是本地分页丢失。

当 owner 明确选择“门户原生导出”时，本地 APP 的“全部”指当前分类树中的全部子类分别调用该导出接口，不重建 Excel、不补入 `allClear=Y` 记录，也不声称与分页查询总数一致。一键导出必须保持串行，并把每个子类的原始 OOXML 作为独立文件交付；ZIP 打包属于本地组合工作流，不得写成门户生产接口。

## Headers 与安全边界

JSON XHR 使用：

```text
Accept: application/json, text/plain, */*
Referer: https://ieb.csair.com/index/index
X-Requested-With: XMLHttpRequest
```

原生导出可使用 `Accept: */*`，并保留同一 Referer 和 XHR 标记。所有请求都是只读；页面中的 `updateQualificationAlarmAllClearByIds` 等解除或恢复警告 POST 不属于本接口，不得因实现查询或导出而调用。

Cookie、原始 JSON、Excel、人员身份和探针输出不得进入 Git、fixture、日志或静态文件。APP 生成的原生文件只能位于已忽略结果目录或当前下载响应中，独立分发包不得包含历史结果。
