# API 文档开发规格

## 定位

API 文档是跨系统 HTTP 接口的事实导航和真实调试器，不是独立批量业务工作台。当前目录包含 IEB 飞行经历、训练安排、非生产任务下的锁班、飞行人员信息、资质监控按资质查询、OA 数量扫描与已阅、SOC 随机置位申请以及 CAAC 飞行员信息模块；后续系统继续以独立模块加入，不在规格中固定模块数量。catalog 可以登记本地组合工作流，但必须明确标记，不能把组合流程描述成生产系统原生接口。锁班提交只在唯一归属且状态为待审批时返回提交成功；`lock-entry.approve-pending` 是独立本地工作流，按员工、类型和完整日期时间唯一定位待审批记录，复用共享状态动作协议执行通过，并在目标已进入已锁且不再待审批后才返回通过成功。

## 事实源

`public/tool/app/api-docs/catalog/index.json` 保存系统级 Cookie 获取指南和模块索引；其引用的模块 JSON 是 URL、方法、Headers、参数、响应契约、端点真实执行链路和模块相关请求的唯一事实源。静态页面、Python 后端和 Markdown 导出必须直接消费同一目录，不分别维护接口字段表或获取说明。

同一系统的 API 文档执行器与独立 APP 共用 protocol core。protocol core 负责 Cookie、真实请求构造、分页、会话失效、响应结构校验和业务实体归属；API 文档只把单次结果转换为摘要和动态表格，独立 APP 只增加批量编排、检查点、Excel 与工作台状态。构建时把同一 core 封装进各自交付目录，入口之间不形成运行时依赖；catalog 与 core 的路径、方法和参数存在性由契约测试核对。

本地执行器按生产系统组织为 `systems/<system>/` 包，包内拆分会话 adapter、领域执行和展示特判，不保留同名散装模块或旧导入转发层。`scripts/protocol-cores.json` 集中声明系统、core、catalog 模块、API 包和分发目标；构建与合同测试消费同一声明。

飞行人员信息模块按四个分组展示：基础信息、技术等级、运行资格、训练检查记录。当前五个业务 endpoint 为基础信息、技术等级、运行资格、培训记录和训练经历；运行资格使用当前资格接口，培训记录的批量分页属于飞行人员信息查询（皇帝版）工作台，API 文档只执行用户指定的单页真实请求。

运行资质人员名册模块记录技术资料组合筛选页、动态运行资格列表、按单个资格查询、普通人员清单导出和本地逐资格合并工作流。门户多个 `operQualArray` 是 OR 查询，API 文档的生产请求只表达单个资格；机型和人员状态按重复 Query 参数发送。共享 core 接受 `qualTypeArray=CAP` 和 `qualTypeArray=FO` 友好别名，分别展开为当前 13 项机长/返聘机长/飞行教员等级和 6 项副驾驶等级；`operQualArray` 可留空以按技术等级筛选。普通人员清单导出按实际 Excel 表头解析全部数据行，二进制正文不进入原始响应区；四列 Excel 合并属于独立 APP 的 local workflow，不伪装成门户原生接口。

CAAC 有效飞行员列表把当前 `{total, rows}` 转为动态字段表格。单人详情是正向本地工作流：先把姓名和可选档案号发送给列表请求并动态分页，姓名精确匹配且唯一后，才把该行真实 `pilotId` 发送给详情请求；零匹配或多匹配停止，不猜内部 ID。详情顶层标量、对象和数组按当前响应分别结构化，嵌套值使用 JSON 文本保留，不产生 `[object Object]`。

资质监控模块按资质运行类、资质资格类、资质特殊类展示分类树当前返回的独立 endpoint。常规资质共享 `GET /newieb/qualification/alarm/new/queryAlarmDetail`、空筛选参数和 PageInfo 响应契约，只固定不同 `qualType`；`JCY` 使用 `GET /newieb/zhftcCheckerInfo/pageZhftcCheckerInfo` 及检查员库独立筛选参数，不继承常规参数。共享默认值由 catalog 的 `endpointDefaults` 与 `commonParameters` 保存，真实特判可明确关闭公共参数继承；浏览器、Markdown 和 Python 目录加载器必须得到相同展开结果。分类树、权限选项、有效机型、检查员库选项和两类原生 Excel 导出登记为模块相关请求；当前真实 Session 下检查员库原生导出返回 HTTP 500，资质监控 APP 对 `JCY` 改走分页查询并本地生成 Excel，API 文档仍保留分页接口调试事实。

