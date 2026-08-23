# 资质监控（皇帝版）开发规格

## 产品边界

本工具是独立的本地 HTTP APP，只读访问 IEB“资质监控 -> 按资质查询”。用户提供已登录 Cookie Header 或 Copy as cURL；Cookie 只保存在 Python 进程内存中。服务只监听 `127.0.0.1`，不使用 Playwright，不调用解除或恢复警告接口。

## 核心工作流

凭据验证通过分类树接口完成。客户端只接受资质运行类 `ZZYX`、资质资格类 `ZZZG`、资质特殊类 `ZZTS`，子类按门户响应动态读取；缺失父类、意外父类、重复代码或缺少名称时停止。

单项与全部导出均调用门户原生 `GET /newieb/qualification/alarm/new/exportQualificationInfoExcel`。请求保留页面的全部空筛选参数且不携带分页字段。响应通过 ZIP 魔数、OOXML 必要部件和 worksheet 校验后原样保存，不用 Excel 库解析、修复或重写。

一键全部按分类树顺序严格串行。普通失败记录后继续；登录失效立即停止并清除凭据；人工停止只在当前请求返回后的子类边界生效。只有全部子类成功才生成完整 ZIP，ZIP 按三类分目录且每个子类保留独立 `.xlsx`。成功单项始终可独立下载。

## 本地接口

- `POST /api/session/verify`：验证 Cookie 并加载分类。
- `POST /api/export/all`：启动全部子类串行导出。
- `POST /api/export/one`：启动已加载子类的单项导出。
- `POST /api/stop`：请求在当前请求返回后停止。
- `POST /api/start`：验证凭据并启动全部导出。
- `GET /api/status`：返回脱敏状态、进度和下载 ID。
- `GET /api/download/<file-id>`：只下载 manager 登记的结果文件。

门户原生导出对 `GJQYDF`、`GJQYYYTX` 排除部分已解除警告记录，本工具保留这一门户行为，不用分页 JSON 补齐或重建 Excel。
