# API Catalog 编写规范

## 作用域

Catalog 使用四层结构记录当前已确认的接口事实：系统级 `session`、模块级 `requestDefinitions`、端点级 `execution` 和模块级 `relatedRequests`。同一个生产请求只定义一次，再由稳定引用表达它在不同上下文中的角色。

`requestDefinitions` 只保存不能直接由 endpoint 自身表达的生产 HTTP 请求。直接 HTTP endpoint 在执行步骤中用 `$endpoint` 引用自身；不得为它再复制一份请求定义。

## 系统会话

每个系统在 `catalog/index.json` 中声明验证和保活请求：

```json
"session": {
  "validationRequestRef": "module.session-check",
  "identityRequestRef": "module.identity",
  "keepAliveRequestRef": "module.session-check"
}
```

引用格式为 `<module-id>.<request-id>`，目标必须属于同一系统。验证和保活可以引用同一请求，也可以分别引用不同请求。

## 端点执行

每个 endpoint 必须有 `execution.kind` 和至少一个 step。`kind` 只能是 `direct-http` 或 `local-workflow`。

直接 HTTP endpoint 必须恰好包含一个自身主请求：

```json
"execution": {
  "kind": "direct-http",
  "steps": [
    { "id": "request", "requestRef": "$endpoint", "role": "primary", "cardinality": "once" }
  ]
}
```

有前置请求时按真实顺序登记。条件步骤必须说明 `condition`：

```json
{
  "id": "load-options",
  "requestRef": "module.options",
  "role": "prerequisite",
  "cardinality": "zero-or-one",
  "condition": "当前 Session 尚未缓存动态选项"
}
```

本地组合工作流不使用 `$endpoint`，而是引用实际生产请求。分页和逐项循环必须说明停止条件：

```json
{
  "id": "scan-pages",
  "requestRef": "module.page-query",
  "role": "page-loop",
  "cardinality": "one-or-more",
  "stopCondition": "达到服务端总数，或遇到空页、短页、无新增记录"
}
```

step `role` 只允许 `primary`、`prerequisite`、`page-loop`、`item-loop`、`postcondition`；`cardinality` 只允许 `once`、`zero-or-one`、`one-or-more`、`zero-or-more`。

## 模块相关请求

不会随当前 endpoint 自动执行，但需要保留的已确认请求放入 `relatedRequests`。关系只引用请求定义并补充上下文，不复制方法、路径和响应契约。

`kind` 只允许：

- `metadata`：分类树或模块元数据。
- `option-source`：动态选项来源，必须提供全局唯一 `sourceId`。
- `export`：生产系统原生导出。
- `reference-query`：相关查询或状态核对接口。
- `state-action`：相关状态动作，底层请求必须标记 `risk: write`。

没有相关请求时省略 `relatedRequests`，页面不显示空区域。

## 请求定义

每个 request definition 必须包含唯一 `id`、非空 `name`、`purpose`、`risk`、`method`、绝对 `path`、参数列表和非空 `response`。`risk` 只能是 `read` 或 `write`，`method` 只能是 `GET` 或 `POST`。

所有定义至少被系统会话、端点 execution 或模块 related request 使用一次。加载器拒绝悬空引用、跨系统引用、孤立定义、重复 step/source ID 和未知枚举。

## 响应与安全

`response.example` 只在已有脱敏事实时填写；没有示例时省略该字段，页面和 Markdown 同步隐藏示例区域。不得为了填满页面伪造业务数据。

Cookie、员工号、姓名、记录 ID、OA 标题、原始响应、截图和下载文件不得进入 catalog、模板或测试 fixture。生产 URL、方法、Headers、参数和响应条件必须来自已确认 reference 或真实只读验证；写操作需要 owner 对当次对象和动作另行授权。

## 新增检查

新增模块时使用 `catalog-module.template.json` 建立结构，并同步完成：目录加载测试、端点请求构造测试、页面与 Markdown 语义测试、开发规格和用户手册。测试保护引用、角色、顺序和可观察结果，不保护模块数组位置或私有 DOM 形状。