## Cookie 生命周期

- IEB 与 OA 分别维护 Cookie、`requests.Session`、验证请求和保活状态，不共享运行时凭据。
- `POST /api/session` 携带 `systemId` 和当前页面提交的 Cookie Header/cURL；各系统 parser 先复用 `credential_text.normalize_credential_source` 撤销富文本引入的 Markdown URL、反斜杠下划线/星号和转义长选项，再执行各自 Cookie 规则。
- Cookie 管理在右侧同一滚动区域按 catalog 系统顺序纵向叠加完整面板；每个面板独立提供输入、验证、状态、清除和当前页 Cookie。新增系统继续向下追加，不使用横向系统标签切换。
- 验证成功后对应系统面板显示可复制的规范化 Cookie Header；页面刷新从当前 Python 后端恢复仍有效的 Session 与规范化 Cookie，主动清除只清对应面板的系统。页面不得从 localStorage 恢复凭据。
- `GET/POST /api/credentials` 导出或导入 `format=csn2api-cookie-bundle`、`schemaVersion=1` 的 JSON。导出只包含当前仍有效系统的规范化明文 Cookie；导入按系统调用现有验证链路，逐系统返回成功和失败，不绕过真实验证。页面直接粘贴验证通过 API 文档自身的 `/api/session` 提交；统一运行时不解析、不保存或分发 Cookie，普通工作台保留自己的 Cookie 输入和验证入口。独立 API 文档和独立 APP 仍各自维护本进程凭据。
- 每个有效系统会话使用 30-60 秒随机只读请求独立保活；页面按后端返回的下一次间隔显示倒计时，登录失效会清空对应系统会话并停止该系统请求，不影响另一系统。
- 会话验证成功后按系统身份请求解析当前使用人；IEB 从门户首页解析员工号和姓名，OA 从 `loginUserInfo` 解析员工号和姓名，SOC 只从外层导航页 `#checkout_soc`/`#checkout` 的服务端欢迎语解析并显示姓名，失败时不伪造身份。
- SOC 使用独立 Cookie 和 `requests.Session`，验证请求为随机置位申请页；页面返回 `applyFm` 与 `KkTvlApply` 才视为进入业务页面。SOC 业务 action 失效时可能返回 `302 .../doSsoProxy` 或 IAM 登录页，静态资源 200 不能代替业务验证。
- 常规状态、日志、Markdown 和原始响应不得包含 Cookie 值；只有用户明确执行的 Cookie 文件导出响应包含明文凭据。

系统访问网址、建议抓取请求、Copy as cURL 步骤和 HttpOnly 说明来自 `catalog/index.json`。IEB 从 `https://ieb.csair.com/index/index` 登录并可复制任意已登录 `ieb.csair.com` 请求；OA 从待办列表进入，优先复制 `POST /oai/work/box/query/waiting` 的完整 cURL，以同时取得 Cookie、User-Agent 和待办 JSON 模板。标准 Windows/Linux cURL 直接解析；聊天或富文本复制产生的等价 Markdown 转义在共享输入层规范化。

## 接口执行

飞行经历时间轴提供 `flight-detail.query-history`：按员工号和姓名校验归属，输出全页汇总、历史合计、年度和月份全部行及动态原表头，与飞行经历时间查询 APP 共用同一 protocol core；姓名仅作为本地归属校验参数。

页面只提交完整 endpoint ID 和业务参数，基础地址、路径和方法来自目录。后端按 `systemId` 选择适配器，区分 HTTP 状态、登录失效、解析错误和业务返回；HTTP 200 不单独代表业务成功。结构化表格、原始 JSON/HTML、响应 Headers 和状态码同时返回。

