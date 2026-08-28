RUNTIME_CSS = """
.csn2api-runtime-strip{display:flex;min-height:42px;align-items:center;justify-content:space-between;gap:16px;padding:8px 14px;border:0;border-bottom:2px solid var(--soft-border);background:var(--soft-surface);color:var(--soft-muted);font:600 12px/1.4 \"Microsoft YaHei UI\",sans-serif;position:relative;z-index:10000}
.csn2api-runtime-actions{display:flex;align-items:center;gap:8px}
.csn2api-runtime-strip button,.csn2api-runtime-strip a{display:inline-flex;min-height:30px;align-items:center;padding:4px 12px;border:2px solid var(--soft-border);background:var(--soft-surface);color:var(--soft-ink);cursor:pointer;text-decoration:none}
.csn2api-runtime-strip button:hover,.csn2api-runtime-strip a:hover{background:var(--soft-sky);color:var(--soft-on-pastel)}
.csn2api-lan-workbench label[for="credentials"],.csn2api-lan-workbench #credentials,.csn2api-lan-workbench #verifyButton,.csn2api-lan-workbench #savedCredentialsPanel{display:none!important}
@media(max-width:640px){.csn2api-runtime-strip{align-items:flex-start;flex-direction:column}.csn2api-runtime-actions{width:100%;flex-wrap:wrap}}
""".strip()

RUNTIME_JS = """
(() => {
  window.Csn2ApiRuntime = { mode: "lan" };
  const isApiDocs = window.location.pathname.startsWith("/api-docs/");
  if (!isApiDocs) document.body.classList.add("csn2api-lan-workbench");
  const bar = document.createElement("div");
  bar.className = "csn2api-runtime-strip";
  bar.innerHTML = '<span>正在读取当前使用状态</span><div class="csn2api-runtime-actions"><a href="/api-docs/" data-cookie-management>Cookie 管理</a><button type="button" data-lease-action>读取中</button></div>';
  document.body.prepend(bar);
  if (isApiDocs) bar.querySelector("[data-cookie-management]")?.remove();
  const credentialHeading = document.querySelector("#credentialHeading, .credential-panel h2");
  if (!isApiDocs && credentialHeading) credentialHeading.textContent = "1. Cookie 状态";
  const status = bar.querySelector("span");
  const action = bar.querySelector("[data-lease-action]");
  let current = null;
  const requestJson = async (path, method = "GET") => {
    const response = await fetch(path, { method, cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `请求返回 HTTP ${response.status}`);
    return payload;
  };
  const render = (value) => {
    current = value;
    if (!value?.occupied) {
      status.textContent = "当前无人使用";
      action.textContent = "开始使用";
      action.dataset.mode = "takeover";
    } else if (value.youOwn) {
      status.textContent = `当前由你的 IP ${value.ownerIp} 使用`;
      action.textContent = value.busy ? "任务运行中" : "结束使用";
      action.dataset.mode = "release";
      action.disabled = value.busy === true;
    } else {
      status.textContent = `当前由 IP ${value.ownerIp} 使用`;
      action.textContent = "接管使用";
      action.dataset.mode = "takeover";
    }
    if (action.dataset.mode !== "release" || value.busy !== true) action.disabled = false;
  };
  const refresh = async () => render(await requestJson("/__runtime__/status"));
  action.addEventListener("click", async () => {
    try {
      const release = action.dataset.mode === "release";
      const path = release ? "/__runtime__/release" : "/__runtime__/takeover";
      render(await requestJson(path, "POST"));
      if (release) window.location.href = "/tool/";
    } catch (error) {
      status.textContent = error.message || String(error);
    }
  });
  const heartbeat = async () => {
    try {
      if (current?.youOwn) await requestJson("/__runtime__/heartbeat", "POST");
      await refresh();
    } catch (_error) {}
  };
  void refresh();
  window.setInterval(heartbeat, 15000);
})();
""".strip()

__all__ = ["RUNTIME_CSS", "RUNTIME_JS"]
