const $ = (id) => document.querySelector(`#${id}`);
const state = { payload: null, timer: null };
const elements = {
  credentials: $("credentials"),
  verify: $("verifyButton"),
  check: $("checkButton"),
  run: $("runButton"),
  stop: $("stopButton"),
  file: $("excelFile"),
  paste: $("pasteText"),
  excelBox: $("excelBox"),
  pasteBox: $("pasteBox"),
  status: $("statusMessage"),
  badge: $("statusBadge"),
  session: $("sessionStatus"),
  verifiedAt: $("verifiedAt"),
  cookieCount: $("cookieCount"),
  identity: $("sessionIdentity"),
  keepAliveRing: $("keepAliveRing"),
  keepAliveCountdown: $("keepAliveCountdown"),
  keepAliveStatus: $("keepAliveStatus"),
  keepAliveDetail: $("keepAliveDetail"),
  savedPanel: $("savedCredentialsPanel"),
  saved: $("savedCredentials"),
  result: $("checkResult"),
  errors: $("checkErrors"),
  logs: $("logList"),
  resultsViewport: $("resultsViewport"),
  table: $("resultsTable"),
  empty: $("empty"),
  count: $("resultCount"),
  download: $("download"),
};

let keepAliveTimer = () => ({ active: false, total: 0, remaining: 0 });
let renderKeepAlive = () => undefined;
let followLogs = true;
let followResults = true;

void import("./session_keepalive.mjs")
  .then((module) => {
    keepAliveTimer = module.createKeepAliveTimer();
    renderKeepAlive = module.renderKeepAlive;
    return refresh();
  })
  .catch(() => {
    elements.keepAliveStatus.textContent = "保活组件加载失败";
    elements.keepAliveDetail.textContent = "核心功能仍可使用，请重新下载安装包";
    return refresh();
  });

function isNearBottom(element) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 24;
}

async function api(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "本地服务请求失败");
  return value;
}

function setStatus(value) {
  const phase = value.phase || "waiting_credentials";
  const phaseLabel = {
    credentials_ready: "凭据有效",
    data_checked: "已检查",
    running: "录入中",
    completed: "已完成",
    terminated: "已终止",
    session_expired: "会话失效",
  };
  elements.status.textContent = value.message || "";
  elements.badge.textContent = phaseLabel[phase] || "待验证";
  elements.badge.className = `badge text-bg-${phase === "completed" || phase === "credentials_ready" ? "success" : phase === "failed" || phase === "session_expired" ? "danger" : "secondary"}`;
  const session = value.session || {};
  const identity = session.identity || {};
  elements.session.textContent = session.verified ? "已验证" : "尚未验证";
  elements.verifiedAt.textContent = session.verifiedAt || "-";
  elements.cookieCount.textContent = session.cookieCount || 0;
  elements.identity.textContent = session.verified ? identity.name || "未识别" : "-";
  elements.verify.disabled = value.canVerify === false;
  elements.check.disabled = !value.canCheckData;
  elements.run.disabled = !value.canRun;
  elements.stop.disabled = !value.canStop;
  if (!session.verified) {
    elements.saved.value = "";
    elements.savedPanel.hidden = true;
  }
}

