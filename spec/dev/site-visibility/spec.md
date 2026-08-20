# 站点入口可见性开发规格

`src/site-visibility.ts` 只维护首页图案门禁开关。该开关控制入口遮罩，不提供权限或安全隔离。

工具目录不经过可见性开关过滤，`src/tool/tools-data.ts` 中的全部工具直接进入首页列表。

工具名称和说明由 `src/tool/tools-data.ts` 维护；工具内部业务规则的 `enabled` 不属于此配置。
