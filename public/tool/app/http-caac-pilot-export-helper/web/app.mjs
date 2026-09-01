import { createResultTable } from "./results_table.mjs";

const elements = {
  statusMessage: document.querySelector("#statusMessage"),
  statusBadge: document.querySelector("#statusBadge"),
  themeToggle: document.querySelector("#themeToggle"),
  credentials: document.querySelector("#credentials"),
  verifyButton: document.querySelector("#verifyButton"),
  sessionStatus: document.querySelector("#sessionStatus"),
  serverTotal: document.querySelector("#serverTotal"),
  sessionVerifiedAt: document.querySelector("#sessionVerifiedAt"),
  cookieCount: document.querySelector("#cookieCount"),
  sessionIdentity: document.querySelector("#sessionIdentity"),
  keepAliveRing: document.querySelector("#keepAliveRing"),
  keepAliveCountdown: document.querySelector("#keepAliveCountdown"),
  keepAliveStatus: document.querySelector("#keepAliveStatus"),
  keepAliveDetail: document.querySelector("#keepAliveDetail"),
  savedCredentialsPanel: document.querySelector("#savedCredentialsPanel"),
  savedCredentials: document.querySelector("#savedCredentials"),
  copyCredentialsButton: document.querySelector("#copyCredentialsButton"),
  allModePanel: document.querySelector("#allModePanel"),
  selectedModePanel: document.querySelector("#selectedModePanel"),
  allModeTotal: document.querySelector("#allModeTotal"),
  excelFile: document.querySelector("#excelFile"),
  dataCheckButton: document.querySelector("#dataCheckButton"),
  runButton: document.querySelector("#runButton"),
  stopButton: document.querySelector("#stopButton"),
  dataCheckResult: document.querySelector("#dataCheckResult"),
  dataCheckErrors: document.querySelector("#dataCheckErrors"),
  progress: document.querySelector(".progress"),
  progressBar: document.querySelector("#progressBar"),
  progressText: document.querySelector("#progressText"),
  totalCount: document.querySelector("#totalCount"),
  completedCount: document.querySelector("#completedCount"),
  successCount: document.querySelector("#successCount"),
  failedCount: document.querySelector("#failedCount"),
  currentRecord: document.querySelector("#currentRecord"),
  excelDownload: document.querySelector("#excelDownload"),
  logList: document.querySelector("#logList"),
};

const phaseLabels = {
  waiting_credentials: "待验证",
  verifying_credentials: "验证中",
  credentials_ready: "凭据有效",
  data_checked: "数据已检查",
  running: "抓取中",
  stopping: "停止中",
  completed: "已完成",
  terminated: "已停止",
  session_expired: "会话失效",
  failed: "失败",
};

let keepAliveTimer = () => ({ active: false, total: 0, remaining: 0 });
let renderKeepAlive = () => undefined;
let savedCredentials = "";
let currentState = {};
let followLog = true;
let lastLogsSignature = "";
let lastRunId = "";
const resultTable = createResultTable(showActionError);

void import("./session_keepalive.mjs")
  .then((module) => {
    keepAliveTimer = module.createKeepAliveTimer();
    renderKeepAlive = module.renderKeepAlive;
    return pollStatus();
  })
  .catch(() => {
    elements.keepAliveRing.hidden = true;
    elements.keepAliveStatus.textContent = "保活组件加载失败";
    elements.keepAliveDetail.textContent = "核心功能仍可使用，请重新下载安装包";
    showActionError(new Error("保活状态组件加载失败，核心功能仍可使用"));
  });

function isNearBottom(element) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 24;
}

function currentMode() {
  return document.querySelector('input[name="runMode"]:checked')?.value || "all";
}

function updateSavedCredentials(value) {
  savedCredentials = String(value || "");
  elements.savedCredentials.value = savedCredentials;
  elements.savedCredentialsPanel.hidden = !savedCredentials;
}

async function copyCurrentCredentials() {
  if (!savedCredentials) return;
  try {
    await navigator.clipboard.writeText(savedCredentials);
    elements.statusMessage.textContent = "当前页凭据已复制";
  } catch (_error) {
    showActionError(new Error("复制失败，请手动选择当前页凭据"));
  }
}

function syncMode() {
  const selected = currentMode() === "selected";
  elements.allModePanel.hidden = selected;
  elements.selectedModePanel.hidden = !selected;
  elements.dataCheckButton.hidden = !selected;
  syncControls();
}

function syncControls() {
  const selected = currentMode() === "selected";
  const hasFile = Boolean(elements.excelFile.files[0]);
  elements.dataCheckButton.disabled = !currentState.canCheckData || !selected || !hasFile;
  elements.runButton.disabled = !currentState.canRun || (selected && !hasFile);
  elements.stopButton.disabled = !currentState.canStop;
  document.querySelectorAll('input[name="runMode"]').forEach((input) => {
    input.disabled = Boolean(currentState.canStop);
  });
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("读取 Excel 文件失败"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}

async function buildPayload() {
  const mode = currentMode();
  const payload = { mode, excelName: "", excelBase64: "" };
  if (mode === "selected") {
    const file = elements.excelFile.files[0];
    if (!file) throw new Error("请选择 Excel 名单");
    payload.excelName = file.name;
    payload.excelBase64 = await readFileAsBase64(file);
  }
  return payload;
}

async function postJson(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `请求失败：HTTP ${response.status}`);
  return data;
}

