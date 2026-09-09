# 万能查询接口

万能查询用于把当前 API 文档目录里的业务能力交给机器人、CLI 或其他本机程序调用。它与 API 文档页面共享同一份系统会话和保活状态；不需要为飞行门户、OA、SOC 或 CAAC 再维护一套 Cookie 和请求逻辑。

本地独立 API 文档启动后，接口前缀为 `http://127.0.0.1:<端口>/api/universal-query/v1`。通过统一网关访问时，在此前缀前增加 `/api-docs`。

先调用 `GET /operations`。每个操作的 `minimumInput` 就是最少需要向用户询问的参数；`parameters` 中 `mode=input` 的字段可以填写，`mode=fixed` 和 `mode=automatic` 由服务负责。参数有 `default` 时可省略，`risk` 为 `write` 表示动作会改变生产数据。

需要读取门户动态选项时调用 `GET /options/<sourceId>`，例如锁班类型使用 `GET /options/lock-types`。该响应只返回当前选项的业务字段（代码、名称和门户要求的派生标识），不返回 Cookie、请求 URL 或原始响应正文。

向 `POST /sessions/<systemId>` 提交以下 JSON 验证系统凭据。支持完整 Cookie Header 或浏览器 Network 复制的 Copy as cURL；凭据不会在万能查询响应中回显。

```json
{
  "credential": "Cookie: <当前系统凭据>"
}
```

验证成功后，向 `POST /executions` 提交操作和输入参数：

```json
{
  "operation": "flight-stats.query",
  "parameters": {
    "staffNum": "<员工号>",
    "startStr": "<YYYY-MM-DD>",
    "endStr": "<YYYY-MM-DD>"
  }
}
```

普通查询立即返回 `state=completed`、摘要和表格。渐进操作返回 HTTP 202、`runId` 和 `state=running`；使用 `GET /executions/<runId>` 读取最新进度。会话状态通过 `GET /sessions` 查看，完成后可用 `DELETE /sessions/<systemId>` 清除。

锁班需要顺序执行两个写操作。先调用 `lock-entry.submit`，只有返回 `outcome=提交成功` 且 `lockStatuses=["待审批"]` 才进入下一步；存在冲突时停止。再以相同员工、类型和日期时间调用 `lock-entry.approve-pending`，并把第一步返回的 `remark` 作为备注传入。第二步只有在服务回查目标已锁且不再待审批后才返回 `outcome=通过成功` 和 `lockStatuses=["已锁"]`。调用方不需要也不能猜测门户记录 ID。

万能查询不返回底层请求 URL、原始响应、调试 headers 或 Cookie；业务查询结果保留在 `result.summary` 和 `result.tables`。生产写操作也会出现在操作清单中，但应只在已获得当前对象和动作授权时调用。
