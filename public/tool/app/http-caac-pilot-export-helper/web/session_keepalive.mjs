export function formatKeepAliveStatus(status) {
  return status?.running ? "保活运行中" : `保活${status?.state || "未启动"}`;
}
