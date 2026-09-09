# 万能查询开发规格

## 定位

万能查询是 API 文档本地服务的稳定机器接口，供机器人、CLI 和其他受控本地调用方发现当前已登记操作、载入系统凭据并取得统一结构化结果。它不是新的业务工作台、协议 core 或 Cookie 存储。

模块位于 `public/tool/app/api-docs/universal_query/`，直接复用同一 `ApiCatalog`、`ApiExecutor`、系统 adapter、内存会话和保活实例。Catalog 是操作、参数、默认值、固定项、自动生成项和读写风险的唯一事实源；万能查询不得维护静态操作名单或第二份系统请求定义。

## HTTP 契约

本地 API 文档服务以 `/api/universal-query/v1` 为前缀提供下列资源：

- `GET /health`：服务版本与已登记系统。
- `GET /sessions`：所有 Catalog 系统的脱敏会话状态。
- `POST /sessions/<systemId>`：请求体仅含 `credential`，通过现有系统验证链路载入 Cookie/cURL 并启动同一保活实例。
- `DELETE /sessions/<systemId>`：清除该系统的内存会话。
- `GET /operations` 和 `GET /operations/<operationId>`：从当前 Catalog 动态生成的操作与参数元数据。
- `POST /executions`：请求体为 `operation` 与 `parameters`，执行已登记操作。
- `GET /executions/<runId>`：读取渐进操作的当前快照。

操作描述包含模块、系统、`risk`、执行类型、是否渐进、参数清单及 `minimumInput`。参数的 `mode` 为 `input`、`fixed` 或 `automatic`；只有 `input` 参数可由调用方传入。Catalog 的非空默认值使必填输入变为可省略，服务在执行前补齐所有可调用方省略的默认参数；固定值和自动值继续由既有 adapter/protocol core 生成，不能被调用方覆盖。

普通执行返回 `ok`、操作、系统、风险、`state=completed` 与 `result`；渐进执行以 HTTP 202 返回 `runId` 和当前 `state`，后续从执行资源轮询。`result` 只含安全元信息、`summary` 和 `tables`，不会含请求 URL、原始响应正文、响应 headers 或 Cookie。错误使用 `{ "ok": false, "error": { "code", "message" } }` 的统一结构。

锁班的提交和通过是两个独立写操作。`lock-entry.submit` 返回待审批状态、冲突结果和实际使用的备注；`lock-entry.approve-pending` 以同一组员工、动态类型和日期时间业务字段查询全部待审批分页并唯一归属目标，不要求调用方传记录 ID。通过接口返回成功后，工作流继续回查已锁和待审批列表；只有目标已锁且不再待审批才返回 `outcome=通过成功`，否则执行失败。

## 读写边界

目录中的全部读写操作都出现在万能查询操作清单并使用同一个执行入口；`risk=write` 是调用方必须显式识别的风险标记，不建立只读版名单或并行接口。真实写入仍遵守仓库现有生产授权规则：执行前必须具有 owner 对当前对象与动作的当次明确授权。

## 凭据与交付

凭据仅作为会话载入请求体传入现有 adapter，默认仅存在当前本地进程内存。万能查询的会话、执行、错误与日志响应不得回显 Cookie、`Set-Cookie`、`Authorization` 或原始请求/响应内容。`examples/` 只保留不含真实凭据或业务数据的 JSON 模板。

构建整体复制 API 文档目录，因而模块、模板和本地服务随 API 文档既有独立运行与统一网关分发，不需要新增工具卡、页面或第二个启动入口。