API 文档服务同时提供 `/api/universal-query/v1` 机器接口，供机器人和 CLI 使用。该接口在 `universal_query` 模块内把同一 `ApiCatalog` 动态投影为操作、参数、默认值、固定/自动项、最少用户输入和读写风险，不维护第二份操作清单或协议实现。它经现有 `ApiExecutor` 复用同一系统会话和保活；会话载入只接受 `credential`，返回的会话状态已脱敏。普通和渐进执行统一返回操作、系统、风险、状态和安全的 `summary`/`tables`，不返回 Cookie、请求 URL、原始正文或调试 headers。写操作仍在动态清单和同一执行入口中开放，但真实调用遵守现有当次生产授权边界。完整 HTTP 契约见 `spec/dev/universal-query/spec.md`。

生产请求仍由 Python `requests` 发送，但共享 protocol core 会显式设置浏览器 User-Agent，不使用 `python-requests/...` 默认标识；OA 完整 cURL 中存在 User-Agent 时优先复用用户提供的值，未提供时才使用默认浏览器 User-Agent。

资质监控常规入口使用通用 GET 执行分支，固定 `qualType` 不接受调用方覆盖且空筛选参数仍进入 Query。JCY 执行分支由 protocol core 根据稳定业务代码切换到检查员库路径，省略空筛选项且不发送 `qualType`。两类 PageInfo 的 `list` 都转为动态字段表格，摘要保留当前页记录数、总数、页数、页码、每页条数和下一页标记。API 文档不代理原生 Excel 二进制下载；资质监控（皇帝版）的一键 ZIP 是独立本地 APP 的组合工作流。

OA 对外只提供两个本地组合工作流。“获取全部 OA 数量”遍历全部待办分页并返回总数、可处理公文数、跳过数和动态模块汇总；“按数量点击 OA 已阅”先执行相同全量扫描，再只选取 `DOC/official-document`，按用户输入的任意正整数逐条调用生产 `haveRead`。生产待办分页和单条已阅登记为端点真实执行步骤，不独立显示为业务入口。

SOC 随机置位接口按“站点建议 -> 动态航班 -> 人员与业务校验 -> 单条提交”理解。申请原因使用当前页面确认的 20 条静态字典，动态航班 option 的完整复合值必须原样传入提交；批量工作台属于独立本地 APP，API 文档只调试目录登记的单次请求。SOC 的提交是写操作，只有 owner 当次明确授权才可真实执行，业务成功唯一按 JSON `message=录入成功！` 判定。

数量 1 和其他数量使用同一链路；不设置最大值，超过可处理数时自动收敛。分页按服务端总数、空页、短页或无新增记录收敛，不设置固定页数上限。已阅入口启动本地渐进任务：扫描完成即发布初始快照，每条 OA 返回后把该条结果追加到快照，页面轮询并立即更新结果表。结果表默认跟随最新一条并自动滚到底部；用户向上滚动后暂停跟随，回到底部后恢复。只有登录会话失效时停止后续派发；单条 HTTP、响应结构、业务码或其他异常均标记当前条目失败并继续，每条最多提交一次；同一系统不并行运行两个渐进任务。

## 导出

“导出 Markdown”不依赖本地后端，读取当前已加载的静态目录生成一个机器和人类都可读的单文件；正文按系统会话、模块概览、端点执行链路和模块相关请求分层输出，不得包含 Cookie、会话状态、真实响应或人员数据。原始目录 JSON 作为附录保留全部条件字段、动态选项、派生来源和响应契约。

## 页面布局

桌面宽屏使用接口目录、文档、调试控制台三栏布局；中等宽度把调试控制台排到文档下方。720px 及以下按状态条、页头、目录、文档、调试控制台纵向排列，搜索独占一行，Cookie 与 Markdown 操作使用两列可收缩网格。页面壳不得产生横向滚动；参数表、响应表等确需固定列宽的内容只在各自滚动壳内横向滚动。

## 验证

API 接入顺序固定为：使用 owner 当次授权的 Session 按真实页面正向链路完成修改前探测，记录 URL、方法、参数存在性、重复字段、响应格式和结构化归属；再更新 catalog、执行器、测试和文档；最后使用同一真实链路完成修改后复验，核对结构化结果与原始响应。单元测试、fixture 和 Mock 只保护已确认的目录加载、参数构造、解析、状态生命周期和交付连通性，不能替代任一阶段的真实验证；HTTP 200 也不能单独证明接口有效。生产写操作必须取得当次明确授权。没有真实验证只能标记未验证，不能宣称生产有效。
