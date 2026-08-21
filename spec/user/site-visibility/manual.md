# 站点入口显示配置

站点维护者只需编辑 `src/site-visibility.ts`：

- `homepage.patternGate` 控制首页图案门禁。

工具清单不使用显示开关，`src/tool/tools-data.ts` 中登记的 HTTP 工具会直接进入首页。页面级配置用于整理入口呈现，不是权限控制。
