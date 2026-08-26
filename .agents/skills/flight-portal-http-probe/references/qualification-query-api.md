# 技术等级与运行资格 HTTP 接口事实

本文件记录 IEB 技术资料只读查询的已验证请求契约。维护 `http-qualification-query-helper` 时，业务输入、输出和阶段口径另读对应 APP spec。

## 会话验证

```text
GET https://ieb.csair.com/newieb/basics/showEmpprofileCompositeListPageNew
Query: random=<防缓存值>
有效标记: #showEmpProfileCompositeListPageForm
```

最终 URL 进入 `/login`，或响应出现 `#scanLogin`、登录表单时，当前 Session 已失效。HTTP 200 本身不是有效登录证据。

## 按员工号检索

```text
GET https://ieb.csair.com/newieb/basics/showEmpProfileCompositeResult
```

Query：

```text
personName=<六位员工号>
staffNumAllDesc=
primaryBaseArray=
baseArray=
techBase=
fleetCdToArray=
bolMultiQualCd=
bolPriBase=
bolJCY=
activeStatusArray=ZAIZHI
activeStatusArray=WAIBU
fleetCdbranch=
isOperQual=Y
operQualArray=
page=1
currentStr=<毫秒时间戳>
```

`activeStatusArray` 必须用 tuple 列表或等价的重复参数结构保留。使用普通字典只会保留最后一个值，已验证会造成查询结果变化。响应为 HTML table，不能依赖固定包装 class；应按动态表头读取并按员工号唯一归属。姓名由员工号同行取得，输入姓名非空时再核对。真实姓名单元格内含有标题为“查看作风纪律资料”的链接，该 `title` 是操作提示，姓名必须读取单元格可见文本，不能把任意交互控件的 `title` 当作业务值。

## 技术资料组合筛选

组合筛选与按员工号检索使用同一个 `GET /newieb/basics/showEmpProfileCompositeResult`。当前已验证的“直飞机型 + 全部人员状态 + 具备所选运行资格”请求形状为：

```text
personName=
staffNumAllDesc=
primaryBaseArray=
baseArray=
techBase=
fleetCdToArray=<直飞机型代码，例如 777>
bolMultiQualCd=
bolPriBase=
bolJCY=
activeStatusArray=ZAIZHI
activeStatusArray=WAIBU
activeStatusArray=TUIXIU
activeStatusArray=LIZHI
fleetCdbranch=
isOperQual=Y
operQualArray=<一个或多个资格代码，英文逗号分隔>
page=1
currentStr=<毫秒时间戳>
```

四个人员状态分别是“在职、外部、退休、离职”，必须作为四个重复 Query 参数发送。“全部”不是单独代码。`fleetCdToArray` 来自页面当前多选项，不能把已观察到的机型清单写死。

结果当前每页 20 条，分页 HTML 通过“共 N 条记录”和 `goPageTwo(...)` 提供总数与后续页；总数和页数是动态业务结果。当前结果表为 17 列：`#`、员工号、姓名、技术基地、注册基地、运行基地、技术信息、实际机型、保护等级、性别、在职状态、出生日期、国籍、政治面貌、所属部门、行政职务、行政级别。客户端应按实际表头解析，不固定记录数或页数。

## 运行资格动态选项

运行资格选择器由页面动态加载，不是静态字典：

```text
POST https://ieb.csair.com/newieb/basics/showChooseOperQualificationDialog
GET  https://ieb.csair.com/newieb/basics/showChooseOperQualificationList
Query: qualCd=<资格代码筛选>&chnDesc=<中文描述筛选>
```

列表表头为：选择、资格代码、中文描述、资格简码、资格类型、类型描述。2026-08-26 的真实空筛选响应一次返回 147 条、147 个唯一资格代码和 13 个资格类型；这些数量只能作为验证快照，客户端必须消费当前响应。

复选框 `value` 是内部记录 ID，不是查询值。页面确认函数从勾选行的 `.qualCdTd[data-qualCd]` 读取资格代码，以英文逗号连接后写入 `operQualArray`。多个资格代码的查询语义已验证为 OR，即人员具备任一所选资格即可命中。当前已确认 `RAMA` 表示“北美区域单飞资格”，类型代码为 `QYHXZG`，类型描述为“区域航线资格”。

