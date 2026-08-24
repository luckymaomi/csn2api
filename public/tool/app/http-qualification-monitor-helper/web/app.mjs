const elements = {
  statusMessage: document.querySelector("#statusMessage"),
  statusBadge: document.querySelector("#statusBadge"),
  themeToggle: document.querySelector("#themeToggle"),
  credentials: document.querySelector("#credentials"),
  verifyButton: document.querySelector("#verifyButton"),
  sessionStatus: document.querySelector("#sessionStatus"),
  sessionVerified: document.querySelector("#sessionVerified"),
  sessionVerifiedAt: document.querySelector("#sessionVerifiedAt"),
  keepAliveRing: document.querySelector("#keepAliveRing"),
  keepAliveCountdown: document.querySelector("#keepAliveCountdown"),
  keepAliveStatus: document.querySelector("#keepAliveStatus"),
  keepAliveDetail: document.querySelector("#keepAliveDetail"),
  groupCount: document.querySelector("#groupCount"),
  qualificationCount: document.querySelector("#qualificationCount"),
  exportAllButton: document.querySelector("#exportAllButton"),
  stopButton: document.querySelector("#stopButton"),
  currentItem: document.querySelector("#currentItem"),
  archiveDownload: document.querySelector("#archiveDownload"),
  progress: document.querySelector(".progress"),
  progressBar: document.querySelector("#progressBar"),
  progressText: document.querySelector("#progressText"),
  totalCount: document.querySelector("#totalCount"),
  completedCount: document.querySelector("#completedCount"),
  successCount: document.querySelector("#successCount"),
  failedCount: document.querySelector("#failedCount"),
  loadedCount: document.querySelector("#loadedCount"),
  qualificationGroups: document.querySelector("#qualificationGroups"),
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
  verifying: "验证中",
  ready: "可执行",
  exporting: "导出中",
  stopping: "停止中",
  stopped: "已停止",
  partial_failure: "部分失败",
  completed: "已完成",
  session_expired: "会话失效",
  failed: "失败",
};

const itemLabels = {
  pending: "等待",
  running: "导出中",
  success: "成功",
  failed: "失败",
};

let lastGroupSignature = "";
let lastLogSignature = "";
let followLogs = true;
let pollingFailed = false;

function nearBottom(element) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 20;
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

function showActionError(error) {
  elements.statusMessage.textContent = error.message || String(error);
  elements.statusBadge.textContent = "操作失败";
  elements.statusBadge.className = "status-badge is-failed";
}

async function verify() {
  const credentials = elements.credentials.value.trim();
  if (!credentials) throw new Error("请粘贴登录 Cookie");
  elements.verifyButton.disabled = true;
  try {
    const state = await postJson("/api/session/verify", { credentials });
    elements.credentials.value = "";
    renderState(state);
  } finally {
    elements.verifyButton.disabled = false;
  }
}

async function exportAll() {
  renderState(await postJson("/api/export/all"));
}

async function exportOne(code) {
  renderState(await postJson("/api/export/one", { qualType: code }));
}

async function stopExport() {
  renderState(await postJson("/api/stop"));
}

function setDownload(link, fileId) {
  const enabled = Boolean(fileId);
  link.classList.toggle("disabled", !enabled);
  link.setAttribute("aria-disabled", enabled ? "false" : "true");
  if (enabled) link.href = `/api/download/${encodeURIComponent(fileId)}`;
  else link.removeAttribute("href");
}

function renderGroups(groups = [], items = [], busy = false) {
  const signature = JSON.stringify([groups, items, busy]);
  if (signature === lastGroupSignature) return;
  lastGroupSignature = signature;
  if (!groups.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "验证 Cookie 后加载当前资质分类";
    elements.qualificationGroups.replaceChildren(empty);
    return;
  }
  const states = new Map(items.map((item) => [item.code, item]));
  elements.qualificationGroups.replaceChildren(...groups.map((group) => {
    const section = document.createElement("section");
    section.className = "qualification-group";
    const heading = document.createElement("div");
    heading.className = "group-heading";
    const title = document.createElement("h3");
    title.textContent = group.name;
    const count = document.createElement("span");
    count.textContent = `${group.items.length} 项`;
    heading.append(title, count);
    const viewport = document.createElement("div");
    viewport.className = "qualification-viewport";
    const table = document.createElement("table");
    table.className = "qualification-table";
    table.innerHTML = "<thead><tr><th>资质子类</th><th>代码</th><th>状态</th><th>操作</th></tr></thead>";
    const body = document.createElement("tbody");
    group.items.forEach((definition) => {
      const state = states.get(definition.code) || { status: "pending" };
      const row = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = definition.name;
      const code = document.createElement("td");
      code.className = "code-cell";
      code.textContent = definition.code;
      const status = document.createElement("td");
      status.className = `item-status is-${state.status || "pending"}`;
      status.textContent = itemLabels[state.status] || state.status || "等待";
      if (state.error) status.title = state.error;
      const actions = document.createElement("td");
      actions.className = "row-actions";
      const exportButton = document.createElement("button");
      exportButton.type = "button";
      exportButton.className = "btn btn-outline-secondary btn-sm";
      exportButton.textContent = "导出";
      exportButton.disabled = busy;
      exportButton.addEventListener("click", () => exportOne(definition.code).catch(showActionError));
      actions.append(exportButton);
      if (state.downloadId) {
        const download = document.createElement("a");
        download.className = "btn btn-outline-secondary btn-sm";
        download.textContent = "下载";
        download.href = `/api/download/${encodeURIComponent(state.downloadId)}`;
        actions.append(download);
      }
      row.append(name, code, status, actions);
      body.append(row);
    });
    table.append(body);
    viewport.append(table);
    section.append(heading, viewport);
    return section;
  }));
}

