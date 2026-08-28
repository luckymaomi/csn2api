# 局域网统一运行开发规格

## 入口与发现

根目录 `start_all.py` 是全部前后端工具的局域网统一入口，默认监听 `0.0.0.0:4567`。它先执行生产构建，再读取由 `src/tool/tools-data.ts` 和 `scripts/protocol-cores.json` 生成的 `dist/runtime-tools.json`，动态启动当前登记的全部 HTTP 工作台和 API 文档；新增工具不维护第二份 Python 名单。

统一网关是唯一对局域网暴露的服务。每个工作台和 API 文档仍由自己的 `create_server()` 在 `127.0.0.1` 随机端口运行，保持独立 manager、executor、Session、protocol core 和业务状态。网关只剥离已登记路径前缀并代理 HTTP，不解释业务请求或响应。

路径合同：

```text
/                         临时跳转到规范首页 `/tool/`
/tool/                    首页及其相对静态资源基址
/apps/<entry>/            当前登记的独立工作台
/api-docs/                API 文档与本地调试器
/__runtime__/...          占用、心跳、Cookie 文件和释放
```

## 单人占用

首页和静态资源允许多人查看。第一位进入运行入口的客户端 IP 取得全局租约，同一 IP 可以跨工具使用；其他 IP 访问工作台 HTML 时得到含当前使用者 IP 的友好 `423 Locked` 页面，访问 API 时得到包含 `ownerIp` 的 JSON `423`。响应不得包含使用者业务身份、Cookie、结果、日志或下载内容。

页面每 15 秒发送心跳。默认连续 3 分钟无活动且所有子服务均无任务运行时，下一位访问者可以接管；接管前重启全部子服务，清空上一位用户的内存 Session。显式“结束使用”只在无任务运行时成功，并同样重启全部子服务。任务运行期间不因普通空闲超时释放。

## Cookie 文件

API 文档的 `/api/credentials` 是 Cookie 包导入、导出的实现入口，格式和验证行为由 API 文档 spec 定义。统一网关复用该端点，不另写 Cookie parser；导入成功后依据 `runtime-tools.json` 的 `systemId` 把规范化 Cookie 发送到同系统工作台现有 `/api/session/verify`，每个工作台仍执行自己的真实验证。导入失败按系统或工作台返回，不伪装为成功。

## 生命周期

共享运行时按职责拆分：`application.py` 发现并创建单 APP server，`single_app.py` 管理独立入口，`supervisor.py` 管理全部子服务与 busy 状态，`lease.py` 管理租约，`gateway.py` 负责静态/前缀代理和运行时 API，`lan_assets.py` 提供注入状态条。业务 manager、Cookie 规则、请求契约和 Excel 不进入共享运行时。

任一子服务启动失败时回滚已经启动的服务；网关绑定失败、Ctrl+C、显式关闭或异常收口时关闭全部 manager/executor、HTTP server 和线程。构建、测试和 agent 临时验证不得遗留监听端口。

统一入口连通性门禁读取 `runtime-tools.json`，遍历首页、API 文档和全部登记工作台，从各页面 HTML 动态发现本地样式、脚本和图片，并递归请求 ES module 依赖；任何资源非 `200`、内容为空或越出统一网关均视为失败。系统特有业务合同继续由各工具专属测试保护。
