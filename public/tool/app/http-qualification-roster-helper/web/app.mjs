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
  qualificationCount: document.querySelector("#qualificationCount"),
  sessionIdentity: document.querySelector("#sessionIdentity"),
  keepAliveRing: document.querySelector("#keepAliveRing"),
  keepAliveCountdown: document.querySelector("#keepAliveCountdown"),
  keepAliveStatus: document.querySelector("#keepAliveStatus"),
  keepAliveDetail: document.querySelector("#keepAliveDetail"),
  filterFields: document.querySelector("#filterFields"),
  qualificationSearch: document.querySelector("#qualificationSearch"),
  qualificationList: document.querySelector("#qualificationList"),
  selectedQualificationCount: document.querySelector("#selectedQualificationCount"),
  selectDefaultsButton: document.querySelector("#selectDefaultsButton"),
  clearQualificationsButton: document.querySelector("#clearQualificationsButton"),
  selectedFilterSummary: document.querySelector("#selectedFilterSummary"),
  runButton: document.querySelector("#runButton"),
  stopButton: document.querySelector("#stopButton"),
  excelDownload: document.querySelector("#excelDownload"),
  progress: document.querySelector(".progress"),
  progressBar: document.querySelector("#progressBar"),
  progressText: document.querySelector("#progressText"),
  totalCount: document.querySelector("#totalCount"),
  completedCount: document.querySelector("#completedCount"),
  successCount: document.querySelector("#successCount"),
  failedCount: document.querySelector("#failedCount"),
  relationshipCount: document.querySelector("#relationshipCount"),
  currentRecord: document.querySelector("#currentRecord"),
  resultsCount: document.querySelector("#resultsCount"),
  resultsViewport: document.querySelector("#resultsViewport"),
  resultsEmpty: document.querySelector("#resultsEmpty"),
  resultsTable: document.querySelector("#resultsTable"),
  logList: document.querySelector("#logList"),
};

const phaseLabels = {
  waiting_credentials: "待验证", verifying: "验证中", ready: "可执行", querying: "查询中",
  stopping: "停止中", stopped: "已停止", partial_failure: "部分失败", completed: "已完成",
  session_expired: "会话失效", failed: "失败",
};

let keepAliveTimer = () => ({ active: false, total: 0, remaining: 0 });
let renderKeepAlive = () => undefined;
let savedCredentials = "";
let qualifications = [];
let lastMetadataSignature = "";
let lastResultSignature = "";
let lastLogSignature = "";
let followResults = true;
let followLogs = true;
let pollingFailed = false;

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

function updateSavedCredentials(value) {
  savedCredentials = String(value || "");
  elements.savedCredentials.value = savedCredentials;
  elements.savedCredentialsPanel.hidden = !savedCredentials;
}

async function verify() {
  const value = elements.credentials.value.trim();
  if (!value) throw new Error("请粘贴登录 Cookie");
  updateSavedCredentials("");
  elements.verifyButton.disabled = true;
  try {
    const state = await postJson("/api/session/verify", { credentials: value });
    updateSavedCredentials(state.credentials);
    elements.credentials.value = "";
    renderState(state);
  } finally {
    elements.verifyButton.disabled = false;
  }
}

function selectedValues(name) {
  const field = document.querySelector(`[data-filter-name="${CSS.escape(name)}"]`);
  if (!field) return [];
  if (field.type === "checkbox") return field.checked ? [field.value] : [];
  if (field.multiple) return [...field.selectedOptions].map((option) => option.value).filter(Boolean);
  return field.value ? [field.value] : [];
}

function readFilters() {
  const values = {};
  document.querySelectorAll("[data-filter-name]").forEach((field) => {
    const name = field.dataset.filterName;
    if (!name) return;
    if (field.type === "checkbox") values[name] = field.checked;
    else if (field.multiple) values[name] = [...field.selectedOptions].map((option) => option.value).filter(Boolean);
    else values[name] = field.value || "";
  });
  return values;
}

