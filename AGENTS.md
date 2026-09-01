# csn2api Agent 工作规约

本文件是仓库地图和最高约束。具体开发方法看 `.agents/skills/`，具体业务事实看 `spec/`。

## 基础约束

- 始终使用简体中文和项目 owner 交流。
- 仓库文本文件统一使用 UTF-8 无 BOM；发现 BOM 或其他可清洗的编码问题时直接规范源文件，不在读取端保留兼容分支。
- 阅读本仓库文本文件时按 UTF-8 读取；PowerShell 中文显示乱码时，不要误判文件损坏。
- PowerShell here-string 或管道把含中文字符串的脚本传给 `node`、`python` 等命令时，中文字面量可能被终端编码污染成问号；涉及中文路径、sheet 名、表头、分类名的验证脚本，优先用文件扫描、索引、表头读取结果或 UTF-8 脚本文件定位。
- 在 PowerShell 中运行 Node/npm 命令时使用 `npm.cmd`、`npx.cmd`，不要直接用 `npm`、`npx`。
- 不回滚用户已有改动；脏工作区只处理当前任务相关文件。

## 事实纪律

- 所有判断、计划、代码修改和回复必须基于仓库代码、spec、测试、命令输出、用户提供的数据或可复现运行结果。
- 必须区分已确认事实、用户提供事实、未验证推测、计划事项和已完成并验证事项。
- 任何会影响生产数据、接口契约、导出结果、自动化提交或用户工作流的不明确事项，都必须向 owner 确认后再执行。
- HTTP 200、页面提示、Mock 或单元测试都不能单独证明生产业务成功。
- 文档只写当前事实，不写历史过程、未来计划或未经验证的推测。

## 产品边界

- 本项目品牌和仓库名均为 `csn2api`；飞行门户 IEB 是接入的业务系统，其应用名称、域名、Cookie 和接口事实不随仓库品牌改名。
- 首页业务工具由 `src/tool/tools-data.ts` 登记，不在 Agent 规约中固定工具数量或穷举当前清单。
- API 文档位于 `public/tool/app/api-docs/`，通过 catalog 按系统持续接入已确认的 HTTP 接口事实和明确标记的本地组合工作流。
- 每个工作台与 API 文档必须保持独立可运行，不依赖其他本地仓库；不同系统不得共享 Cookie、Session 或接口事实。
- SOC 随机置位是 csn2api 接入的独立业务系统，当前工作台、API catalog 和 `soc_protocol` 共同维护同一契约；SOC 与 IEB 不共享页面、Cookie、Session、protocol core 或接口事实，领域探测继续由 `soc-positioning` skill 维护。

## Skills

- 中大型开发、跨模块重构、工具下线、测试结构整理或生产级验收时，先读 `.agents/skills/plan/SKILL.md` 并维护根目录 `plan.md`。
- `plan.md` 仅作为本地执行合同，必须由 `.gitignore` 忽略，不得使用 `git add -f` 强制提交；任务收口写回本地即可。
- 新增或修改工具、业务规则、spec、测试或构建时，读 `.agents/skills/csn2api-dev/SKILL.md`。
- 涉及页面 UI、表格、筛选区、结果区或主题时，读 `.agents/skills/ui-clarity/SKILL.md`。
- 涉及 Excel 读取、导出、表头映射或日期解析时，读 `.agents/skills/excel-dev/SKILL.md`。
- 涉及 IEB Cookie/cURL、Network 请求、纯 HTTP 查询或状态动作时，读 `.agents/skills/flight-portal-http-probe/SKILL.md`。
- 涉及 IEB 飞行航班明细、`flytimeList`、`showFlyDetail`、按自然月查询或 `http-flight-detail-helper` 时，除通用开发规约外必须按 `flight-portal-http-probe` 的明细 reference 和真实验收链路执行；接口事实只进入该 skill reference、catalog 和对应 spec，不在本文件复制。
- 涉及 API 目录、页面、本地执行器、Cookie 生命周期、真实调试或 Markdown 导出时，读 `.agents/skills/api-docs-dev/SKILL.md`。
- 涉及 SOC 随机置位、`KkTvlApply` 或随机审批申请时，读 `.agents/skills/soc-positioning/SKILL.md`；不得把 SOC 与 IEB skill 或接口事实混用。
- 新增任何 APP 必须遵循固定前置顺序：先用当次授权 Session 完成真实 HTTP 探针并确认数据结构，再把已确认经验沉淀到对应 skill，随后仅在被 `.gitignore` 忽略的根目录临时文件中提供脱敏探针脚本、样例输入和结果摘要，交由 owner 审核确认；owner 未确认前不得创建或实现新的 APP。
- 如果 skill 和 owner 当前明确需求冲突，以 owner 当前需求为准，并说明冲突点。

## 规则归属

