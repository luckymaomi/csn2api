<div align="center">

# csn2api

[项目主页](https://luckymaomi.github.io/csn2api/) · [API 文档](https://luckymaomi.github.io/csn2api/tool/app/api-docs/) · [GitHub](https://github.com/luckymaomi/csn2api)

<p>
  <a href="https://github.com/luckymaomi/csn2api/actions/workflows/deploy-pages.yml"><img alt="Deploy Pages" src="https://img.shields.io/github/actions/workflow/status/luckymaomi/csn2api/deploy-pages.yml?branch=master&logo=githubactions&logoColor=white&label=Pages"></a>
  <a href="https://www.typescriptlang.org/"><img alt="TypeScript 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6"></a>
  <a href="https://www.python.org/"><img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB"></a>
  <a href="https://vitest.dev/"><img alt="Vitest 4" src="https://img.shields.io/badge/Vitest-4-6E9F18"></a>
  <img alt="Static local-first" src="https://img.shields.io/badge/Architecture-static%20local--first-0f766e">
  <a href="./LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/luckymaomi/csn2api?color=0f766e"></a>
</p>
</div>

## 当前工具

状态：✅ 已启用 · 🧪 Beta 测试 · 🧊 冷却中

<!-- tools-table:start -->
| 工具 | 状态 | 功能 |
| --- | --- | --- |
| 飞行经历时间查询 | 🧪 | 输入员工号和姓名，批量导出飞行经历时间页的汇总、年度和月份全部数据。 |
| 锁班皇帝（新） | 🧪 | 好活，直接调用接口锁班，极速。 |
| 飞行经历查询（皇帝版） | 🧪 | 好活，直接调用接口查完整飞行经历和起落数，极速。 |
| 航班明细查询（皇帝版） | 🧪 | 按员工和自然月读取 IEB 逐航班明细，保留人工飞行方式。 |
| 飞行人员信息查询（皇帝版） | 🧪 | 好活，哈哈。直接调用 IEB 接口查询基础信息、技术等级、运行资格和训练检查记录。 |
| 训练安排查询（HTTP版） | 🧪 | 查询 IEB 已结束训练安排，支持单类别和区域默认配置一键汇总导出。 |
| 运行资质人员名册 | 🧪 | 按门户动态运行资格逐项查询人员，并合并为四列名册。 |
| OA 已阅助手（HTTP版） | 🧪 | 扫描全部 OA 待办，按指定数量或无限模式逐条处理可点击的公文已阅。 |
| 资质监控（皇帝版） | 🧪 | 直接调用 IEB 原生导出，按三类资质严格串行获取全部独立 Excel。 |
| CAAC 飞行员信息导出 | 🧪 | 支持全量或按 Excel 名单抓取飞行员详情，并保存为单 Sheet Excel。 |
| SOC 随机置位批量助手 | 🧪 | 导入航班执行申请表，按当前 SOC 动态航班逐条提交随机置位申请。 |
<!-- tools-table:end -->

## 开源协议与贡献

开发规格、用户手册和重建说明见[文档目录](spec/README.md)。首页“下载开发文档”提供构建时合并的 APP 与 API 单文件 Markdown。

本项目遵循 [MIT License](./LICENSE) 开源协议。

欢迎提交 Issue 或 Pull Request 改进工具、修复问题、补充文档。贡献前建议先阅读 [贡献指南](./CONTRIBUTING.md)，并尽量说明问题场景、输入样例、期望结果和验证方式。

## 目前

服务于：南货航飞行部、中国南方航空货运有限公司。
