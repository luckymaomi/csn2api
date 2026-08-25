# CAAC 飞行员全量信息导出开发规格

## 产品边界

`http-caac-pilot-export-helper` 是独立本地 Python APP，只读访问 `fsop.caac.gov.cn` 人员管理接口。它不创建、修改、删除人员，不使用 Playwright，不与 IEB、OA 或 SOC 共享 Cookie。凭据只存在当前 Python 进程内存，结果 Excel 写入 APP 的本地 `results/<runId>/`，该目录被 Git 忽略。

## 已验证接口

- `POST /yzzzm/rygl/queryPilotByParamForPage?ajaxPrefilter=<timestamp>`：表单包含筛选空值、`medicalStatus`、`page`、`rows`、`sort=archiveNo`、`order=asc`；响应为 `{total, rows}`。
- `POST /yzzzm/rygl/queryPilotDetails`：表单 `pilotId`；响应顶层对象的 `pilotId` 必须与请求一致。
- 当前真实验证列表返回过动态 `total`、`rows=10`；人数和页数只作为运行时事实，绝不写死。
- 指定样例人员筛选返回唯一列表记录；列表与详情的姓名、英文名、证件号、档案号、国籍和手机一致。
- 详情包括基础标量、`pilotPhotoFileUrl`、递归 `layerInfosList`，以及教育、工作、经历、检查和打印记录等数组；字段按实际响应动态并集。

## 执行规则

1. 解析 `yzzzm`、`JSESSIONID`、`home`，还原 Bash `$'...'` 中的 `\\u0021` 和 `\\_`，不执行 cURL 文本。
2. 验证时请求第 1 页，确认 JSON、`total` 和 `rows` 契约；验证成功后启动 30-60 秒随机间隔只读保活。
3. 按 `total`、实际行数和唯一 `pilotId` 动态分页；空页、重复 ID、total 变化或缺 ID 属于契约错误，停止当前批次。
4. 详情严格串行，每个 `pilotId` 最多请求一次。普通 HTTP、解析或业务异常标记该行失败并继续；登录失效停止后续详情。工具不请求照片文件，`pilotPhotoFileUrl` 只作为详情文本字段保留。
5. Excel 只有一个 Sheet。每完成一名人员就把该行和运行中首次出现的新列原子保存到检查点工作簿；进程异常时保留最后一次完整保存。列表标量和详情标量各自带 `列表.`/`详情.` 前缀；数组记录压入同一单元格的纵向换行文本；`layerInfosList` 保留层级缩进。

## 当前登录人

已检查当前 CAAC 入口页和已确认 JSON，未发现稳定可归属的当前登录人字段。APP 和 API 文档显示“未从 CAAC 已确认接口识别”，不从 Cookie、人员列表或浏览器账号猜测姓名。

## 错误边界

普通单人异常继续；登录页重定向、响应契约变化、列表不前进、重复或归属不唯一停止；不自动重试、不并发。
