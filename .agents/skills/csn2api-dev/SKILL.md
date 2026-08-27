---
name: csn2api-dev
description: csn2api 仓库内新增、接入或修改工具的一般开发流程，覆盖业务工作台、API 文档、本地 Python 执行器、spec、测试和构建收尾。
---

# csn2api Dev

在本仓库新增或修改工具时使用本 skill。先读 AGENTS.md，再看同类型的目标工具和对应 spec，不从零臆造结构。

## 开始顺序

1. 定位目标 spec、工具登记、同类型成熟工具、共享 protocol core/catalog、构建脚本和动态合同测试；先确认哪些能力已经由仓库统一提供。
2. 画清职责链：catalog 声明接口事实，protocol core 实现请求与响应契约，adapter 处理系统或端点特判，runner/manager 负责编排和状态，Excel 与 UI 只消费稳定结果。
3. 回归或契约变化先补最小失败测试；中大型任务在 `plan.md` 写清真实事实、复用边界、特判位置、入口和交付验证。
4. 涉及生产 HTTP 时先按对应 probe skill 用 owner 当次 Session 走页面正向链路；会话失效就停止该系统真实请求，不用 Mock 代替事实发现。

## 开发范围

- API 文档由 public/tool/app/api-docs/catalog/ 驱动，接口事实以 catalog 和 HTTP probe reference 为准。
- Python 工具页面位于 public/tool/app/<tool>/，源码位于 src/tool/app/<tool>/，每个 APP 可独立分发。
- SOC 随机置位的工作台与 API 文档遵循本仓库通用开发合同，领域接口事实读取 `soc-positioning`；SOC 使用独立 `soc_protocol`，不与 IEB Cookie、Session、core 或接口事实混用。

## 实现原则

- 业务规则写入 spec/dev/<tool>/，用户操作写入 spec/user/<tool>/manual.md，不要把业务事实写进 skill。
- 代码、测试、文档同步维护；任一处仍描述旧工具或旧品牌，任务就未完成。
- 业务逻辑与页面渲染分开，稳定逻辑直接导入 src/ 测试。
- 页面接入共享 theme.js、theme.css；专属 CSS 只维护布局和领域特判。
- Cookie、真实响应和生产写操作不写入仓库；没有授权时只运行本地脱敏测试。
- 重构直接更新当前契约及其调用方、测试和文档，不保留已废弃字段、旧目录或双实现兜底。
- 单个模块只承担一个可独立解释的职责。稳定事实进入共享 core；小而必要的系统差异也进入对应 adapter，不以“代码少”为理由混入通用模块。

## 工作台完成合同

新增或修改 Python HTTP 工作台时，按任务性质复用现有合同：

- 首页工具只通过 `src/tool/tools-data.ts` 登记；详情入口提供对应独立 ZIP，构建包包含 manifest、启动入口、Python 依赖、页面实际引用资源和封装后的 protocol core。
- 页面按用户工作顺序分步。Cookie 验证、动态元数据加载和业务执行是不同动作时必须分开；批量或长任务提供进度、停止边界、逐项结果和活动日志。
- 页面加载 Bootstrap、`theme.js`、`theme.css`、专属 `styles.css` 和标准保活模块。实现不能只写引用，loopback 服务和独立 ZIP 都必须实际返回这些资源。
- 页面交互、滚动、可见文案和动态表格遵循 `ui-clarity`，Excel 解析与持久化遵循 `excel-dev`，不在工作台内另造一套通用规范。
- 新工作台必须进入现有动态合同测试，并在统一真实验收中维护对应业务 Case；不要为当前工具另写固定数量或固定名单检查。

## 双入口与真实证据

- API 文档与独立 APP 共用同一 protocol core，但入口职责不同：API 文档提供单次参数调试和结构化结果，APP 提供封装工作流、批量状态、Excel 和用户交互。
- 修改 HTTP 契约时，顺序是“真实页面探测 -> core/catalog -> API 与 APP -> 同一真实链路复验”。真实复验要经过 API 执行器和 APP loopback 路由，不能只直接调用 client。
- HTTP 200 只证明服务器返回；成功还要核对登录状态、响应契约、业务归属、动态计数或写后查询。最终回复分别报告自动测试和真实验收。

## 验证

修改后按范围运行局部测试，并在收尾执行：

    npm.cmd run build
    npm.cmd run typecheck
    npm.cmd test
    npm.cmd run verify

PowerShell 中使用 npm.cmd 和 npx.cmd。构建失败时修复源代码、入口清单、静态文件或依赖闭包，不从旧 dist/ 回填源码。

提交前再确认：

- 页面引用的公共资源可由 loopback 服务实际访问，前端按钮绑定真实后端路由。
- 详情入口、独立 ZIP、包内资源闭包和 protocol core 依赖由动态合同测试覆盖。
- spec、用户手册、catalog、代码和测试描述同一当前行为。
- 临时服务已关闭，端口已释放；Cookie、真实身份、原始响应、结果文件和构建产物未进入 Git。

## 提交

- 提交前检查 git status --short，只包含当前任务文件。
- 不提交真实业务数据、Cookie、临时探测输出、dist/ 或无关变更。
- 提交信息使用简体中文单段落。
