const elements = {
  statusMessage: document.querySelector("#statusMessage"),
  statusBadge: document.querySelector("#statusBadge"),
  themeToggle: document.querySelector("#themeToggle"),
  credentials: document.querySelector("#credentials"),
  verifyButton: document.querySelector("#verifyButton"),
  savedCredentialsPanel: document.querySelector("#savedCredentialsPanel"),
  savedCredentials: document.querySelector("#savedCredentials"),
  copyCredentialsButton: document.querySelector("#copyCredentialsButton"),
  sessionStatus: document.querySelector("#sessionStatus"),
  sessionVerified: document.querySelector("#sessionVerified"),
  sessionVerifiedAt: document.querySelector("#sessionVerifiedAt"),
  sessionIdentity: document.querySelector("#sessionIdentity"),
  keepAliveRing: document.querySelector("#keepAliveRing"),
  keepAliveCountdown: document.querySelector("#keepAliveCountdown"),
  keepAliveStatus: document.querySelector("#keepAliveStatus"),
  keepAliveDetail: document.querySelector("#keepAliveDetail"),
  cookieCount: document.querySelector("#cookieCount"),
  scanButton: document.querySelector("#scanButton"),
  scanTotal: document.querySelector("#scanTotal"),
  eligibleCount: document.querySelector("#eligibleCount"),
  skippedCount: document.querySelector("#skippedCount"),
  scanState: document.querySelector("#scanState"),
  categoryRows: document.querySelector("#categoryRows"),
  finiteMode: document.querySelector("#finiteMode"),
  allMode: document.querySelector("#allMode"),
  maxCount: document.querySelector("#maxCount"),
  targetPreview: document.querySelector("#targetPreview"),
  runButton: document.querySelector("#runButton"),
  stopButton: document.querySelector("#stopButton"),
  progress: document.querySelector(".progress"),
  progressBar: document.querySelector("#progressBar"),
  progressText: document.querySelector("#progressText"),
  runTotal: document.querySelector("#runTotal"),
  completedCount: document.querySelector("#completedCount"),
  successCount: document.querySelector("#successCount"),
  failedCount: document.querySelector("#failedCount"),
  currentRecord: document.querySelector("#currentRecord"),
  resultsCount: document.querySelector("#resultsCount"),
  resultsViewport: document.querySelector("#resultsViewport"),
  resultRows: document.querySelector("#resultRows"),
  logList: document.querySelector("#logList"),
};

let keepAliveTimer = () => ({ active: false, total: 0, remaining: 0 });
let renderKeepAlive = () => undefined;

void import("./session_keepalive.mjs")
  .then((keepAliveModule) => {
    keepAliveTimer = keepAliveModule.createKeepAliveTimer();
    renderKeepAlive = keepAliveModule.renderKeepAlive;
    return refreshStatus();
  })
  .catch(() => {
    elements.keepAliveRing.hidden = true;
    elements.keepAliveStatus.textContent = "保活组件加载失败";
    elements.keepAliveDetail.textContent = "核心功能仍可使用，请重新下载安装包";
    showLocalError(new Error("保活状态组件加载失败，核心功能仍可使用"));
  });
const phaseLabels = {
  waiting_credentials: "待验证",
  verifying_credentials: "验证中",
  credentials_ready: "凭据有效",
  scanning: "扫描中",
  scan_ready: "可执行",
  running: "已阅中",
  stopping: "终止中",
  completed: "已完成",
  terminated: "已终止",
  session_expired: "会话失效",
  failed: "失败",
};

let lastResultsSignature = "";
let lastLogsSignature = "";
let followResults = true;
let followLogs = true;
let pollingErrorShown = false;
let savedCredentials = "";

function updateSavedCredentials(value) {
  savedCredentials = String(value || "");
  elements.savedCredentials.value = savedCredentials;
  elements.savedCredentialsPanel.hidden = !savedCredentials;
}

async function copySavedCredentials() {
  if (!savedCredentials) return;
  try {
    await navigator.clipboard.writeText(savedCredentials);
    elements.statusMessage.textContent = "当前页 Cookie 已复制";
  } catch (_error) {
    showLocalError(new Error("复制失败，请手动选择当前页 Cookie"));
  }
}
let latestEligibleCount = 0;