async function verifyCredentials() {
  const credentials = elements.credentials.value.trim();
  if (!credentials) throw new Error("请粘贴登录凭据");
  const state = await postJson("./api/session/verify", { credentials });
  updateSavedCredentials(state.credentials);
  elements.credentials.value = "";
  renderState(state);
}

async function checkData() {
  renderState(await postJson("./api/check-data", await buildPayload()));
}

async function startRun() {
  followLog = true;
  resultTable.followLatest();
  renderState(await postJson("./api/run", await buildPayload()));
}

function renderCheck(check = {}) {
  const summary = elements.dataCheckResult.querySelector("strong");
  if (!check.checked) {
    elements.dataCheckResult.className = "health-check";
    summary.textContent = "尚未检查";
  } else {
    elements.dataCheckResult.className = `health-check ${check.ok ? "is-ok" : "is-error"}`;
    summary.textContent = `有效 ${check.validCount || 0}，无效 ${check.invalidCount || 0}`;
  }
  const errors = check.errors || [];
  elements.dataCheckErrors.hidden = errors.length === 0;
  elements.dataCheckErrors.replaceChildren(...errors.map((message) => {
    const item = document.createElement("li");
    item.textContent = message;
    return item;
  }));
}

function renderLogs(logs = []) {
  const signature = JSON.stringify(logs);
  if (signature === lastLogsSignature) return;
  lastLogsSignature = signature;
  const previousTop = elements.logList.scrollTop;
  if (!logs.length) {
    const item = document.createElement("li");
    item.className = "is-muted";
    item.textContent = "尚无运行记录";
    elements.logList.replaceChildren(item);
  } else {
    elements.logList.replaceChildren(...logs.map((log) => {
      const item = document.createElement("li");
      item.className = `is-${log.level || "info"}`;
      item.textContent = `${log.time ? `[${log.time}] ` : ""}${log.message || ""}`;
      return item;
    }));
  }
  elements.logList.scrollTop = followLog ? elements.logList.scrollHeight : previousTop;
}

function setDownload(enabled) {
  elements.excelDownload.classList.toggle("disabled", !enabled);
  elements.excelDownload.setAttribute("aria-disabled", enabled ? "false" : "true");
  if (enabled) elements.excelDownload.href = "./api/download";
  else elements.excelDownload.removeAttribute("href");
}

function renderState(state) {
  currentState = state;
  const phase = state.phase || "waiting_credentials";
  const session = state.session || {};
  const progress = state.progress || {};
  const total = Number(progress.total || 0);
  const completed = Number(progress.completed || 0);
  const percent = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  if (!session.verified || phase === "session_expired") updateSavedCredentials("");
  if (state.runId && state.runId !== lastRunId) {
    lastRunId = state.runId;
    resultTable.reset();
  }

  elements.statusMessage.textContent = state.message || "";
  elements.statusBadge.textContent = phaseLabels[phase] || phase;
  elements.statusBadge.className = `status-badge is-${phase}`;
  elements.sessionStatus.textContent = session.verified ? "已验证" : "尚未验证";
  elements.serverTotal.textContent = state.totalFromServer || "-";
  elements.allModeTotal.textContent = state.totalFromServer || "-";
  elements.sessionVerifiedAt.textContent = session.verifiedAt || "-";
  elements.cookieCount.textContent = String(session.cookieCount || 0);
  elements.sessionIdentity.textContent = session.verified ? session.identity?.name || "未识别" : "-";
  renderKeepAlive(
    { ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail },
    session,
    keepAliveTimer,
  );

  elements.credentials.disabled = !state.canVerify;
  elements.verifyButton.disabled = !state.canVerify;
  syncControls();
  elements.progressBar.style.width = `${percent}%`;
  elements.progress.setAttribute("aria-valuenow", String(percent));
  elements.progressText.textContent = `${completed} / ${total}`;
  elements.totalCount.textContent = String(total);
  elements.completedCount.textContent = String(completed);
  elements.successCount.textContent = String(progress.success || 0);
  elements.failedCount.textContent = String(progress.failed || 0);
  elements.currentRecord.textContent = progress.current || "-";
  renderCheck(state.checks?.data || {});
  renderLogs(state.logs || []);
  setDownload(Boolean(state.downloads?.excel));

  void resultTable.render(state.resultTable || {}).catch(showActionError);
}

function showActionError(error) {
  elements.statusMessage.textContent = error.message || String(error);
  elements.statusBadge.textContent = "操作失败";
  elements.statusBadge.className = "status-badge is-failed";
}

async function pollStatus() {
  try {
    const response = await fetch("./api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderState(await response.json());
  } catch (error) {
    showActionError(new Error(`状态连接失败：${error.message || error}`));
  }
}

document.querySelectorAll('input[name="runMode"]').forEach((input) => input.addEventListener("change", syncMode));
elements.excelFile.addEventListener("change", syncControls);
elements.verifyButton.addEventListener("click", () => verifyCredentials().catch(showActionError));
elements.copyCredentialsButton.addEventListener("click", () => copyCurrentCredentials());
elements.dataCheckButton.addEventListener("click", () => checkData().catch(showActionError));
elements.runButton.addEventListener("click", () => startRun().catch(showActionError));
elements.stopButton.addEventListener("click", () => postJson("./api/stop").then(renderState).catch(showActionError));
elements.themeToggle.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
elements.logList.addEventListener("scroll", () => { followLog = isNearBottom(elements.logList); });

syncMode();
pollStatus();
window.setInterval(pollStatus, 800);
