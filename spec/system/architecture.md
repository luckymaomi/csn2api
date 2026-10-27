# 系统架构

## 产品与运行形态

csn2api 将已确认的生产系统 HTTP 能力封装为独立 APP、API 文档调试器和机器接口。浏览器负责输入和展示；生产请求由本地 Python 服务发送。它不代替目标系统登录，不实现验证码，也不借助浏览器自动化操作生产页面。

| 形态 | 入口 | 页面及后端 |
| --- | --- | --- |
| 静态站点 | 构建后的首页，或 `start_index.py` | 工具介绍、ZIP 下载、API 静态目录、开发文档下载；静态托管本身不执行生产请求 |
| 独立 APP | 解压单工具 ZIP，安装依赖并执行 `start.py` | 自带页面、库、Python 业务包、共享运行时和对应 protocol core，监听 loopback |
| 局域网工作站 | 根目录 `start_all.py` | 单一网关代理各独立子服务；各 APP 与 API 调试器仍有独立会话和状态 |

当前工具从 `src/tool/tools-data.ts` 发现；API 从 `public/tool/app/api-docs/catalog/index.json` 发现。`scripts/protocol-cores.json` 声明系统、core、模块及分发目标，构建与合同测试消费同一声明。项目运行不依赖 watchdog 或其他本地仓库。

## 依赖与职责

| 层 | 当前位置 | 变化原因与边界 |
| --- | --- | --- |
| 声明式 API 事实 | `public/tool/app/api-docs/catalog/` | URL、方法、字段、条件、动态来源、响应、读写风险与执行链变化 |
| 系统协议 | `public/tool/app/_shared/ieb_protocol/`、`oa_protocol/`、`soc_protocol/`、`caac_protocol/` | 请求构造、响应解析、身份归属、分页和会话失效变化 |
| 凭据文本解析 | `public/tool/app/_shared/credential_text/` | cURL 与 Header 文本的共同读取规则；系统凭据要求仍由各 core 定义 |
| APP 业务包 | `public/tool/app/<entry>/<package>/` | 输入、批次、状态、结果文件和本地路由变化；业务特判留在对应 APP 或领域 adapter |
| APP 页面 | `public/tool/app/<entry>/web/` | 人工步骤、状态、进度、表格与下载交互变化 |
| API 调试 | `public/tool/app/api-docs/api_docs/`、`app.mjs` 及配套模块 | 单次调试、系统会话、动态选项、结果投影与渐进快照变化 |
| 机器接口 | `public/tool/app/api-docs/universal_query/` | 从同一 catalog/executor 投影操作和安全结构化输出 |
| 运行时 | `public/tool/app/_shared/csn2api_runtime/` | 服务发现、loopback 启动、网关转发、使用提示与关闭变化 |
| 主题及保活展示 | `public/theme.*`、`public/tool/app/_shared/session_keepalive.mjs` | 共享展示变化；保活请求及失效判断仍由各系统维护 |
| 分发与文档生成 | `scripts/build.mts`、`runtime-delivery.mts`、`protocol-cores.mts`、`tool-exports.mts`、`documentation-export.mts` | 构建依赖闭包、单工具包、统一运行清单和合并文档变化 |

## 两条业务数据流

APP：凭据文本 → 本 APP 验证并建立 Session → 当前输入与动态元数据检查 → runner 执行 → 共享 protocol core 请求并校验结果 → manager 更新状态 → exporter/结果存储 → 页面与下载。`portal_client.py` 是 APP 适配层；批次线程、停止事件和下载登记由 manager 持有。不同 APP 的保存时机不同，必须按各自规格实现。

API：当前 catalog → 页面生成导航和参数 → API 本地 executor → 系统 adapter → 相同 protocol core → 摘要、动态表格及调试正文。万能查询复用同一 executor，只对外投影安全的摘要和表格，不输出 Cookie、原始正文或调试 headers。本地组合工作流显式标记，不能当作生产原生端点。

同一系统的 core 会在构建时封装进各独立交付目录。共享源码不意味着共享运行实例：每个 APP 与 API 调试器分别验证、持有和清除自己的 Cookie、Session 和保活；一个 APP 不需要另一个 APP 正在运行。

## 状态、失败与结果

普通业务批次按输入顺序串行，每次最终写请求最多一次。登录失效停止后续派发；普通行级失败通常记录并继续。训练安排等完整统计流程遇到表头、分页或状态契约异常时会停止最终导出，不能用一般规则覆盖领域特判。人工停止在当前请求结束后的业务边界生效。

局域网使用者 IP 是提示型状态，不能作为权限隔离：多人可以访问及操作同一子服务，任务和结果共享。接管不停止原任务，不清除会话。网关只负责已登记路径代理，不解释凭据、业务结果或生产规则。生命周期细节见[局域网规格](../dev/lan-runtime/spec.md)。

文件型工具使用应用本地结果目录；OA 已阅仅保存当前进程内状态。结果、真实凭据和原始响应不进入 Git、静态发布或 ZIP。模板与静态 catalog 可以发布；合并文档只读取可版本管理的文档和 catalog，不读取运行状态。
