# API 文档请求角色与真实执行链路统一 Plan

## 1. 需求文档

API 文档当前把会话验证、端点真实执行步骤、分页循环、选项请求、导出请求和其他相关状态动作都放在模块级 `internalRequests` 中，再把整组内容显示到该模块的每个端点。使用者因此无法从页面判断某个请求究竟会不会在点击“发送请求”后执行，也会看到技术等级等模块没有“内部请求链路”、锁班和资质监控却出现大量与当前端点无关的请求。

本任务要统一 API catalog 的编写口径，使每一个请求只按真实角色登记：

- 系统级会话请求：载入 Cookie 时的验证请求和后台保活请求。
- 端点级执行步骤：点击当前端点后，本地执行器实际调用的生产请求、顺序、次数和条件。
- 模块级相关请求：已确认但不会随当前端点执行的元数据、选项、导出、相关查询和状态动作。
- 端点自身请求：直接 HTTP 端点以自身方法、路径、Headers 和参数作为主请求，不再复制一份“内部请求”。

统一后的用户路径是：进入 Cookie 管理可看到当前系统真实的验证和保活请求；进入任意端点都能看到该端点自己的真实执行链路；进入模块概览只看到该模块已确认的相关请求。页面不显示空标题、空请求卡片或作者规范，也不把“相关请求”描述成会实际执行的步骤。

后续新增系统或模块时，作者按同一份 catalog v2 模板填写请求定义、系统会话引用、端点执行步骤和模块相关请求；Python 加载器在启动时验证引用、角色和基数，浏览器页面、Python 执行器与 Markdown 从同一结构读取，不再靠文案约定区分。

完成标准：五个现有模块和两个系统一次性迁移；共 38 个端点均有可解析的执行契约；当前生产 URL、方法、参数、响应解析、Cookie 生命周期和写操作边界不变；旧 `internalRequests`、`validationRequestId` 和散落的 `executionKind` 不再存在；自动测试只保护真实请求选择与调用顺序，不保护 catalog 数组位置或临时 DOM 字符串。

## 2. 当前事实

- owner 已明确本轮不新增负向测试；测试只保护核心请求选择、调用顺序、解析结果和用户可观察的作用域语义。

### 2.1 Catalog 与页面

- `public/tool/app/api-docs/catalog/index.json` 和五个模块文件当前均为 `schemaVersion: 1`。
- catalog 展开默认值后共有 38 个端点：飞行经历 1 个、非生产任务锁班 1 个、飞行人员信息 5 个、OA 2 个、资质监控 29 个。
- 当前 schema v2 共有 19 个 request definition；系统会话、端点执行和模块相关关系均通过稳定引用消费，不再存在 `internalRequests`。
- `catalog-view.mjs` 的 `internalRequestList(module)` 在每个端点末尾遍历整个模块的 `internalRequests`；所以同一列表会在同模块每个端点重复，空数组仍会留下“内部请求链路”标题。
- `markdown-export.mjs` 同样按模块把整组 `internalRequests` 输出为“内部请求链路”，无法表示端点之间不同的执行顺序。
- Cookie 页面通过系统的 `validationRequestId` 回到某个模块的 `internalRequests` 查找验证请求；当前结构没有独立保活引用，只能依赖执行器实现知道验证与保活是否相同。
- `catalog.py` 只校验 endpoint 与 `internalRequests` 的基本方法和路径，不校验一个内部请求是否由会话、端点执行或模块说明使用，也不检查孤立请求和跨层引用。
- 38 个端点均有响应格式、状态定义和状态说明。飞行人员信息 5 个端点没有脱敏响应示例，页面不输出空示例框；脱敏示例不能为了视觉一致而虚构。

### 2.2 真实运行链路

以下事实来自当前 catalog、`FlightPortalAdapter`、`OaAdapter`、解析器和现有测试，不是根据页面标题推测：