elements.themeToggle.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
elements.verifyButton.addEventListener("click", async () => {
  const credentials = elements.credentials.value.trim();
  if (!credentials) return showLocalError("请粘贴 cURL 或 Cookie Header");
  updateSavedCredentials("");
  try {
    const state = await postJson("./api/session/verify", { credentials });
    updateSavedCredentials(state.credentials);
    elements.credentials.value = "";
    render(state);
  } catch (error) {
    showLocalError(error);
  }
});
elements.copyCredentialsButton.addEventListener("click", () => copySavedCredentials());
elements.scanButton.addEventListener("click", () => invoke("./api/scan", {}));
elements.finiteMode.addEventListener("change", updateTargetPreview);
elements.allMode.addEventListener("change", updateTargetPreview);
elements.maxCount.addEventListener("input", updateTargetPreview);
elements.runButton.addEventListener("click", async () => {
  const maxCount = elements.maxCount.value.trim();
  if (!/^[1-9]\d*$/.test(maxCount)) {
    return showLocalError("本次数量必须是正整数");
  }
  try {
    await postJson("./api/run", {
      maxCount,
      runMode: elements.allMode.checked ? "all" : "finite",
    });
    await refreshStatus();
  } catch (error) {
    showLocalError(error);
  }
});
elements.stopButton.addEventListener("click", () => invoke("./api/stop", {}));
elements.resultsViewport.addEventListener("scroll", () => {
  followResults = isNearBottom(elements.resultsViewport);
});
elements.logList.addEventListener("scroll", () => {
  followLogs = isNearBottom(elements.logList);
});