function renderFilterFields(fields = []) {
  if (!fields.length) {
    elements.filterFields.innerHTML = '<div class="empty-state">验证 Cookie 后加载筛选项</div>';
    return;
  }
  elements.filterFields.replaceChildren(...fields.map((field) => {
    const wrapper = document.createElement("div");
    wrapper.className = "filter-field";
    const label = document.createElement("label");
    label.textContent = field.label;
    const select = document.createElement("select");
    select.className = "form-select";
    select.dataset.filterName = field.name;
    select.multiple = Boolean(field.multiple);
    select.size = field.multiple ? Math.min(4, Math.max(2, field.options.length)) : 1;
    field.options.forEach((option) => {
      const item = document.createElement("option");
      item.value = option.value;
      item.textContent = option.label || option.value || "请选择";
      select.append(item);
    });
    if (field.name === "fleetCdToArray") {
      [...select.options].filter((option) => option.value === "777").forEach((option) => { option.selected = true; });
    }
    if (field.name === "activeStatusArray") {
      [...select.options].forEach((option) => { option.selected = ["ZAIZHI", "WAIBU", "TUIXIU", "LIZHI"].includes(option.value); });
    }
    select.addEventListener("change", updateSelectionSummary);
    wrapper.append(label, select);
    return wrapper;
  }));
  updateSelectionSummary();
}

function renderQualifications(items = []) {
  qualifications = items;
  if (!items.length) {
    elements.qualificationList.innerHTML = '<div class="empty-state">验证 Cookie 后加载动态运行资格</div>';
    return;
  }
  elements.qualificationList.replaceChildren(...items.map((item) => {
    const row = document.createElement("label");
    row.className = "qualification-row";
    row.dataset.code = item.code;
    row.dataset.search = `${item.code} ${item.name} ${item.typeName}`.toLowerCase();
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = item.code;
    checkbox.dataset.qualificationCode = item.code;
    checkbox.checked = Boolean(item.defaultSelected);
    checkbox.addEventListener("change", updateSelectionSummary);
    const code = document.createElement("strong");
    code.className = "qualification-code";
    code.textContent = item.code;
    const name = document.createElement("span");
    name.className = "qualification-name";
    name.textContent = item.name || "未提供中文描述";
    const type = document.createElement("span");
    type.className = "qualification-type";
    type.textContent = item.typeName || item.typeCode || "";
    row.append(checkbox, code, name, type);
    return row;
  }));
  filterQualifications();
  updateSelectionSummary();
}

function filterQualifications() {
  const query = elements.qualificationSearch.value.trim().toLowerCase();
  document.querySelectorAll(".qualification-row").forEach((row) => {
    row.hidden = Boolean(query) && !row.dataset.search.includes(query);
  });
}

function selectedQualificationCodes() {
  return [...document.querySelectorAll("[data-qualification-code]:checked")].map((input) => input.value);
}

function updateSelectionSummary() {
  const codes = selectedQualificationCodes();
  elements.selectedQualificationCount.textContent = `${codes.length} 项已选`;
  const fleet = selectedValues("fleetCdToArray");
  const status = selectedValues("activeStatusArray");
  elements.selectedFilterSummary.textContent = `机型 ${fleet.join(", ") || "未选"} · 状态 ${status.length} 项 · 资质 ${codes.length} 项`;
  elements.runButton.disabled = !codes.length || !document.querySelector("#sessionVerified")?.textContent.includes("有效");
}

function renderResults(rows = []) {
  const signature = JSON.stringify(rows);
  if (signature === lastResultSignature) return;
  lastResultSignature = signature;
  elements.resultsCount.textContent = `${rows.length} 条`;
  if (!rows.length) {
    elements.resultsEmpty.hidden = false;
    elements.resultsTable.hidden = true;
    return;
  }
  elements.resultsEmpty.hidden = true;
  elements.resultsTable.hidden = false;
  elements.resultsTable.querySelector("thead").innerHTML = "<tr><th>序号</th><th>员工号</th><th>姓名</th><th>资质类别</th></tr>";
  const body = elements.resultsTable.querySelector("tbody");
  body.replaceChildren(...rows.map((row) => {
    const tr = document.createElement("tr");
    [row.sequence, row.staffNumber, row.name, row.qualificationCode].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = String(value ?? "");
      tr.append(td);
    });
    return tr;
  }));
  if (followResults) elements.resultsViewport.scrollTop = elements.resultsViewport.scrollHeight;
}

