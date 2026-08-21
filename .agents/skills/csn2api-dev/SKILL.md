---
name: csn2api-dev
description: csn2api 仓库内新增、接入或修改工具的一般开发流程，覆盖业务工作台、API 文档、本地 Python 执行器、spec、测试和构建收尾。
---

# csn2api Dev

在本仓库新增或修改工具时使用本 skill。先读 AGENTS.md，再看同类型的目标工具和对应 spec，不从零臆造结构。

## 开发范围

- API 文档由 public/tool/app/api-docs/catalog/ 驱动，接口事实以 catalog 和 HTTP probe reference 为准。
- Python 工具页面位于 public/tool/app/<tool>/，源码位于 src/tool/app/<tool>/，每个 APP 可独立分发。
- SOC 随机置位只由 soc-positioning skill 维护，不加入 csn2api 首页，也不与 IEB Cookie 或接口事实混用。

## 实现原则

- 业务规则写入 spec/dev/<tool>/，用户操作写入 spec/user/<tool>/manual.md，不要把业务事实写进 skill。
- 代码、测试、文档同步维护；任一处仍描述旧工具或旧品牌，任务就未完成。
- 业务逻辑与页面渲染分开，稳定逻辑直接导入 src/ 测试。
- 页面接入共享 theme.js、theme.css；专属 CSS 只维护布局和领域特判。
- Cookie、真实响应和生产写操作不写入仓库；没有授权时只运行本地脱敏测试。

## 验证

修改后按范围运行局部测试，并在收尾执行：

    npm.cmd run build
    npm.cmd run typecheck
    npm.cmd test
    npm.cmd run verify

PowerShell 中使用 npm.cmd 和 npx.cmd。构建失败时修复源代码、入口清单、静态文件或依赖闭包，不从旧 dist/ 回填源码。

## 提交

- 提交前检查 git status --short，只包含当前任务文件。
- 不提交真实业务数据、Cookie、临时探测输出、dist/ 或无关变更。
- 提交信息使用简体中文单段落。
