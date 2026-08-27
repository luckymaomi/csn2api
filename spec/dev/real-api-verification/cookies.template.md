# 真实接口验收凭据

只在本机填写，不要提交真实 Cookie。脚本读取每个 `##` 段落的原始文本，并交给对应系统已有的凭据解析器；不要改写 Cookie 值，也不要把 cURL 当作命令执行。

## 验收参数

以下字段同样只填写在被 Git 忽略的 `cookies.local.md`。人员身份、日期、资格代码和写操作对象不固化在脚本中。

```json
{
  "iebStaffNumber": "",
  "iebStaffName": "",
  "flightStartDate": "",
  "flightEndDate": "",
  "iebRosterQualification": "",
  "iebMonitorQualification": "",
  "lockStaffNumber": "",
  "lockType": "",
  "lockStartDate": "",
  "lockEndDate": "",
  "lockRemark": "",
  "caacPilotName": ""
}
```

## IEB

在此粘贴飞行门户已登录请求的完整 `Copy as cURL`，或 `Cookie: ...` Header。必须包含当前有效的 `JSESSIONID` 和 `iebJSid`。

## OA

在此粘贴 OA 待办 `POST /oai/work/box/query/waiting` 的完整 `Copy as cURL`。必须包含 `SESSION`，建议保留完整 User-Agent、Referer、Origin 和待办 JSON 模板。

## CAAC

在此粘贴 CAAC 人员列表已登录请求的完整 `Copy as cURL`，或包含 `yzzzm`、`JSESSIONID`、`home` 的 Cookie Header。

## SOC

当前脚本不执行 SOC。SOC 需要按 `soc-positioning` 规约单独确认真实测试和写操作边界。