- `AGENTS.md` 只维护跨工具长期成立的仓库约束；skill 维护可复用开发方法；`spec/dev/` 与 `spec/user/` 维护当前业务行为；catalog 维护 HTTP 声明事实；protocol core 维护真实请求与响应契约。不得在多个层级复制同一事实。
- 接口路径、参数、动态选项、字段映射和系统特判不得写入通用 skill；一次真实返回的数量、页数和字段快照只能作为当次证据或业务 reference，不能升级为永久常量。
- 经验沉淀优先变成已有动态合同测试、统一构建或真实验收门禁；只有无法由代码表达且会改变后续决策的内容才写入规约。
- 当前契约重构直接迁移到新架构，不为已废弃字段、目录、入口或历史结果保留兼容分支；只有当前 spec 明确支持的真实输入才允许兼容，并必须有测试保护。

## 安全与生产边界

- Cookie、cURL、真实身份、记录 ID、原始响应、截图和临时结果不得进入 Git、fixture、日志或静态文件。
- 各 HTTP 工作台与 API 文档子服务只监听 `127.0.0.1`；只有根目录 `start_all.py` 的统一网关监听局域网地址并转发已登记入口。
- 凭据默认只保存在各应用自己的本地后端内存；API 文档可导出或导入含明文凭据的 `csn2api-cookie-bundle` 文件，但不得自动分发给工作台。每个工作台与 API 文档分别验证、保存和清除自己的 Cookie 与 Session。Cookie 文件不得进入 Git、日志、结果目录或静态构建产物。
- 飞行经历和飞行人员信息是只读查询；锁班提交、通过、撤销、解锁和否决是写操作。
- 生产写操作必须取得 owner 对当前对象、日期、类型、备注和动作的明确授权；过去授权不延续。
- 批量工作台的执行顺序、停止和恢复边界以对应 spec 为准；没有 owner 明确要求和真实证据时不新增并发入口。
- 批量工作台默认严格串行：除登录会话失效外，行级 HTTP 异常、动态数据缺失、校验拒绝、业务失败和解析异常都必须记录为失败并继续完成后续行；每行最终写请求最多一次，不自动重试。
- 登录失效、响应契约变化、归属不唯一或业务结果不明确时停止当前动作，不无限重试或猜字段；若属于单行普通异常，按对应批量 spec 标记该行失败并继续。

## Spec、测试与完成标准

- `spec/dev/` 保存开发规格和业务规则，`spec/user/` 保存用户手册。
- 代码、测试和文档必须同步；任一方描述旧事实，任务就没有完成。
- 修改业务规则、解析规则、日期规则、导出结构或修复回归时，优先补充或更新测试。
- 测试保护可观察业务规则，不为目录形状或临时实现写脆弱断言。
- 仓库发生代码改动后，收尾前必须运行全量测试；无法运行时说明原因和风险。
- 真实接口验证需要 owner 当次授权的 Session；没有真实验证时只能报告自动测试结果。
- 新增或修改 API 文档、请求参数、响应解析或执行链路时，必须先使用 owner 当次授权的 Session 按真实页面正向链路探测请求与响应，再编写 catalog 和执行器；实现后必须使用同一真实链路复验结构化结果。Mock、fixture、HTTP 200 和单元测试只用于保护已确认契约，不能替代修改前探测或修改后真实复验。
- 开始实现前必须阅读目标 spec、同类型成熟工具、已有 protocol core/catalog 和相关动态合同测试，确认沿用边界与特判位置；中大型任务在 `plan.md` 记录，不得从空白页面或复制旧单文件开始堆功能。
- 修复回归或改变可观察契约时，先用最小失败测试证明缺口；完成后局部测试、全量 `npm.cmd run verify` 和适用的真实验收必须分别通过。
- 新增工具不得维护固定工具总数或测试名单。工具登记、页面发现、独立 ZIP、共享运行资源和 protocol core 封装必须进入现有动态发现链路；通用门禁缺口优先修复统一门禁，而不是只给当前工具补特例。
- 同一能力同时提供 APP 和 API 文档时，验收必须从各自用户入口进入同一 protocol core。API 调通不代表 APP 已接通，APP 可用也不代表 API 文档的参数与结构化展示正确；两个入口必须分别验证。

## 工程取舍

- 浏览器工具保持静态、本地优先和按工具独立；不为了展示技术增加框架和层级。
- TypeScript 使用同一严格类型检查配置；稳定业务函数写明参数和返回结构。
- 每个 Python 工作台是可独立分发的完整 APP，不为了复用拆成跨工具运行时依赖。
- Excel 员工号按文本归一，日期按业务日期处理，不依赖 UTC 字符串表现。
- 页面使用 `public/theme.css` 和 `public/theme.js`；页面专属 CSS 只维护布局和领域特判。
- 同一生产系统的 API 文档与独立 APP 必须共用 protocol core；Cookie 解析、URL/方法、参数构造、分页收敛、会话失效、响应契约和实体归属不得维护两套实现。catalog 是声明式接口事实源，protocol core 是命令式请求实现；APP 只扩展批量编排、进度、Excel 和业务 UI，API 文档只扩展单次调试和结构化展示。
- 独立分发不等于复制核心源码。构建过程把同一 protocol core 封装进需要它的独立包；任何入口不得在运行时依赖另一个正在运行的 APP。测试必须同时保护 catalog 与 protocol core 契约一致、各入口使用同一 core，以及独立包包含完整运行依赖。
- 稳定事实集中在 core、catalog、字段映射或共享模块；系统、端点和页面差异放各自 adapter。不得用条件分支把特判反向塞进通用层，也不得把 core、HTTP 适配、批量编排、Excel 和 UI 混成上帝文件。