| 范围 | 当前真实请求链路 |
| --- | --- |
| IEB 会话载入 | 调用 `flight-stats.query-page` 验证 Cookie；后台保活在 30-60 秒动态间隔后重复调用同一请求 |
| OA 会话载入 | 调用 `oa-read.user-info` 验证 Cookie；后台保活在 30-60 秒动态间隔后重复调用同一请求 |
| 飞行经历查询 | 当前 endpoint 自身 GET 一次 |
| 锁班提交 | 锁班类型未缓存时调用 `lock-entry.entry-page`；调用 `lock-entry.employee-validation` 一次；当前 endpoint 自身 POST 一次 |
| 飞行人员信息 5 个端点 | 每个端点只调用自身生产请求一次 |
| 资质监控 29 个端点 | 每个端点只调用自身 `queryAlarmDetail` GET 一次 |
| OA 数量 | 循环调用 `oa-read.waiting-query`，直到总数、空页、短页或无新增记录使分页收敛 |
| OA 已阅 | 先执行相同待办分页循环，再对本次目标逐条调用 `oa-read.have-read`；单条失败后停止 |

因此，“飞行人员信息没有内部请求”不代表它没有执行请求，而是它的生产请求已经由 endpoint 自身定义；“资质监控有 4 个内部请求”也不代表查询一个子类会调用分类树、权限、机型和原生导出。

### 2.3 当前请求的实际角色

- `flight-stats.query` 与飞行经历 endpoint 自身重复，应删除副本；`flight-stats.query-page` 只承担 IEB 会话验证和保活。
- `lock-entry.submit` 与锁班 endpoint 自身重复，应删除副本。
- `lock-entry.entry-page` 是锁班提交的条件前置请求，也是 `lock-types` 动态选项来源。
- `lock-entry.employee-validation` 是锁班提交的必经前置请求。
- 锁班的额度、查询页、分页查询、通过、撤销、解锁和否决不会由当前单次提交 endpoint 执行，只是模块相关请求；其中通过、撤销、解锁和否决仍是生产写操作。
- OA 的 `user-info` 只属于系统会话；`waiting-query` 和 `have-read` 分别属于端点分页循环和逐项循环。
- 资质监控的分类树、数据权限、有效机型和原生导出不会由 29 个分页查询 endpoint 执行，只是元数据、选项和导出相关请求。
- 飞行人员信息没有额外生产请求定义；五个 endpoint 的真实执行链路都应显示 endpoint 自身。

### 2.4 当前实现耦合

- Python 执行器通过 `get_internal_request("<module>.<request>")` 硬编码取得 IEB 验证、IEB 保活、锁班类型、员工校验、OA 验证、OA 分页和 OA 已阅请求。
- `FlightPortalAdapter.load_options()` 另行硬编码 `lock-types -> lock-entry.entry-page`，catalog 的 `optionSource` 与真实请求之间没有可验证引用。
- OA 的本地组合工作流由专用 Python 代码实现；catalog 记录了请求事实，但当前无法自动证明页面所写顺序与代码实际取用的请求一致。
- 当前测试直接断言 `internalRequests` 的集合和前端源码包含某段 HTML，保护的是旧结构或实现形状，不足以保护请求角色、引用解析和真实顺序。

### 2.5 本轮验证边界

- 已完成 catalog v2、身份显示和 30-60 秒动态保活；自动测试使用虚构数据，未把真实 Cookie、身份或响应写入仓库。
- IEB 会话保活已用 owner 提供的当前 Cookie 做过两轮只读请求验证；IEB 与 OA 均真实返回有效会话，动态间隔落在 30-60 秒。

## 3. 失败测试

实施时先写以下失败测试，再迁移实现。测试保护可观察契约和真实调用顺序，不断言模块数组位置、文件数量、私有函数名或整段 HTML 字符串。

### 3.1 Catalog v2 结构测试

