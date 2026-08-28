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
/__runtime__/...          使用状态、接管、心跳和释放
```

## 提示型使用状态

所有客户端共享同一套子服务、任务状态和结果，但每个子服务拥有独立 Cookie、Session 和业务状态；网关不按 IP 隔离或拦截页面与 API。第一位进入运行入口的客户端 IP 取得提示型全局租约，同一 IP 可以跨工具使用；其他 IP 仍可访问和操作，并在注入状态条中看到当前使用者 IP 和“接管使用”。状态接口不得包含使用者业务身份、Cookie、结果、日志或下载内容。

owner 页面每 15 秒发送心跳。默认连续 3 分钟无活动且所有子服务均无任务运行时，下一位进入运行入口的访问者自动成为 owner；任务运行期间不因普通空闲超时换人。其他 IP 可以显式接管，接管只改变提示中的 owner，不停止正在运行的任务。显式“结束使用”只允许当前 owner 在无任务运行时执行，成功后返回工具首页。自动换人、接管和结束使用均不重启子服务，不清空 Cookie、任务状态或结果。

## Cookie 管理

API 文档只管理 API 文档进程内各系统的 Cookie；直接粘贴验证、JSON/TXT 导入和导出复用 API 文档自身的 `/api/session` 与 `/api/credentials` 合同。统一网关不解析、保存或分发 Cookie。

局域网工作台保留自己的 Cookie 输入、验证和复制控件，通过对应工作台的 `/api/session/verify` 在本进程内验证和保存凭据。不同工作台、API 文档和独立 APP 不共享 Cookie、Session 或 keepalive；同一份 Cookie 如需用于多个应用，必须在各应用分别显式验证。

## 生命周期

共享运行时按职责拆分：`application.py` 发现并创建单 APP server，`single_app.py` 管理独立入口，`supervisor.py` 管理全部子服务与 busy 状态，`lease.py` 管理租约，`gateway.py` 负责静态/前缀代理和运行时 API，`lan_assets.py` 提供注入状态条。业务 manager、Cookie 规则、请求契约和 Excel 不进入共享运行时。

任一子服务启动失败时回滚已经启动的服务；网关绑定失败、Ctrl+C、显式关闭或异常收口时关闭全部 manager/executor、HTTP server 和线程。构建、测试和 agent 临时验证不得遗留监听端口。

统一入口连通性门禁读取 `runtime-tools.json`，遍历首页、API 文档和全部登记工作台，从各页面 HTML 动态发现本地样式、脚本和图片，并递归请求 ES module 依赖；任何资源非 `200`、内容为空或越出统一网关均视为失败。系统特有业务合同继续由各工具专属测试保护。

独立 ZIP 生命周期门禁同样读取 `runtime-tools.json`，逐个解压到临时目录并通过包内共享启动器启动。Windows 与 Linux 下均不得依赖解压目录具有固定深度；每个入口必须输出 loopback 地址、返回 HTML、响应中断、正常退出并释放端口。启动失败时测试报告完整子进程输出和退出码。