## 可维护性与扩展性审查

- 新增功能必须说明所属职责、扩展边界和依赖的事实来源，优先沿用现有模块、目录和执行器边界。
- 单个源文件超过 300 行时触发语义审查：检查它是否仍然只承担一个内聚职责、是否存在可独立演进的第二职责、是否会阻碍后续扩展；这是审查触发器，不是强制拆文件阈值。
- 审查结论以职责和耦合为依据：若文件仍是单一职责且边界清晰，可以保留；若存在混合职责，必须在当前任务范围内拆分或记录明确的后续拆分理由。
- 不为了降低行数机械拆分，不为了“可扩展”预先引入抽象；扩展点必须对应已确认的业务变化或稳定的接口契约。

## 运行证据

- 用户提供原始输入时优先用原始输入复现；表格、文本、日期和姓名问题需要查看中间值。
- 浏览器自动化问题要区分输入解析、页面值和实际提交值；本仓库当前产品不依赖 Playwright。
- 内网不可访问时，以用户提供的 HTML、截图、日志和本地代码为事实来源。
- `start_index.py`、`start_all.py` 和各 APP 本地入口是否长期运行由 owner 决定。agent 为验证临时启动后必须终止本轮网关及全部子服务并确认端口释放。
- OA 已阅工作台由 owner 自行启动。agent 默认不直接启动或留下后台进程；确需临时启动验证时，必须在交付前关闭并确认端口释放。
- 前端视觉由 owner 人工检查；agent 负责构建、测试和静态连通性验证。

## 仓库入口

- TypeScript 源码在 `src/`，静态页面和 Python APP 在 `public/`，构建产物在 `dist/`。
- 首页工具清单在 `src/tool/tools-data.ts`，首页在 `public/tool/index.html`。
- `start_index.py` 提供纯静态预览；`start_all.py` 提供单端口局域网前后端入口；每个工作台和 API 文档各自保留独立 `start.py`。
- API 文档在 `public/tool/app/api-docs/`，HTTP 工作台分别位于 `public/tool/app/http-*/`。
- API catalog JSON 是接口请求与响应契约的唯一事实源。
- 开发规格在 `spec/dev/<tool>/`，用户手册在 `spec/user/<tool>/manual.md`，测试在 `tests/`。

## 常用命令

```powershell
npm.cmd run build
npm.cmd run typecheck
npm.cmd test
npm.cmd run verify
npx.cmd vitest run tests/tool/<name>.test.ts
```

## 真实验收入口

- 跨系统 API 文档与独立 APP 的真实验收统一使用 `scripts/real-api-verification.py`；具体 Case 维护在 `scripts/real_verification/`，不得另建包含生产请求逻辑的临时探针。
- 从 `spec/dev/real-api-verification/cookies.template.md` 复制本地 `cookies.local.md`，只在被 Git 忽略的本地文件填写 Cookie、真实身份和验收参数。
- 脚本默认只读；使用 `--system`、`--scope` 和 `--case` 单独复跑系统、入口或业务模块。写操作必须同时提供 `--allow-write` 及对应精确确认参数，并遵守本文件的当次授权边界。
- 真实验收脚本必须经过前端路由、APP loopback HTTP 服务和共享 protocol core；执行后关闭临时服务并清理临时结果。自动测试只保护已确认契约，不替代真实验收。
- 新 APP 的修改前探针不进入 `scripts/real_verification/` 或生产代码；审核材料只允许使用脱敏摘要和合成样例，真实 Cookie、身份、员工号、原始响应和临时结果放系统临时目录并在本轮清理。owner 审核通过后，才能把已确认契约转入 spec、core、APP 和正式真实验收 Case。

## 提交与推送

- 提交信息使用简体中文，写成不分段、不换行的完整段落，具体说明实际修改和行为变化。
- 提交前确认暂存区只包含当前任务文件。
- 不提交真实业务数据、Cookie、临时文件、探测输出或构建产物。
- 每次任务完成并通过必要验证后，直接提交并推送到当前分支，不等待 owner 另行提醒；工作区中与当前任务无关的已有改动不得暂存、回滚或覆盖。

## 收尾回复

- 最终回复保持简洁，说明改了什么、验证了什么和剩余风险。
- 不粘贴大段日志、diff 或源码，除非 owner 明确要求。