- 索引和模块必须统一为 `schemaVersion: 2`；出现 v1、`internalRequests`、旧 `validationRequestId` 或 endpoint 顶层 `executionKind` 时加载失败，不保留双结构兼容分支。
- 每个系统必须提供 `session.validationRequestRef` 和 `session.keepAliveRequestRef`，两个引用都必须解析到同系统下已登记的生产请求定义。
- 每个 endpoint 必须有 `execution.kind` 和非空 `execution.steps`；直接 HTTP 与本地组合工作流使用同一入口读取执行契约。
- 每个 step 必须有唯一 `id`、合法 `requestRef`、合法 `role` 和合法 `cardinality`；条件步骤必须有非空 `condition`，分页或逐项循环必须写明收敛或停止条件。
- `$endpoint` 只允许出现在 `direct-http` 端点中，并且必须恰好有一个 `role=primary`、`cardinality=once` 的自身步骤。
- `local-workflow` 的生产步骤必须引用 `requestDefinitions`，不得把本地 `/api/execute` 冒充生产 URL。
- `relatedRequests` 的引用和 `option-source` 的 `sourceId` 必须唯一且可解析；所有 request definition 至少被会话、端点执行或模块相关关系使用一次，孤立定义加载失败。
- 请求定义继续校验 HTTPS 基础地址、GET/POST、绝对路径、Headers、参数、用途和响应契约；不允许用空文案占位。

### 3.2 现有模块迁移测试

- IEB 的验证与保活都解析到飞行经历查询页；OA 的验证与保活都解析到 `user-info`。
- 飞行经历、飞行人员信息 5 个端点和资质监控 29 个端点的执行链路均解析为“endpoint 自身一次”。
- 锁班提交按顺序解析为：类型页零或一次、员工校验一次、endpoint 自身提交一次；类型页条件必须表达“当前 Session 尚未缓存动态类型”。
- OA 数量只解析为待办分页的一次或多次循环；OA 已阅解析为待办分页循环后零次或多次逐条已阅。
- 锁班的额度、相关查询和四个状态动作只属于模块相关请求，不得出现在锁班提交执行链路。
- 资质分类树、权限、有效机型和原生导出只属于模块相关请求，不得出现在任一资质分页查询执行链路。
- 两个与 endpoint 重复的旧请求定义，即 `flight-stats.query` 和 `lock-entry.submit`，迁移后不存在。

### 3.3 执行器行为测试

- IEB 与 OA 载入 Cookie、定时保活都从系统 session 引用取请求，不再使用硬编码全 ID；Mock 请求方法、URL 和 Headers 与迁移前一致。
- 锁班选项通过 `sourceId=lock-types` 解析到相关请求；缓存命中不发类型页请求，缓存未命中时先取类型再校验员工、最后提交。
- OA 数量和已阅通过 endpoint step ID 取生产请求；分页次数、逐项次数、失败停止和渐进快照行为与现有测试一致。
- 所有直接 HTTP endpoint 仍以 endpoint 自身构造方法、URL、参数和 Headers；固定参数、空参数、multipart/form、HTML/JSON 解析行为不变。
- catalog 引用缺失、角色错误或执行器请求了未声明步骤时，在发出网络请求前失败。

### 3.4 页面与 Markdown 测试

- Cookie 页面显示每个系统的会话验证和保活角色；同一 request 同时承担两种角色时只渲染一张请求事实卡并显示两个角色。
- 每个 endpoint 页面都有“真实执行链路”；技术等级等直接端点显示自身请求一次，锁班和 OA 按各自真实步骤显示，不出现整个模块的相关请求集合。
- 模块概览只显示该模块的 `relatedRequests`，并区分元数据、选项来源、导出、相关查询和状态动作；没有相关请求的模块不显示空区域。
- 没有 `response.example` 时不显示“脱敏示例”标题和空框；有示例时页面与 Markdown 原样输出已脱敏 catalog 内容。
- Markdown 按“系统会话 -> 模块 -> endpoint 执行链路 -> 模块相关请求”输出，同一相关请求不在每个 endpoint 下重复。
- 页面和 Markdown 测试通过构造最小 catalog 数据断言语义输出，不以搜索私有函数名或固定 HTML 片段代替行为验证。

