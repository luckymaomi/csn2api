# 文档维护与合并下载

## 内容归属

`spec/README.md` 提供阅读顺序，`system/` 说明架构、重建和验收边界，`dev/<entry>/` 维护业务输入、规则、状态、输出和模块职责，`user/<entry>/manual.md` 维护实际操作。API 请求字段、条件和响应只在 catalog 完整维护；合并时复用 `public/tool/app/api-docs/markdown-export.mjs` 生成 API 正文及原始声明契约附录。

业务变更同时更新实现、核心测试和对应 dev/user；新增 APP 同步目录与系统声明；catalog 变更由已有全部消费者和协议合同验证。文档记录当前可确认行为，来源不明的接口事实、聊天过程和未来承诺不作为规格。

## 合并合同

首页“下载开发文档”下载构建生成的 `downloads/csn2api-development-documentation.md`，保存为 `csn2api开发者文档-YYYY-MM-DD.md`。日期是下载当天浏览器本地日历日，页面初始化及点击时更新，跨夜页面也使用点击当天。正文为中文 UTF-8 无 BOM 的单个 Markdown。

`scripts/documentation-export.mts` 动态发现 `spec/` 下所有受版本管理和新增未忽略的 Markdown；Git 忽略的本地文件不参与扫描，尤其是 `cookies.local.md`。扫描不是固定逐篇白名单。`spec/README.md` 在前，其余按路径排序，最后从 catalog index 及其全部引用模块生成 API 段落。JSON 模板和构建测量文件不直接拼接；API 原始声明附录用于保留有业务意义的条件字段和协议事实。

每篇保留来源路径和正文。目录、篇内标题与相对文档链接使用唯一锚点；外链及代码围栏示例保留。损坏 UTF-8、BOM、断开的文档链接、模块引用越界或 catalog ID 不一致导致构建失败。正文不写源码提交号、摘要、字节表或当前时间；生成全文只在 dist，不作为另一份源文档提交。

浏览器直接下载静态产物，不合并 APP 文档、不读取 Session。API 页原有“导出 Markdown”保留为 API 专用导出，从当前已加载 catalog 生成单文件；它不包含 APP 手册，独立 API 调试器也不依赖首页合并文档。

## 生成与一致性检查

```powershell
npm.cmd run build
npm.cmd test
npm.cmd run verify
```

这些标准命令均构建并重新扫描文档。`test:unit`、`test:tool`、`test:smoke` 和 `test:watch` 也有构建前置；watch 只在启动时构建，后续文档变化需重启或另跑 build。直接运行 Vitest 或 `test:python` 是局部验证，不重新生成全文。

推送 master 后，`.github/workflows/deploy-pages.yml` 先执行完整 verify，生成并检查合并文档。仓库已启用 GitHub Pages 时，文档与 APP 一起上传发布；未启用时跳过发布，验证仍执行。测试动态检查工具 dev/user 覆盖、当前 API 端点覆盖、相对链接、编码、Git 忽略和下载日期；确定性双构建检查包含文档在内的输出一致。

该门禁检查文档覆盖及工程合同，不自动证明全部业务语义正确或生产请求有效。具体核对证据与剩余边界见[规格核对](alignment.md)。
