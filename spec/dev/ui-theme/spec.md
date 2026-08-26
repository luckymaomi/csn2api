# 全站 UI 主题规格

除根跳转页外，所有公开 UI 页面加载 `public/theme.js` 和 `public/theme.css`。首次访问默认白天模式，用户选择保存在浏览器本地；白天和暗夜共用相同的组件语义，只替换全局 token 值。

`public/theme.css` 是背景、表面、文字、边框、焦点、状态色、点缀色、硬阴影、圆角和 Bootstrap 变量的唯一公共来源。首页、支持页、备忘录、赞助页和各工具页面的 CSS 只维护布局、尺寸、滚动、canvas、文档预览及领域组件特判，不重复定义同义公共主题值。

Python 工作台入口页和独立服务页面加载 Bootstrap、`public/theme.css`、`public/theme.js` 及页面专属样式。构建过程从 `src/tool/app/http-*-helper/shell.ts` 动态发现工作台入口并复制公共资源；合同测试从工具清单和 `public/tool/app/http-*-helper/web/index.html` 动态发现独立页面，检查详情下载入口、ZIP 资源闭包、主题引用、标准保活模块、凭据区、结果区和可打断滚动跟随。各工作台服务测试按 Python 包目录动态导入 `create_server`，通过实际 HTTP 请求确认标准保活模块可达。

工作台保活倒计时使用 `public/tool/app/_shared/session_keepalive.mjs` 作为标准来源。源码 APP 保留相同的本地副本，构建时由标准来源覆盖到每个独立分发包；具体系统只维护自己的保活请求和会话失效判断。

通用视觉使用浅灰表面、方角完整边框、无模糊硬阴影和轻量位移反馈。状态通过完整边框、整体浅色背景和文字色表达，不使用彩色 `border-left`、`border-right`、伪元素侧条、status rail 或 accent stripe。

以下边线属于结构或图标语义，可以保留：表格单元格的中性灰网格、密集分段控件的中性灰分隔线、双栏工作区的中性灰分隔线、复选框勾选和折叠箭头的图标几何。它们不得承载彩色状态强调。

PDF/Word 预览可以保持白纸和深色正文，以准确表达文档内容；canvas、拖拽手柄和裁剪区域可以保留交互所需的定位边框。换季图表系列色和身份色相属于数据编码，由页面专属 token 管理；其他表面、边框和状态继续消费全局 token。
