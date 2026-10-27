# 首页图案验证开发规格

`src/site-visibility.ts` 的 `homepage.patternGate` 当前为 `false`，首页直接显示工具。开启后先显示九宫格图案验证，验证完成前首页内容不可操作。图案为九宫格最下面三个点连成横线，左右两个方向均可；快速跨过中间点时自动补齐中间点。

图案验证只用于降低随手访问，不提供真实身份认证，也不保护公开静态资源。`src/site-visibility.ts` 中的 `homepage.patternGate` 控制是否显示门禁，`src/tool/home-pattern-gate-logic.ts` 中的 `HOME_ACCESS_PATTERN` 保存图案序列。

页面支持鼠标拖动、触摸拖动和键盘选择。错误图案清空后可重试，正确图案解除首页的 `inert` 状态并关闭遮罩。
