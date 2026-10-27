# csn2api 文档目录

## 阅读顺序

1. [系统架构](system/architecture.md)：运行形态、数据流、职责和跨系统边界。
2. [从零重建与验收](system/reconstruction.md)：实现顺序、依赖、行为样例和恢复边界。
3. [规格核对与证据](system/alignment.md)：各 APP、API 与当前代码/测试的对应关系及未验证范围。
4. [文档维护与合并下载](system/documentation.md)：正文归属、自动生成与交付合同。
5. [局域网运行规格](dev/lan-runtime/spec.md)与[使用手册](user/lan-runtime/manual.md)：统一入口和应用生命周期。

开发规格负责业务规则、输入输出和职责；用户手册负责操作。完整生产接口参数、响应和执行链由 `public/tool/app/api-docs/catalog/index.json` 及引用的模块 JSON 维护，合并文档末尾从该目录生成完整 API 文档。APP 的本地路由与生产接口属于两层不同契约。

## APP

| APP | 开发规格 | 用户手册 |
| --- | --- | --- |
| 飞行经历时间查询 | [规格](dev/http-flight-history-helper/spec.md) | [手册](user/http-flight-history-helper/manual.md) |
| 锁班皇帝（新） | [规格](dev/http-lock-entry-helper/spec.md) | [手册](user/http-lock-entry-helper/manual.md) |
| 飞行经历查询（皇帝版） | [规格](dev/http-flight-stats-helper/spec.md) | [手册](user/http-flight-stats-helper/manual.md) |
| 航班明细查询（皇帝版） | [规格](dev/http-flight-detail-helper/spec.md) | [手册](user/http-flight-detail-helper/manual.md) |
| 飞行人员信息查询（皇帝版） | [规格](dev/http-qualification-query-helper/spec.md) | [手册](user/http-qualification-query-helper/manual.md) |
| 训练安排查询（HTTP版） | [规格](dev/http-training-arrangement-helper/spec.md) | [手册](user/http-training-arrangement-helper/manual.md) |
| 运行资质人员名册 | [规格](dev/http-qualification-roster-helper/spec.md) | [手册](user/http-qualification-roster-helper/manual.md) |
| OA 已阅助手（HTTP版） | [规格](dev/http-oa-read-helper/spec.md) | [手册](user/http-oa-read-helper/manual.md) |
| 资质监控（皇帝版） | [规格](dev/http-qualification-monitor-helper/spec.md) | [手册](user/http-qualification-monitor-helper/manual.md) |
| CAAC 飞行员信息导出 | [规格](dev/http-caac-pilot-export-helper/spec.md) | [手册](user/http-caac-pilot-export-helper/manual.md) |
| SOC 随机置位批量助手 | [规格](dev/http-soc-positioning-helper/spec.md) | [手册](user/http-soc-positioning-helper/manual.md) |

## API 与公共能力

| 能力 | 开发规格 | 用户手册 |
| --- | --- | --- |
| API 文档与调试器 | [规格](dev/api-docs/spec.md)、[目录编写](dev/api-docs/catalog-authoring.md) | [手册](user/api-docs/manual.md) |
| 万能查询机器接口 | [规格](dev/universal-query/spec.md) | [手册](user/universal-query/manual.md) |
| 首页与独立下载 | [规格](dev/tool-index/spec.md) | [手册](user/tool-index/manual.md) |
| 局域网运行 | [规格](dev/lan-runtime/spec.md) | [手册](user/lan-runtime/manual.md) |
| 首页图案门禁 | [规格](dev/home-pattern-gate/spec.md) | [手册](user/home-pattern-gate/manual.md) |
| 入口可见性 | [规格](dev/site-visibility/spec.md) | [手册](user/site-visibility/manual.md) |
| 主题 | [规格](dev/ui-theme/spec.md) | 由各页面操作手册说明 |
| 构建分发 | [交付说明](dev/esm-delivery/README.md) | 由各 APP 启动说明覆盖 |
| 真实验收 | [说明](dev/real-api-verification/README.md)、[空凭据模板](dev/real-api-verification/cookies.template.md) | 需按真实调用对象授权执行 |
