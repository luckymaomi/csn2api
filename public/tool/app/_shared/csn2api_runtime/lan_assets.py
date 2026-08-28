RUNTIME_CSS = """
.csn2api-runtime-strip{display:flex;min-height:42px;align-items:center;justify-content:space-between;gap:16px;padding:8px 14px;border:0;border-bottom:2px solid var(--soft-border);background:var(--soft-surface);color:var(--soft-muted);font:600 12px/1.4 \"Microsoft YaHei UI\",sans-serif;position:relative;z-index:10000}
.csn2api-runtime-actions{display:flex;align-items:center;gap:8px}
.csn2api-runtime-strip button{min-height:30px;padding:4px 12px;border:2px solid var(--soft-border);background:var(--soft-surface);color:var(--soft-ink);cursor:pointer}
.csn2api-runtime-strip button:hover{background:var(--soft-sky);color:var(--soft-on-pastel)}
@media(max-width:640px){.csn2api-runtime-strip{align-items:flex-start;flex-direction:column}.csn2api-runtime-actions{width:100%;flex-wrap:wrap}}
""".strip()

RUNTIME_JS = """
(() => {
  window.Csn2ApiRuntime = { mode: "lan" };
  const bar = document.createElement("div");
  bar.className = "csn2api-runtime-strip";
  bar.innerHTML = '<span>局域网工作台使用中</span><div class="csn2api-runtime-actions"><input type="file" accept=".json,.txt,application/json,text/plain" hidden><button type="button" data-action="import">导入 Cookie</button><button type="button" data-action="export">导出 Cookie</button><button type="button" data-action="release">结束使用</button></div>';
  document.body.prepend(bar);
  if (window.location.pathname.startsWith("/api-docs/")) {
    bar.querySelector('[data-action="import"]').remove();
    bar.querySelector('[data-action="export"]').remove();
  }
  const status = bar.querySelector("span");
  const fileInput = bar.querySelector("input");
  const requestJson = async (method, body) => {
    const response = await fetch("/__runtime__/credentials", {
      method,
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `请求返回 HTTP ${response.status}`);
    return payload;
  };
  const heartbeat = () => fetch("/__runtime__/heartbeat", { method: "POST", cache: "no-store" }).catch(() => undefined);
  bar.querySelector('[data-action="import"]')?.addEventListener("click", () => fileInput.click());
  fileInput?.addEventListener("change", async () => {
    try {
      const file = fileInput.files[0];
      if (!file) return;
      const result = await requestJson("POST", JSON.parse(await file.text()));
      status.textContent = result.failed?.length
        ? `Cookie 已导入，${result.failed.length} 个工作台验证失败`
        : `Cookie 已导入 ${result.imported?.length || 0} 个系统`;
    } catch (error) {
      status.textContent = error.message || String(error);
    } finally {
      fileInput.value = "";
    }
  });
  bar.querySelector('[data-action="export"]')?.addEventListener("click", async () => {
    try {
      const bundle = await requestJson("GET");
      if (!bundle.systems?.length) throw new Error("当前没有可导出的有效 Cookie");
      const url = URL.createObjectURL(new Blob([`${JSON.stringify(bundle, null, 2)}\n`], { type: "application/json;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `csn2api-cookies-${new Date().toISOString().slice(0, 19).replace(/[:T-]/g, "")}.json`;
      link.click();
      URL.revokeObjectURL(url);
      status.textContent = `已导出 ${bundle.systems.length} 个系统 Cookie`;
    } catch (error) {
      status.textContent = error.message || String(error);
    }
  });
  bar.querySelector('[data-action="release"]').addEventListener("click", async () => {
    const response = await fetch("/__runtime__/release", { method: "POST", cache: "no-store" });
    if (response.ok) window.location.href = "/tool/index.html";
    else status.textContent = "当前任务运行中，完成或停止后才能结束使用";
  });
  heartbeat();
  window.setInterval(heartbeat, 15000);
})();
""".strip()

__all__ = ["RUNTIME_CSS", "RUNTIME_JS"]
