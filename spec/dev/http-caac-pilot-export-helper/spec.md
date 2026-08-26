# CAAC 飞行员全量信息导出开发规格

## 产品边界

`http-caac-pilot-export-helper` 是独立本地 Python APP，只读访问 `fsop.caac.gov.cn` 人员管理接口。它不创建、修改、删除人员，不使用 Playwright，不与 IEB、OA 或 SOC 共享 Cookie。凭据只存在当前 Python 进程内存，结果 Excel 写入 APP 的本地 `results/<runId>/`，该目录被 Git 忽略。

## 已验证接口

- `POST /yzzzm/rygl/queryPilotByParamForPage?ajaxPrefilter=<timestamp>`：表单包含筛选空值、`medicalStatus`、`page`、`rows`、`sort=archiveNo`、`order=asc`；响应为 `{total, rows}`。
- `POST /yzzzm/rygl/queryPilotDetails`：表单 `pilotId`；响应顶层对象的 `pilotId` 必须与请求一致。
- 当前真实验证列表返回过动态 `total`、`rows=10`；人数和页数只作为运行时事实，绝不写死。
- 指定样例人员筛选返回唯一列表记录；列表与详情的姓名、英文名、证件号、档案号、国籍和手机一致。
- 详情包括基础标量、文件 URL、递归 `layerInfosList`，以及学习简历、工作经历、机长航线、应急生存、熟练检查和正式执照打印记录等数组；字段按实际响应动态并集。
- 已使用真实详情 JSP 确认页面 1-24 区块及检查航段、检查状态、训练地点、考试员、打印人、同意日期等中文表头。页面标签用于翻译，不用于过滤接口字段。

## 执行规则

1. 解析 `yzzzm`、`JSESSIONID`、`home`，还原 Bash `$'...'` 中的 `\\u0021` 和 `\\_`，不执行 cURL 文本。
2. 验证时请求第 1 页，确认 JSON、`total` 和 `rows` 契约；验证成功后启动 30-60 秒随机间隔只读保活。
3. 按 `total`、实际行数和唯一 `pilotId` 动态分页；空页、重复 ID、total 变化或缺 ID 属于契约错误，停止当前批次。
4. 详情严格串行，每个 `pilotId` 最多请求一次。普通 HTTP、解析或业务异常标记该行失败并继续；登录失效停止后续详情。
5. Excel 只有一个 Sheet。每完成一名人员就把该行和运行中首次出现的新列原子保存到检查点工作簿；进程异常时保留最后一次完整保存。列表和详情的同义字段合并为中文业务列，详情值优先；已确认数组按中文字段生成单元格内的逐条换行文本，`layerInfosList` 保留层级缩进。
6. 详情 response 的文件 URL、数组内部 ID、创建/更新审计字段、状态码和页面未展示字段全部保留并中文化；工具不请求文件 URL。未建立中文映射的动态字段以 `未映射字段（rawKey）` 保留，避免字段变化导致数据静默丢失。
7. 字段字典独立维护在 `field_mappings.py`，`flatten.py` 只负责值归一、日期转换、层级和单元格文本格式化。

## 当前范围

当前授权会话在 `medicalStatus` 为空或 `0` 时均返回 `total=124040`。该数量与 owner 既有样例不一致；机构筛选条件确认前不得发起真实全量任务。

## UI 资源

主站入口与独立工作台均加载 Bootstrap 和公共主题。独立服务在分发包中读取随包资源，在源码运行时回落到仓库 `public/`；页面引用的本地 CSS/JS 必须通过实际 HTTP 资源测试。

## 当前登录人

已检查当前 CAAC 入口页和已确认 JSON，未发现稳定可归属的当前登录人字段。APP 和 API 文档显示“未从 CAAC 已确认接口识别”，不从 Cookie、人员列表或浏览器账号猜测姓名。

## 错误边界

普通单人异常继续；登录页重定向、响应契约变化、列表不前进、重复或归属不唯一停止；不自动重试、不并发。