async function invoke(path, payload) {
  try {
    await postJson(path, payload);
    await refreshStatus();
  } catch (error) {
    showLocalError(error);
  }
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败：${response.status}`);
  return data;
}

async function refreshStatus() {
  try {
    const response = await fetch("./api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`状态请求失败：${response.status}`);
    render(await response.json());
    pollingErrorShown = false;
  } catch (error) {
    if (!pollingErrorShown) showLocalError(error);
    pollingErrorShown = true;
  }
}

function render(state) {
  const phase = state.phase || "waiting_credentials";
  const session = state.session || {};
  const scan = state.scan || {};
  const progress = state.progress || {};
  const total = Number(progress.total || 0);
  const completed = Number(progress.completed || 0);
  const percent = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  if (!session.verified || phase === "session_expired") updateSavedCredentials("");

  elements.statusMessage.textContent = state.message || "";
  elements.statusBadge.textContent = phaseLabels[phase] || phase;
  elements.statusBadge.className = `status-badge is-${phase}`;
  elements.sessionStatus.textContent = session.verified ? "当前 Session 可用" : "尚未验证";
  elements.sessionVerified.textContent = session.verified ? "有效" : "未验证";
  elements.sessionVerifiedAt.textContent = session.verifiedAt || "-";
  const identity = session.identity || {};
  elements.sessionIdentity.textContent = session.verified
    ? [identity.staffNumber, identity.name].filter(Boolean).join(" · ") || "未识别"
    : "-";
  renderKeepAlive({ ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail }, session, keepAliveTimer);
  elements.cookieCount.textContent = String(session.cookieCount || 0);

  elements.verifyButton.disabled = !state.canVerify;
  elements.scanButton.disabled = !state.canScan;
  elements.runButton.disabled = !state.canRun;
  elements.stopButton.disabled = !state.canStop;
  const running = Boolean(state.canStop);
  elements.maxCount.disabled = running;
  elements.finiteMode.disabled = running;
  elements.allMode.disabled = running;
  elements.credentials.disabled = running;

  elements.scanTotal.textContent = String(scan.total || 0);
  elements.eligibleCount.textContent = String(scan.eligibleCount || 0);
  elements.skippedCount.textContent = String(scan.skippedCount || 0);
  elements.scanState.textContent = scan.current ? "当前有效" : scan.scanned ? "需重新扫描" : "未扫描";
  renderCategories(scan.categories || []);
  latestEligibleCount = Number(scan.eligibleCount || 0);
  updateTargetPreview();

  elements.progressBar.style.width = `${percent}%`;
  elements.progress.setAttribute("aria-valuenow", String(percent));
  elements.progressText.textContent = `${completed} / ${total}`;
  elements.runTotal.textContent = String(total);
  elements.completedCount.textContent = String(completed);
  elements.successCount.textContent = String(progress.success || 0);
  elements.failedCount.textContent = String(progress.failed || 0);
  elements.currentRecord.textContent = progress.current || "-";
  renderResults(state.results || []);
  renderLogs(state.logs || []);
  elements.savedCredentials.value = savedCredentials;
  elements.savedCredentialsPanel.hidden = !savedCredentials;
}

function renderCategories(categories) {
  if (!categories.length) {
    elements.categoryRows.innerHTML = '<tr class="empty-row"><td colspan="5">尚无扫描结果</td></tr>';
    return;
  }
  elements.categoryRows.replaceChildren(...categories.map((category) => {
    const row = document.createElement("tr");
    row.className = category.eligible ? "is-eligible" : "is-skipped";
    appendCells(row, [category.category, category.categoryName, category.count, category.action, category.sampleTitle]);
    row.children[2].className = "number-column";
    row.children[3].className = category.eligible ? "is-success" : "is-muted";
    return row;
  }));
}

function renderResults(results) {
  const signature = JSON.stringify(results);
  elements.resultsCount.textContent = `${results.length} 条`;
  if (signature === lastResultsSignature) return;
  lastResultsSignature = signature;
  const previousTop = elements.resultsViewport.scrollTop;
  if (!results.length) {
    elements.resultRows.innerHTML = '<tr class="empty-row"><td colspan="5">尚无已阅结果</td></tr>';
    return;
  }
  elements.resultRows.replaceChildren(...results.map((result) => {
    const row = document.createElement("tr");
    appendCells(row, [result.title, result.category, result.categoryName, result.status, result.message]);
    row.children[3].className = result.status === "成功" ? "is-success" : "is-failed";
    return row;
  }));
  window.requestAnimationFrame(() => {
    elements.resultsViewport.scrollTop = followResults ? elements.resultsViewport.scrollHeight : previousTop;
  });
}

function renderLogs(logs) {
  const signature = JSON.stringify(logs);
  if (signature === lastLogsSignature) return;
  lastLogsSignature = signature;
  const previousTop = elements.logList.scrollTop;
  if (!logs.length) {
    elements.logList.innerHTML = '<li class="is-muted">尚无运行记录</li>';
  } else {
    elements.logList.replaceChildren(...logs.map((entry) => {
      const item = document.createElement("li");
      item.className = `is-${entry.level || "info"}`;
      item.textContent = `${entry.time || ""} ${entry.message || ""}`.trim();
      return item;
    }));
  }
  elements.logList.scrollTop = followLogs ? elements.logList.scrollHeight : previousTop;
}

function appendCells(row, values) {
  for (const value of values) {
    const cell = document.createElement("td");
    cell.textContent = String(value ?? "");
    row.append(cell);
  }
}

function isNearBottom(element) {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= 24;
}

function showLocalError(error) {
  const item = document.createElement("li");
  item.className = "is-error";
  item.textContent = error instanceof Error ? error.message : String(error);
  if (elements.logList.querySelector(".is-muted")) elements.logList.replaceChildren();
  elements.logList.append(item);
  if (followLogs) elements.logList.scrollTop = elements.logList.scrollHeight;
}

function updateTargetPreview() {
  const value = elements.maxCount.value.trim();
  const requested = /^[1-9]\d*$/.test(value) ? BigInt(value) : 0n;
  const eligible = BigInt(latestEligibleCount);
  const target = elements.allMode.checked
    ? latestEligibleCount
    : Number(requested < eligible ? requested : eligible);
  elements.maxCount.disabled = elements.allMode.checked || elements.stopButton.disabled === false;
  elements.targetPreview.textContent = elements.allMode.checked
    ? `无限模式将处理当前扫描中的全部 ${latestEligibleCount} 条同类公文`
    : `指定数量模式将处理 ${target} 条同类公文`;
}

await postJson("./api/session/clear", {}).catch(() => undefined);
await refreshStatus();
window.setInterval(refreshStatus, 800);