function renderLogs(logs = []) {
  const signature = JSON.stringify(logs);
  if (signature === lastLogSignature) return;
  lastLogSignature = signature;
  if (!logs.length) {
    const empty = document.createElement("li");
    empty.className = "is-muted";
    empty.textContent = "尚无运行记录";
    elements.logList.replaceChildren(empty);
    return;
  }
  elements.logList.replaceChildren(...logs.map((log) => {
    const item = document.createElement("li");
    item.className = `is-${log.level || "info"}`;
    item.textContent = `${log.time ? `[${log.time}] ` : ""}${log.message || ""}`;
    return item;
  }));
  if (followLogs) elements.logList.scrollTop = elements.logList.scrollHeight;
}

function renderState(state) {
  const phase = state.phase || "waiting_credentials";
  const session = state.session || {};
  const groups = state.groups || [];
  const items = state.items || [];
  const progress = state.progress || {};
  const total = Number(progress.total || 0);
  const completed = Number(progress.completed || 0);
  const percent = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const busy = ["verifying", "exporting", "stopping"].includes(phase);
  const ready = Boolean(session.verified) && !busy;

  elements.statusMessage.textContent = state.error || (session.verified ? "会话已验证，可导出当前资质" : "等待验证飞行门户 Cookie");
  elements.statusBadge.textContent = phaseLabels[phase] || phase;
  elements.statusBadge.className = `status-badge is-${phase}`;
  elements.sessionStatus.textContent = session.verified ? "已验证" : "尚未验证";
  elements.sessionVerified.textContent = session.verified ? "有效" : "未验证";
  elements.sessionVerifiedAt.textContent = session.verifiedAt || "-";
  renderKeepAlive({ ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail }, session, keepAliveTimer);
  elements.groupCount.textContent = `${groups.length} 类`;
  elements.qualificationCount.textContent = `${session.qualificationCount || 0} 项`;
  elements.loadedCount.textContent = groups.length ? `${groups.length} 类 / ${session.qualificationCount || 0} 项` : "尚未加载";
  elements.verifyButton.disabled = busy;
  elements.credentials.disabled = busy;
  elements.exportAllButton.disabled = !ready;
  elements.stopButton.disabled = !["exporting", "stopping"].includes(phase);
  elements.currentItem.textContent = state.current?.name || "-";
  elements.progressBar.style.width = `${percent}%`;
  elements.progress.setAttribute("aria-valuenow", String(percent));
  elements.progressText.textContent = `${completed} / ${total}`;
  elements.totalCount.textContent = String(total);
  elements.completedCount.textContent = String(completed);
  elements.successCount.textContent = String(progress.success || 0);
  elements.failedCount.textContent = String(progress.failed || 0);
  setDownload(elements.archiveDownload, state.downloads?.archiveId);
  renderGroups(groups, items, busy);
  renderLogs(state.logs || []);
}

async function pollStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderState(await response.json());
    pollingFailed = false;
  } catch (error) {
    if (!pollingFailed) showActionError(new Error(`状态连接失败：${error.message || error}`));
    pollingFailed = true;
  }
}

elements.verifyButton.addEventListener("click", () => verify().catch(showActionError));
elements.exportAllButton.addEventListener("click", () => exportAll().catch(showActionError));
elements.stopButton.addEventListener("click", () => stopExport().catch(showActionError));
elements.themeToggle.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
elements.logList.addEventListener("scroll", () => { followLogs = nearBottom(elements.logList); });

pollStatus();
window.setInterval(pollStatus, 800);