### 3.5 文档与交付测试

- 开发规格明确四层模型、字段约束、角色枚举、直接 HTTP 与本地组合工作流差异，以及新增模块模板。
- 用户手册只说明用户能看到的会话、执行链路和相关请求，不展示“事实源”“共用规则”等作者设计说明。
- 全量 typecheck、build、Vitest、Python tests 和 verify 通过；Git 中不得出现 Cookie、真实响应、员工数据或探测输出。

## 4. 目标

用户路径完成到：打开 Cookie 管理即可核对当前系统验证/保活请求；打开任一业务 endpoint 即可核对点击发送后会执行的生产步骤；打开模块概览即可查看不会自动执行但与该模块相关的接口。

代码主链路完成到：catalog v2 加载 -> 解析系统会话引用、endpoint 执行引用和模块相关引用 -> Python 执行器按引用选取请求 -> 页面与 Markdown 按角色分别渲染。

状态落点完成到：生产请求事实只定义一次；系统、endpoint 和模块使用稳定引用表达上下文；加载器拒绝悬空、重复、孤立和角色不合法的数据。

输出呈现完成到：每个端点均有真实执行链路；直接端点不再看起来“没有内部请求”；模块相关接口不再伪装成端点执行步骤；空示例和空相关请求区域不显示。

新增接入完成到：开发者复制 catalog v2 模板，填写系统会话、请求定义、endpoint 执行步骤和相关请求后，即可由加载器、页面、执行器和 Markdown 使用；无需新增一套前端专用请求说明。

完成判定：五个模块原子迁移，旧字段完全删除；现有读写风险、生产 URL、参数和运行结果没有行为回归；核心语义测试与全量仓库验证全部通过；规格、用户手册和实现一致。

## 5. 不做范围

- 不新增、删除或重新排序当前业务模块，不为 catalog 末尾位置编写测试。
- 不改变任何生产 URL、HTTP 方法、参数、Cookie、登录判定、响应解析或业务成功条件。
- 不把 catalog 变成通用工作流编排引擎；锁班和 OA 仍由各自专用代码控制数据依赖、循环、停止和错误处理。
- 不把资质原生 Excel、锁班状态动作或其他相关请求新增为可执行业务 endpoint。
- 不真实执行 OA 已阅、锁班提交、通过、撤销、解锁、否决或其他生产写操作。
- 不为缺失的响应示例伪造业务数据；示例没有已确认脱敏事实时保持省略并由渲染器隐藏。
- 不把 schema 迁移历史、作者规范、页面与执行器共用事实源等设计说明展示在前端业务页面。
- 不兼容读取 v1 与 v2 两套 catalog，不保留 `internalRequests` 别名或运行时回退。
- 不顺带重构与请求角色无关的主题、首页工具、业务 APP 或其他仓库模块。

## 6. 设计

### 6.1 统一术语

- `requestDefinitions`：模块内可复用的生产 HTTP 请求定义。只有不能直接用 endpoint 自身表示，且会被会话、组合执行或相关关系引用的请求才进入该列表。
- `session`：系统级 Cookie 验证与保活契约，只保存 request reference，不复制方法、路径和响应条件。
- `execution`：一个业务 endpoint 被执行时的真实生产请求步骤；记录顺序、角色、次数和条件。
- `relatedRequests`：模块已确认但不会作为当前 endpoint 自动执行步骤的请求关系。
- `$endpoint`：当前直接 HTTP endpoint 自身，只在该 endpoint 的执行步骤中使用，不是全局请求 ID。

“内部请求链路”一词从 schema、页面和 Markdown 中移除。页面使用“真实执行链路”和“模块相关请求”，避免把作用域不同的事实混为一类。

### 6.2 Schema v2

索引系统项改为显式 session 引用：

```json
{
  "id": "flight-portal",
  "session": {
    "validationRequestRef": "flight-stats.query-page",
    "keepAliveRequestRef": "flight-stats.query-page"
  }
}
```

模块内的复用请求使用唯一 ID 定义一次：