## 技术资料页面导出

页面提供四个 GET 导出入口，均把当前表单序列化为 Query 后打开下载：

| 页面按钮 | Path | 数据层级 |
| --- | --- | --- |
| 导出 | `/newieb/basics/createEmpProfileCompositeExcel` | 当前组合筛选命中的人员清单 |
| 技术等级导出 | `/newieb/basics/createEmpProfileCompositeJSDJExcel` | 技术等级明细 |
| 运行资格导出 | `/newieb/basics/createEmpProfileCompositeYXZGExcel` | 运行资格明细 |
| 航校信息导出 | `/newieb/basics/createEmpProfileSupplementaryExcel` | 航校补充信息 |

需要导出当前筛选人员时使用第一个普通“导出”，不能用技术等级或运行资格明细行数代替人员数。技术等级导出和运行资格导出当前有前端校验，要求直飞机型与运行基地同时填写；该限制不属于第一个普通导出。

普通导出必须复刻浏览器表单的参数存在性，不要给未选中的多选字段补空参数。真实验证中额外发送不存在于查询 cURL 的 `qualTypeArray=` 会使导出只剩表头；删除该参数并使用与查询一致的 Query 后，导出数据行数与查询总数一致。

普通导出的响应有以下已验证特征：

- HTTP 200，`Content-Disposition` 文件名后缀为 `.xls`，响应体实际是 OOXML ZIP；`Content-Type` 当前为 `multipart/form-data;charset=utf-8`，不能依赖文件名或 Content-Type 判断格式。
- Sheet 名为 `Sheet0`，当前 21 列：员工号、姓名、技术基地、注册基地、运行基地、技术信息、实际机型、保护等级、运行资格、总经历数时间、总起落数、检查员资格、性别、在职状态、分部、出生日期、国籍、政治面貌、所属部门、行政职务、行政级别。
- worksheet `dimension` 当前错误写为 `A1`，真实 `<row>` 仍完整存在。直接下载时保留原始字节；需要解析时使用能读取真实行节点的模式，或在 openpyxl read-only 模式下先 `reset_dimensions()`，不能用未修正的 `max_row` 判断空文件。
- 成功判定至少同时检查非登录响应、OOXML ZIP 魔数、必要 workbook/worksheet 部件、表头和动态数据行数；HTTP 200 或附件文件名不能单独证明导出成功。

## 技术等级

```text
POST https://ieb.csair.com/newieb/basics/qualList
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

Form：

```text
staffNum=<六位员工号>
currentStr=<毫秒时间戳>
```

结果区域为 `#qualList`。区域内第一个 table 是 9 列表头，第二个 table 是数据：`#`、技术等级代码、技术等级、水平等级、机型、生效时间、失效时间、对应检查记录、数据来源。

## 运行资格

```text
POST https://ieb.csair.com/newieb/basics/showSingleEmpOperQualListByempIdNew
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

Form：

```text
empid=<六位员工号>
currentStr=<毫秒时间戳>
```

已确认 `empid` 使用员工号，不是页面内部 ID。结果区域为 `#showSingleEmpOperQualList`。区域内第一个 table 是 8 列表头，第二个 table 是数据：类型、运行资格代码、运行资格、水平等级、机型、生效时间、失效时间、备注。

运行资格存在 `rowspan` 和 `colspan`，必须展开为规则网格；单元格有 `title` 时优先读取完整值。每行展开后的宽度必须与表头一致，不能静默截断或错位。

## Headers 与页面依赖

XHR 公共 Header：

```text
Accept: text/html, */*; q=0.01
Referer: https://ieb.csair.com/index/index
X-Requested-With: XMLHttpRequest
```

POST 另使用同源 `Origin` 和表单 Content-Type。当前真实请求未观察到 CSRF Token、动态签名、`__VIEWSTATE` 或 Authorization；三个查询请求可以在验证后的同一 `requests.Session` 中直接完成，不需要执行页面 JavaScript。门户升级后若契约异常，应重新录制 Network，而不是增加旧值兜底。