function renderLogs(logs = []) {
  const signature = JSON.stringify(logs);
  if (signature === lastLogSignature) return;
  lastLogSignature = signature;
  if (!logs.length) {
    elements.logList.innerHTML = '<li class="is-muted">尚无运行记录</li>';
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

function setDownload(enabled) {
  elements.excelDownload.classList.toggle("disabled", !enabled);
  elements.excelDownload.setAttribute("aria-disabled", enabled ? "false" : "true");
  if (enabled) elements.excelDownload.href = "/api/download/excel";
  else elements.excelDownload.removeAttribute("href");
}

function renderState(state) {
  const phase = state.phase || "waiting_credentials";
  const session = state.session || {};
  const progress = state.progress || {};
  const total = Number(progress.total || 0);
  const completed = Number(progress.completed || 0);
  const busy = ["verifying", "querying", "stopping"].includes(phase);
  const percent = total ? Math.min(100, Math.round(completed * 100 / total)) : 0;
  if (!session.verified || phase === "session_expired") updateSavedCredentials("");
  elements.statusMessage.textContent = state.error || (session.verified ? "会话已验证，可选择运行资质" : "等待验证飞行门户 Cookie");
  elements.statusBadge.textContent = phaseLabels[phase] || phase;
  elements.statusBadge.className = `status-badge is-${phase}`;
  elements.sessionStatus.textContent = session.verified ? "已验证" : "尚未验证";
  elements.sessionVerified.textContent = session.verified ? "有效" : "未验证";
  elements.sessionVerifiedAt.textContent = session.verifiedAt || "-";
  elements.qualificationCount.textContent = `${(state.qualifications || []).length} 项`;
  const identity = session.identity || {};
  elements.sessionIdentity.textContent = session.verified ? [identity.staffNumber, identity.name].filter(Boolean).join(" · ") || "未识别" : "-";
  renderKeepAlive({ ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail }, session, keepAliveTimer);
  const metadataSignature = JSON.stringify([state.filterFields || [], state.qualifications || []]);
  if (metadataSignature !== lastMetadataSignature) {
    lastMetadataSignature = metadataSignature;
    renderFilterFields(state.filterFields || []);
    renderQualifications(state.qualifications || []);
  }
  elements.credentials.disabled = busy;
  elements.verifyButton.disabled = busy;
  elements.selectDefaultsButton.disabled = !session.verified || busy;
  elements.clearQualificationsButton.disabled = !session.verified || busy;
  elements.stopButton.disabled = !["querying", "stopping"].includes(phase);
  elements.currentRecord.textContent = state.current?.code ? `${state.current.code} · ${state.current.name || ""}` : "-";
  elements.progressBar.style.width = `${percent}%`;
  elements.progress.setAttribute("aria-valuenow", String(percent));
  elements.progressText.textContent = `${completed} / ${total}`;
  elements.totalCount.textContent = String(total);
  elements.completedCount.textContent = String(completed);
  elements.successCount.textContent = String(progress.success || 0);
  elements.failedCount.textContent = String(progress.failed || 0);
  elements.relationshipCount.textContent = String(progress.relationships || 0);
  setDownload(Boolean(state.download?.ready));
  renderResults(state.results || []);
  renderLogs(state.logs || []);
  updateSelectionSummary();
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
elements.copyCredentialsButton.addEventListener("click", async () => {
  if (!savedCredentials) return;
  await navigator.clipboard.writeText(savedCredentials).then(() => { elements.statusMessage.textContent = "当前页 Cookie 已复制"; }).catch(() => showActionError(new Error("复制失败，请手动选择当前页 Cookie")));
});
elements.qualificationSearch.addEventListener("input", filterQualifications);
elements.selectDefaultsButton.addEventListener("click", () => {
  document.querySelectorAll("[data-qualification-code]").forEach((input) => { input.checked = Boolean(qualifications.find((item) => item.code === input.value)?.defaultSelected); });
  updateSelectionSummary();
});
elements.clearQualificationsButton.addEventListener("click", () => { document.querySelectorAll("[data-qualification-code]").forEach((input) => { input.checked = false; }); updateSelectionSummary(); });
elements.runButton.addEventListener("click", () => postJson("/api/run", { filters: readFilters(), qualificationCodes: selectedQualificationCodes() }).then(renderState).catch(showActionError));
elements.stopButton.addEventListener("click", () => postJson("/api/stop").then(renderState).catch(showActionError));
elements.themeToggle.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
elements.resultsViewport.addEventListener("scroll", () => { followResults = nearBottom(elements.resultsViewport); });
elements.logList.addEventListener("scroll", () => { followLogs = nearBottom(elements.logList); });

pollStatus();
window.setInterval(pollStatus, 800);