```json
{
  "requestDefinitions": [
    {
      "id": "query-page",
      "name": "飞行经历查询页",
      "purpose": "验证并保活 IEB 会话",
      "method": "GET",
      "path": "/newieb/flytime/showFlytimeManyQuery",
      "parameters": [],
      "response": "已确认的有效响应条件"
    }
  ]
}
```

直接 HTTP endpoint 明确以自身作为主请求：

```json
{
  "execution": {
    "kind": "direct-http",
    "steps": [
      {
        "id": "request",
        "requestRef": "$endpoint",
        "role": "primary",
        "cardinality": "once"
      }
    ]
  }
}
```

组合或多步骤 endpoint 引用请求定义：

```json
{
  "execution": {
    "kind": "local-workflow",
    "steps": [
      {
        "id": "scan-waiting",
        "requestRef": "oa-read.waiting-query",
        "role": "page-loop",
        "cardinality": "one-or-more",
        "stopCondition": "达到服务端总数，或遇到空页、短页、无新增记录"
      },
      {
        "id": "mark-read",
        "requestRef": "oa-read.have-read",
        "role": "item-loop",
        "cardinality": "zero-or-more",
        "condition": "只处理本次选中的 DOC/official-document",
        "stopCondition": "目标完成或首条失败"
      }
    ]
  }
}
```

模块相关请求通过引用附加上下文，不复制请求定义：

```json
{
  "relatedRequests": [
    {
      "requestRef": "lock-entry.entry-page",
      "kind": "option-source",
      "sourceId": "lock-types",
      "description": "提供当前 Session 可用的动态锁班类型"
    }
  ]
}
```

允许的 step `role` 固定为 `primary`、`prerequisite`、`page-loop`、`item-loop`、`postcondition`；`cardinality` 固定为 `once`、`zero-or-one`、`one-or-more`、`zero-or-more`。允许的 related `kind` 固定为 `metadata`、`option-source`、`export`、`reference-query`、`state-action`。新增枚举必须先有真实业务需要、规格和验证器更新，不能在单个 catalog 中自造字符串。

### 6.3 引用与加载器

`ApiCatalog` 建立 endpoint、request definition、系统 session、endpoint execution、related request 和 option source 六类索引。新增只读访问方法，至少包括：

- `get_endpoint(endpoint_id)`
- `get_request_definition(request_ref)`
- `get_session_request(system_id, purpose)`，其中 purpose 为 `validation` 或 `keepAlive`
- `get_execution_steps(endpoint_id)`
- `get_execution_request(endpoint_id, step_id)`
- `get_related_requests(module_id)`
- `get_option_source(source_id)`

引用统一使用 `<module-id>.<request-id>`；加载器确认被引用模块属于同一 system，避免跨系统复用 Cookie 或 Session。`$endpoint` 在解析时生成当前 `EndpointRecord`，不进入全局 request definition 索引。

schema v2 原子切换：Python 和浏览器 normalization 同时只接受 v2。浏览器侧不承担权威校验，但使用与 Python 相同的展开和引用语义；Python 启动加载是阻止错误 catalog 发出请求的最终边界。

### 6.4 五个模块迁移映射

| 模块 | Endpoint 执行契约 | 系统或模块关系 |
| --- | --- | --- |
| flight-stats | `query`: `$endpoint` primary once | `query-page` 供 IEB validation + keepAlive；删除重复 `query` definition |
| lock-entry | `submit`: `entry-page` prerequisite zero-or-one -> `employee-validation` prerequisite once -> `$endpoint` primary once | `entry-page` 是 `lock-types` option-source；额度和锁班查询类为 reference-query；通过/撤销/解锁/否决为 state-action；写操作均标记 write |
| personnel-info | 5 个 endpoint 各自 `$endpoint` primary once | 无额外 request definition，无空 related section |
| oa-read | `count`: `waiting-query` page-loop one-or-more；`read`: `waiting-query` page-loop one-or-more -> `have-read` item-loop zero-or-more | `user-info` 供 OA validation + keepAlive；没有额外 related request |
| qualification-monitor | 29 个 endpoint 各自 `$endpoint` primary once | 分类树为 metadata，数据权限和有效机型为 option-source，原生导出为 export |