function render(value) {
  setStatus(value);
  renderKeepAlive(
    { ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail },
    value.session || {},
    keepAliveTimer,
  );
  const progress = value.progress || {};
  const total = Number(progress.total || 0);
  const completed = Number(progress.completed || 0);
  $("progressText").textContent = `${completed} / ${total}`;
  $("progressBar").style.width = `${total ? Math.round(completed / total * 100) : 0}%`;
  $("total").textContent = total;
  $("completed").textContent = completed;
  $("success").textContent = progress.success || 0;
  $("failed").textContent = progress.failed || 0;

  const downloadable = Boolean(value.downloads?.result);
  elements.download.classList.toggle("disabled", !downloadable);
  elements.download.setAttribute("aria-disabled", String(!downloadable));

  const previousResultTop = elements.resultsViewport.scrollTop;
  const results = value.results || [];
  elements.count.textContent = `${results.length} 条`;
  elements.empty.hidden = results.length > 0;
  elements.table.hidden = results.length === 0;
  elements.table.querySelector("tbody").replaceChildren(...results.map((result) => {
    const row = document.createElement("tr");
    [
      result["来源行"],
      result["员工号"],
      result["姓名"],
      `${result["出发地"]} → ${result["目的地"]}`,
      result["航班号"],
      result["申请原因"],
      result["状态"],
      result["说明"],
    ].forEach((text) => {
      const cell = document.createElement("td");
      cell.textContent = text || "";
      row.append(cell);
    });
    return row;
  }));
  elements.resultsViewport.scrollTop = followResults ? elements.resultsViewport.scrollHeight : previousResultTop;

  const previousLogTop = elements.logs.scrollTop;
  const logs = value.logs || [];
  elements.logs.replaceChildren(...(logs.length ? logs : [{ message: "尚无运行记录" }]).map((entry) => {
    const item = document.createElement("li");
    item.textContent = entry.time ? `[${entry.time}] ${entry.message}` : entry.message;
    return item;
  }));
  elements.logs.scrollTop = followLogs ? elements.logs.scrollHeight : previousLogTop;

  const check = value.checks || {};
  if (check.checked) {
    elements.result.textContent = `有效 ${check.validCount || 0} 条，无效 ${check.invalidCount || 0} 条`;
    elements.errors.hidden = !check.errors?.length;
    elements.errors.replaceChildren(...(check.errors || []).map((error) => {
      const item = document.createElement("li");
      item.textContent = error;
      return item;
    }));
  }
}

async function refresh() {
  try {
    const response = await fetch("./api/status", { cache: "no-store" });
    render(await response.json());
  } catch (_error) {
    // The next poll restores the local status connection.
  }
}

function payload() {
  return state.payload || { inputMode: "paste", pastedText: elements.paste.value };
}

async function readFile() {
  const file = elements.file.files?.[0];
  if (!file) throw new Error("请选择 Excel 文件");
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return { inputMode: "excel", excelName: file.name, excelBase64: btoa(binary) };
}

$("themeToggle")?.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
document.querySelectorAll('input[name="inputMode"]').forEach((input) => input.addEventListener("change", () => {
  const excel = $("excelMode").checked;
  elements.excelBox.hidden = !excel;
  elements.pasteBox.hidden = excel;
  state.payload = null;
}));
elements.verify.addEventListener("click", async () => {
  try {
    const value = await api("./api/session/verify", { credentials: elements.credentials.value });
    render(value);
    if (value.credentials) {
      elements.saved.value = value.credentials;
      elements.savedPanel.hidden = false;
    }
  } catch (error) {
    alert(error.message);
    await refresh();
  }
});
elements.copyCredentialsButton = $("copyCredentialsButton");
elements.copyCredentialsButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(elements.saved.value);
});
elements.check.addEventListener("click", async () => {
  try {
    state.payload = $("excelMode").checked ? await readFile() : { inputMode: "paste", pastedText: elements.paste.value };
    render(await api("./api/check-data", state.payload));
  } catch (error) {
    alert(error.message);
  }
});
elements.run.addEventListener("click", async () => {
  try {
    if (!state.payload) state.payload = $("excelMode").checked ? await readFile() : { inputMode: "paste", pastedText: elements.paste.value };
    followLogs = true;
    followResults = true;
    render(await api("./api/run", state.payload));
  } catch (error) {
    alert(error.message);
  }
});
elements.stop.addEventListener("click", async () => { render(await api("./api/stop")); });
elements.download.addEventListener("click", () => {
  if (!elements.download.classList.contains("disabled")) window.location.href = "./api/download/result";
});
elements.logs.addEventListener("scroll", () => { followLogs = isNearBottom(elements.logs); });
elements.resultsViewport.addEventListener("scroll", () => { followResults = isNearBottom(elements.resultsViewport); });

state.timer = window.setInterval(refresh, 1000);
refresh();
