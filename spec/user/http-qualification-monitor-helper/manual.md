# 资质监控（皇帝版）用户手册

## 启动

下载独立应用并解压，在应用目录运行：

```powershell
pip install -r requirements.txt
python start.py
```

程序只监听本机 `127.0.0.1`，不启动 Playwright。

## 验证 Cookie

验证成功后，凭据区会显示该 Session 对应的“员工号 · 姓名”。身份只保存在当前页面和后端进程内存，会话失效时与 Cookie 同步清除。

在 Chrome 或 Edge 正常登录飞行门户，在 `F12` 的 `Network` 中选择任意已登录 `ieb.csair.com` 请求，右键选择 `Copy as cURL`。把完整内容或 Cookie Header 粘贴到工作台，点击“验证 Cookie”。

验证成功后输入框会清空，当前页凭据面板显示规范化 Cookie 并提供“复制凭据”。刷新页面不会清除本地 Python 进程内的 Session，但页面不会自动恢复明文 Cookie；服务关闭、主动清除或门户 Session 失效后需要重新导入或粘贴验证。点击“加载分类”后，页面显示资质运行类、资质资格类、资质特殊类及门户当前返回的全部子类。

## 导出

每个子类右侧的“导出”只获取该项的门户原生 Excel，成功后可单独下载。“一键导出全部”按页面分类顺序逐项串行请求；页面显示当前项目、完成数和各项状态。运行期间不会同时发送第二个导出请求。

“停止”不会强行中断已经发出的 HTTP 请求；当前项返回后不再派发下一项。普通单项失败会记录并继续后续项，登录失效会立即停止并清除当前会话。

只有本批全部子类成功时才提供完整 ZIP。ZIP 内按三大类分目录，每个子类是独立 `.xlsx`；部分失败或人工停止时不生成不完整 ZIP，已经成功的单项仍可分别下载。

文件是门户原生 OOXML 字节，本地工具不解析、修复或重写。门户当前对“国际区域单飞”和“国际区域英语通信”的原生导出会排除部分已解除警告记录，本工具保留该行为，不通过分页 JSON 补齐。

## 本地接口

Agent 可通过 `POST /api/start` 提交 `credentials`，一次完成验证、分类加载和全部导出；也可分阶段调用 `/api/session/verify`、`/api/metadata/load`、`/api/export/all`、`/api/export/one` 和 `/api/stop`。通过 `GET /api/status` 轮询状态，通过 `/api/download/<file-id>` 下载 manager 已登记的文件。
