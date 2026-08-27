# 资质监控（皇帝版）开发规格

## 产品边界

本工具是独立的本地 HTTP APP，只读访问 IEB“资质监控 -> 按资质查询”。用户提供已登录 Cookie Header 或 Copy as cURL；Cookie 只保存在 Python 进程内存中，验证成功响应一次性返回规范化 Cookie Header 供当前页复制，状态响应不返回 Cookie。服务只监听 `127.0.0.1`，不使用 Playwright，不调用解除或恢复警告接口。

APP 与 API 文档共用 `ieb_protocol` 中的资质监控 core。分类树、动态子类、筛选参数、分页契约、OOXML 校验、身份和会话失效由 core 维护；APP 只增加全量串行导出、文件保存、ZIP、进度、停止边界和保活状态。

## 核心工作流

凭据验证只读请求 `GET /index/index`。员工号来自 `.detailInfo .empid span[title]`，姓名来自 `#personalInfo .name-txt`；身份缺失时验证失败。页面显示“员工号 · 姓名”，身份只保存在内存 Session，会话失效时与 Cookie 同步清除。

用户完成凭据验证后，通过独立“加载分类”动作读取分类树。客户端只接受资质运行类 `ZZYX`、资质资格类 `ZZZG`、资质特殊类 `ZZTS`，子类按门户响应动态读取；缺失父类、意外父类、重复代码或缺少名称时停止。未加载分类时不能执行批次或单项导出。

常规资质导出调用门户原生 `GET /newieb/qualification/alarm/new/exportQualificationInfoExcel`，请求保留页面的全部空筛选参数且不携带分页字段。JCY 调用检查员库独立的 `GET /newieb/zhftcCheckerInfo/exportZhftcCheckerInfoExcel`，使用检查员库筛选参数且不发送 `qualType`。两类响应都通过 ZIP 魔数、OOXML 必要部件和 worksheet 校验后原样保存，不用 Excel 库解析、修复或重写；检查员库导出受页面管理权限控制，失败时按单项失败处理。

一键全部按分类树顺序严格串行。普通失败记录后继续；登录失效立即停止并清除凭据；人工停止只在当前请求返回后的子类边界生效。只有全部子类成功才生成完整 ZIP，ZIP 按三类分目录且每个子类保留独立 `.xlsx`。成功单项始终可独立下载。

## 本地接口

- `POST /api/session/verify`：验证 Cookie 和当前登录人，成功响应一次性返回规范化 Cookie Header。
- `POST /api/metadata/load`：读取当前动态资质分类。
- `POST /api/export/all`：启动全部子类串行导出。
- `POST /api/export/one`：启动已加载子类的单项导出。
- `POST /api/stop`：请求在当前请求返回后停止。
- `POST /api/start`：验证凭据并启动全部导出。
- `GET /api/status`：返回脱敏状态、进度和下载 ID。
- `GET /api/download/<file-id>`：只下载 manager 登记的结果文件。

验证成功后，APP 内独立保活线程每 30-60 秒读取当前登录页检查会话，不在后台加载资质分类；保活与分类加载、资质 Excel 导出共用请求锁但职责分离，会话失效时停止后续导出。前端保活展示模块采用可降级动态加载；模块加载失败时显示明确警告，但不得阻断凭据验证和导出按钮的核心通信。

门户原生导出对 `GJQYDF`、`GJQYYYTX` 排除部分已解除警告记录，本工具保留这一门户行为，不用分页 JSON 补齐或重建 Excel。