当前共有 19 个 request definition：在删除两个与 endpoint 自身重复的旧定义后，增加 IEB 当前使用人请求。一个请求可以被多个上下文引用，例如锁班类型页同时是执行前置步骤和模块选项来源；页面按上下文展示角色，不复制底层方法、路径和响应契约。

### 6.5 执行器接入

IEB 与 OA adapter 不再写死验证和保活的全 ID，统一调用 `get_session_request()`。验证响应的系统专属解析规则保留在 adapter 中，catalog 只负责选择已确认请求，不用字符串代替真实判定代码。

锁班专用逻辑按 step ID 取得动态类型页、员工校验和 endpoint 请求；`load_options()` 通过 option source 索引解析 `lock-types`。endpoint 自身仍负责最终业务请求，避免重复请求事实。

OA 专用逻辑按 `scan-waiting` 和 `mark-read` step ID 取得请求。循环边界仍由现有代码执行，但测试同时核对 catalog 声明的 cardinality、condition、stopCondition 与代码行为，防止文档漂移。

直接 HTTP endpoint 继续使用当前 record 构造请求；新增通用 helper 可以校验 `$endpoint` primary step，但不把 HTML、multipart、PageInfo 或业务解析合并成一个不透明的通用工作流。

### 6.6 页面信息架构

Cookie 管理按系统显示会话请求和当前使用人。validation、identity 与 keepAlive 引用相同时合并请求事实，只用标签表达多个角色；不重复相同卡片。成功验证后身份只来自本次会话响应，不写死员工号或姓名。

sidebar 按系统 -> 飞行门户原生模块 -> GET/POST endpoint 镜像展示；系统和模块使用真实箭头展开/收起，OA 直接展示其两个本地工作流入口，不伪造 OA 原生模块层级。模块概览承载模块描述和 `relatedRequests`；endpoint 页面只承载该 endpoint 的请求、参数、响应和 `execution.steps`。

endpoint 的“真实执行链路”按步骤顺序展示：角色、次数、触发条件或停止条件、方法、完整 URL、参数摘要、用途和响应契约。直接 HTTP 端点也显示一步自身请求，因此技术等级、运行资格等页面不会再出现看似缺失的区域。

模块相关请求按 kind 分组并保留读写风险。`state-action` 必须显式显示写操作标记；相关请求不提供“发送”按钮，不改变现有可执行 endpoint 范围。

所有可选区域按数据存在性渲染：无 related request 不显示该区；无脱敏示例不显示示例标题和空框。页面不展示 schema 规则、事实源关系或迁移说明。

### 6.7 Markdown 与编写模板

Markdown 顺序固定为：认证与会话、模块概览、业务 endpoint、每个 endpoint 的真实执行链路、模块相关请求。原始 catalog 附录输出 v2 数据，但人类可读正文不再使用“内部请求链路”。

新增 `spec/dev/api-docs/catalog-authoring.md` 保存编写口径，并提供一份不含真实 Cookie/人员数据的最小 v2 模块模板。模板覆盖：

- 直接 HTTP endpoint 与 `$endpoint`。
- 有条件前置步骤。
- 本地组合工作流的分页和逐项循环。
- 系统 validation/keepAlive 引用。
- metadata、option-source、export、reference-query、state-action 五类相关请求。
- 可选响应示例的省略规则和敏感数据禁入规则。

catalog 仍是生产接口事实唯一来源；模板只规定结构，不复制任何现有业务模块的 URL、字段或响应事实。

### 6.8 错误与安全边界

任何无法解析的 request ref、跨系统引用、孤立定义、未知 role/kind/cardinality、重复 step/source ID 或不合法 `$endpoint` 都在目录加载阶段失败，不启动可执行服务。

