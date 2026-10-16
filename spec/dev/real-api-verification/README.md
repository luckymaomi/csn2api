# 真实接口验收

`scripts/real-api-verification.py` 是仓库内可重复的真实 HTTP 验收入口。它读取本地 Cookie 与验收参数，调用 API 文档使用的执行器，并通过各独立 APP 的 `127.0.0.1` HTTP 路由执行页面对应操作。每个 APP Case 会实际请求首页声明的 Bootstrap、共享主题、页面样式、前端脚本和标准保活模块，再检查前端绑定路由、真实后端路由和生产 protocol core；任一运行资源未挂载时在生产业务请求前失败。完成后关闭临时服务并清理临时结果。

复制 `cookies.template.md` 为被 Git 忽略的 `cookies.local.md`，填写验收参数以及需要执行的系统 Cookie。Cookie、真实身份、原始响应和业务结果不会写入仓库。

默认执行 API 文档与独立 APP 的只读 Case：

```powershell
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md
```

可按系统或入口单独执行，适合失效后只补跑相应 Case：

```powershell
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system ieb --scope api
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system ieb --scope app
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system oa --scope both
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system caac --scope both
```

每个业务模块可单独执行；`--case` 可重复填写：

`flight-history` 用于完整飞行经历时间页，使用员工号和姓名，可通过本地参数 `flightHistoryExpectedTime` 核对汇总飞行时间。该 Case 比较 API、APP 粘贴、Excel 输入及导出文件的全部行列，执行后检查临时端口释放。

```powershell
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system ieb --scope both --case flight-stats
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system ieb --scope both --case personnel-info
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system ieb --scope both --case qualification-roster
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system ieb --scope both --case qualification-monitor
python -X utf8 scripts/real-api-verification.py --cookies-file spec/dev/real-api-verification/cookies.local.md --system ieb --scope app --case lock-entry
```

本轮写操作需要显式确认。锁班会严格执行“提交待审批 -> 通过 -> 回查已锁”两步，只有两步都成功才算通过；OA 已阅最多提交一条。脚本不会自动撤销锁班，也不会继续派发 OA：

```powershell
python -X utf8 scripts/real-api-verification.py `
  --cookies-file spec/dev/real-api-verification/cookies.local.md `
  --allow-write `
  --lock-confirmation '<员工号>|<类型>|<开始日期>|<结束日期>|<备注>' `
  --oa-read-count 1
```

锁班确认串必须与本地验收参数逐项完全一致。API 与 APP 同时验收时，同一系统的写额度只会被一个入口消耗；另一个入口只做真实只读或提交前检查，避免重复写入。

脚本在会话失效、登录重定向、响应契约变化导致无法归属或业务结果不明确时停止该系统后续请求；普通单项失败会记录并继续其他 Case。SOC 不包含在此入口中。

代码按职责组织：

- `real_verification/common.py`：凭据段落、验收参数、脱敏与结果摘要。
- `real_verification/runner.py`：系统和入口编排、停止边界、写额度与汇总。
- `real_verification/app_http.py`：独立 APP loopback 服务、前端路由检查与状态轮询。
- `real_verification/ieb/`：飞行经历、人员信息、资质名册、资质监控和锁班分别维护。
- `real_verification/oa_cases.py`、`caac_cases.py`：各系统 API/APP 真实 Case。