迁移不改变 Cookie 保存、Session 隔离、Headers 脱敏或 loopback 监听。页面、Markdown、错误和测试 fixture 都不得加入真实 Cookie、员工号、OA 标题、响应正文或原生 Excel。

schema 迁移只需 Mock HTTP 回归即可证明请求选择和顺序。没有 owner 当次授权时不做生产写验证；若后续进行真实烟测，只允许已授权 Session 下的只读 IEB/OA 验证和查询，写接口仍需对具体对象另行授权。

### 6.9 可维护性语义审查

根目录 `AGENTS.md` 规定：单文件超过 300 行触发职责、耦合和扩展边界审查，但不机械要求拆分。当前超过 300 行的文件分别保持单一内聚职责：`flight_portal.py` 负责 IEB 适配器生命周期和请求编排，`flight_portal_parsers.py` 负责 IEB 响应解析，`app.mjs` 负责 API 文档页面状态编排，`catalog-view.mjs` 负责目录视图渲染，`styles.css` 负责页面样式；本轮未发现需要强制拆分的混合职责。后续跨职责新增代码必须先更新审查结论。

## 7. 实施任务

- [x] T001 建立 catalog v2 失败测试；文件：`tests/python/api_docs_tests/test_catalog.py`、新增前端 catalog normalization 测试；依赖：本 plan；验收：旧字段、悬空引用、孤立定义、跨系统引用、非法角色/基数和错误 `$endpoint` 在实现前明确失败。
- [x] T002 建立真实执行链路行为测试；文件：`tests/python/api_docs_tests/test_executor.py` 及必要的前端渲染测试；依赖：T001；验收：两个系统会话、锁班三步、OA 两类循环、36 个直接 HTTP endpoint 自身请求和模块相关请求隔离都有语义断言。
- [x] T003 编写 catalog v2 结构与新增模块模板；文件：`spec/dev/api-docs/catalog-authoring.md`、`spec/dev/api-docs/catalog-module.template.json`；依赖：T001；验收：四层模型、枚举、引用、可选字段、敏感数据和直接/组合示例完整，模板结构与身份引用口径已同步。
- [x] T004 原子迁移 index 与五个模块 catalog；文件：`public/tool/app/api-docs/catalog/*.json`；依赖：T001-T003；验收：全部文件为 v2，38 个 endpoint 均有 execution，19 个 request definition 全部被使用，旧字段与两个重复定义清零，现有生产请求事实不变。
- [x] T005 重构 Python catalog 加载与引用 API；文件：`public/tool/app/api-docs/api_docs/catalog.py`；依赖：T004；验收：六类索引和全部 v2 不变量测试通过，错误在任何网络请求前抛出，不保留 v1 回退。
- [x] T006 让系统 adapter 消费新引用；文件：`api_docs/systems/flight_portal.py`、`api_docs/systems/oa.py` 及相关 helper；依赖：T005；验收：验证、身份、保活、动态选项、锁班、OA 分页和逐项请求都从 session/execution/option source 解析，Mock 方法、URL、次数、顺序和停止行为无回归。
- [x] T007 更新浏览器 normalization、导航和渲染；文件：`catalog-normalize.mjs`、`app.mjs`、`catalog-view.mjs`、必要的页面样式；依赖：T004；验收：Cookie 会话角色、当前使用人、飞行门户原生层级导航、模块概览、每端点真实执行链路、相关请求分类和空区域条件渲染按数据驱动实现；页面不显示作者规范。
- [x] T008 更新 Markdown v2 导出；文件：`markdown-export.mjs`、`tests/tool/api-docs/markdown-export.test.ts`；依赖：T004、T007；验收：系统会话、端点链路和模块相关请求分层输出，资质相关请求不重复 29 次，原始附录是 v2 且不含旧字段。
- [x] T009 同步 API 文档规格和用户手册；文件：`spec/dev/api-docs/spec.md`、`spec/user/api-docs/manual.md`；依赖：T003-T008；验收：文档描述当前实现、身份、保活和原生导航，删除“内部请求链路”旧口径，不写迁移历史或未来事项。
- [x] T010 清理旧测试并运行聚焦验证；文件：`tests/python/api_docs_tests/`、`tests/tool/api-docs/`；依赖：T005-T009；验收：删除对 `internalRequests` 集合、catalog 顺序和私有 HTML 源码的脆弱断言，catalog、executor、server、页面、Markdown 聚焦测试全部通过。
- [x] T011 运行仓库全量收尾；依赖：T010；验收：`npm.cmd run typecheck`、`npm.cmd run build`、`npm.cmd test`、Python API docs 全量测试和 `npm.cmd run verify` 全部通过；未启动或遗留后台进程，Git diff 不含凭据、真实数据、探测结果或无关文件。

## 8. 验证计划

### 8.1 静态与结构验证

- 扫描 catalog，确认 `schemaVersion` 全部为 2，`internalRequests`、`validationRequestId` 和 endpoint 顶层 `executionKind` 为零。
- 展开 endpoint defaults 后统计为 5 个模块、38 个 endpoint、3 个资质分组和 29 个唯一 `qualType`。
- 统计 request definition 的所有使用方，确认没有悬空引用、孤立定义、跨系统引用或重复 option source。
- 对迁移前后每个生产请求的方法、基础地址、路径、Headers、参数和响应契约做结构化比较；仅允许字段搬迁和两个 endpoint 重复副本删除。

### 8.2 Python 聚焦验证

```powershell
python -m unittest discover -s tests/python/api_docs_tests -t tests/python
```

使用 fake Session 核对 IEB/OA 验证、身份与保活，锁班缓存分支和三步顺序，五个飞行人员请求编码，29 个资质 GET 参数，OA 分页收敛、逐项次数、失败停止与渐进结果。所有自动测试使用虚构数据，不触发生产请求。

### 8.3 前端与 Markdown 验证

```powershell
npx.cmd vitest run tests/tool/api-docs
npm.cmd run typecheck
npm.cmd run build
```

用最小内存 catalog 分别覆盖：同一会话请求的双角色、直接 endpoint、条件前置步骤、分页循环、逐项循环、有/无相关请求、有/无响应示例和 state-action 写标记。Markdown 核对语义与唯一出现次数，不快照整篇文档。

### 8.4 全量验证

```powershell
npm.cmd test
npm.cmd run verify
```

检查 `git diff --check`、UTF-8 无 BOM、敏感词和未跟踪输出；确认没有真实 Cookie、请求响应、人员信息、OA 标题、Excel 或临时探测文件进入变更。

### 8.5 人工验收

由 owner 打开页面检查：

- Cookie 管理中的 IEB、OA 验证与保活角色是否清楚。
- 技术等级、运行资格、资质查询等直接端点是否显示自身一步请求。
- 锁班提交是否只显示真实三步，相关状态动作是否只在模块概览出现并标记写操作。
- OA 数量与已阅是否分别显示正确的分页和逐项循环。
- 资质监控四个相关请求是否只在模块概览出现一次。
- 无响应示例和无相关请求时是否没有空白标题或空容器。

本次是 catalog 与执行引用重构，不改变已确认的生产接口事实；自动测试通过只能证明本地实现一致，不能单独证明外部系统当日状态。生产烟测如需进行，必须另取 owner 当次 Session 和授权，且写操作逐项确认。

## 9. 收口

实现完成后，`plan.md` 中 T001-T011 必须依据实际证据逐项勾选，不能一次性补写完成。代码、catalog、测试、开发规格和用户手册必须同时反映 v2 当前事实。

收口检查：旧字段与旧文案全局扫描为零；五个模块执行映射与本 plan 一致；全量命令通过；页面人工验收完成；没有遗留进程、端口、Cookie、真实业务数据、下载物、临时 fixture 或无关变更。

最终回复只说明统一后的三类作用域、迁移和验证结果，以及未进行的生产验证。若任一核心引用、执行顺序、文档或全量测试未完成，不得把任务标记为完成。
