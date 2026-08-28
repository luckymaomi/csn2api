const elements = {
  statusMessage: document.querySelector("#statusMessage"),
  statusBadge: document.querySelector("#statusBadge"),
  themeToggle: document.querySelector("#themeToggle"),
  credentials: document.querySelector("#credentials"),
  verifyButton: document.querySelector("#verifyButton"),
  loadFiltersButton: document.querySelector("#loadFiltersButton"),
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
  metadataStatus: document.querySelector("#metadataStatus"),
  filterFieldCount: document.querySelector("#filterFieldCount"),
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
  waiting_credentials: "待验证", verifying: "验证中", loading_metadata: "加载中", ready: "可执行", querying: "查询中",
  stopping: "停止中", stopped: "已停止", partial_failure: "部分失败", completed: "已完成",
  session_expired: "会话失效", failed: "失败",
};

let keepAliveTimer = () => ({ active: false, total: 0, remaining: 0 });
let renderKeepAlive = () => undefined;
let savedCredentials = "";
let filterDefinitions = [];
let qualifications = [];
let sessionVerified = false;
let metadataLoaded = false;
let interactionBusy = false;
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
    const state = await postJson("./api/session/verify", { credentials: value });
    updateSavedCredentials(state.credentials);
    elements.credentials.value = "";
    renderState(state);
  } finally {
    elements.verifyButton.disabled = false;
  }
}

async function loadMetadata() {
  elements.loadFiltersButton.disabled = true;
  try {
    renderState(await postJson("./api/metadata/load"));
  } finally {
    elements.loadFiltersButton.disabled = false;
  }
}

function selectedValues(name) {
  return [...document.querySelectorAll("[data-filter-name]")]
    .filter((input) => input.dataset.filterName === name && input.checked)
    .map((input) => input.value)
    .filter(Boolean);
}

function readFilters() {
  const values = {};
  filterDefinitions.forEach((field) => {
    const selected = selectedValues(field.name);
    values[field.name] = field.multiple ? selected : (selected[0] || "");
  });
  return values;
}

function renderFilterFields(fields = []) {
  filterDefinitions = fields;
  if (!fields.length) {
    elements.filterFields.innerHTML = '<div class="empty-state">验证 Cookie 后点击“加载筛选”</div>';
    return;
  }
  elements.filterFields.replaceChildren(...fields.map((field) => {
    const group = document.createElement("fieldset");
    group.className = "filter-group";
    const heading = document.createElement("div");
    heading.className = "filter-group-heading";
    const legend = document.createElement("legend");
    legend.textContent = field.label;
    const mode = document.createElement("span");
    mode.textContent = field.multiple ? "多选" : "单选";
    heading.append(legend, mode);
    const options = document.createElement("div");
    options.className = "filter-options";
    const available = field.options.filter((option) => option.value);
    available.forEach((option, index) => {
      const item = document.createElement("label");
      item.className = "check-choice";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = option.value;
      checkbox.dataset.filterName = field.name;
      checkbox.dataset.filterMultiple = field.multiple ? "true" : "false";
      checkbox.id = `filter-${field.name}-${index}`;
      checkbox.checked = (
        (field.name === "fleetCdToArray" && option.value === "777")
        || (field.name === "activeStatusArray" && ["ZAIZHI", "WAIBU", "TUIXIU", "LIZHI"].includes(option.value))
      );
      checkbox.addEventListener("change", () => {
        if (checkbox.checked && !field.multiple) {
          options.querySelectorAll("input[type=checkbox]").forEach((peer) => { if (peer !== checkbox) peer.checked = false; });
        }
        updateSelectionSummary();
      });
      const label = document.createElement("span");
      label.textContent = option.label || option.value;
      item.append(checkbox, label);
      options.append(item);
    });
    if (!available.length) options.innerHTML = '<div class="group-empty">门户未返回可选值</div>';
    group.append(heading, options);
    return group;
  }));
  updateSelectionSummary();
}

function renderQualifications(items = []) {
  qualifications = items;
  if (!items.length) {
    elements.qualificationList.innerHTML = '<div class="empty-state">加载筛选后显示当前运行资格</div>';
    return;
  }
  elements.qualificationList.replaceChildren(...items.map((item) => {
    const row = document.createElement("label");
    row.className = "qualification-choice";
    row.dataset.code = item.code;
    row.dataset.search = `${item.code} ${item.name} ${item.typeName}`.toLowerCase();
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = item.code;
    checkbox.dataset.qualificationCode = item.code;
    checkbox.checked = Boolean(item.defaultSelected);
    checkbox.addEventListener("change", updateSelectionSummary);
    const copy = document.createElement("span");
    copy.className = "qualification-copy";
    const code = document.createElement("strong");
    code.textContent = item.code;
    const name = document.createElement("span");
    name.textContent = item.name || "未提供中文描述";
    copy.append(code, name);
    row.append(checkbox, copy);
    return row;
  }));
  filterQualifications();
  updateSelectionSummary();
}

function filterQualifications() {
  const query = elements.qualificationSearch.value.trim().toLowerCase();
  document.querySelectorAll(".qualification-choice").forEach((row) => {
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
  elements.selectedFilterSummary.textContent = metadataLoaded
    ? `机型 ${fleet.join(", ") || "不限"} · 状态 ${status.length ? `${status.length} 项` : "不限"} · 资质 ${codes.length} 项`
    : "尚未加载筛选";
  elements.runButton.disabled = !codes.length || !sessionVerified || !metadataLoaded || interactionBusy;
}

function renderResults(rows = [], columns = []) {
  const signature = JSON.stringify([columns, rows]);
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
  const headers = ["序号", ...columns, "资质类别"];
  const headingRow = document.createElement("tr");
  headers.forEach((header) => {
    const th = document.createElement("th");
    th.textContent = header;
    headingRow.append(th);
  });
  elements.resultsTable.querySelector("thead").replaceChildren(headingRow);
  elements.resultsTable.style.minWidth = `${Math.max(720, 90 + columns.length * 132 + 140)}px`;
  const body = elements.resultsTable.querySelector("tbody");
  body.replaceChildren(...rows.map((row) => {
    const tr = document.createElement("tr");
    [row.sequence, ...columns.map((column) => row.fields?.[column] || ""), row.qualificationCode].forEach((value) => {
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
  if (enabled) elements.excelDownload.href = "./api/download/excel";
  else elements.excelDownload.removeAttribute("href");
}

function renderState(state) {
  const phase = state.phase || "waiting_credentials";
  const session = state.session || {};
  const metadata = state.metadata || {};
  const progress = state.progress || {};
  const total = Number(progress.total || 0);
  const completed = Number(progress.completed || 0);
  const busy = ["verifying", "loading_metadata", "querying", "stopping"].includes(phase);
  interactionBusy = busy;
  const percent = total ? Math.min(100, Math.round(completed * 100 / total)) : 0;
  if (!session.verified || phase === "session_expired") updateSavedCredentials("");
  sessionVerified = Boolean(session.verified);
  metadataLoaded = Boolean(metadata.loaded);
  elements.statusMessage.textContent = state.error || (
    !sessionVerified ? "等待验证飞行门户 Cookie"
      : metadataLoaded ? "筛选已加载，可执行查询" : "Cookie 已验证，请加载筛选"
  );
  elements.statusBadge.textContent = phaseLabels[phase] || phase;
  elements.statusBadge.className = `status-badge is-${phase}`;
  elements.sessionStatus.textContent = session.verified ? "已验证" : "尚未验证";
  elements.sessionVerified.textContent = session.verified ? "有效" : "未验证";
  elements.sessionVerifiedAt.textContent = session.verifiedAt || "-";
  elements.qualificationCount.textContent = `${(state.qualifications || []).length} 项`;
  const identity = session.identity || {};
  elements.sessionIdentity.textContent = session.verified ? [identity.staffNumber, identity.name].filter(Boolean).join(" · ") || "未识别" : "-";
  elements.metadataStatus.textContent = metadataLoaded ? `已加载 ${metadata.loadedAt || ""}`.trim() : "尚未加载";
  elements.filterFieldCount.textContent = `${(state.filterFields || []).length} 项`;
  renderKeepAlive({ ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail }, session, keepAliveTimer);
  const metadataSignature = JSON.stringify([state.filterFields || [], state.qualifications || []]);
  if (metadataSignature !== lastMetadataSignature) {
    lastMetadataSignature = metadataSignature;
    renderFilterFields(state.filterFields || []);
    renderQualifications(state.qualifications || []);
  }
  elements.credentials.disabled = busy;
  elements.verifyButton.disabled = busy;
  elements.loadFiltersButton.disabled = !sessionVerified || busy;
  elements.selectDefaultsButton.disabled = !metadataLoaded || busy;
  elements.clearQualificationsButton.disabled = !metadataLoaded || busy;
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
  renderResults(state.results || [], state.resultColumns || []);
  renderLogs(state.logs || []);
  updateSelectionSummary();
}

async function pollStatus() {
  try {
    const response = await fetch("./api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderState(await response.json());
    pollingFailed = false;
  } catch (error) {
    if (!pollingFailed) showActionError(new Error(`状态连接失败：${error.message || error}`));
    pollingFailed = true;
  }
}

elements.verifyButton.addEventListener("click", () => verify().catch(showActionError));
elements.loadFiltersButton.addEventListener("click", () => loadMetadata().catch(showActionError));
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
elements.runButton.addEventListener("click", () => postJson("./api/run", { filters: readFilters(), qualificationCodes: selectedQualificationCodes() }).then(renderState).catch(showActionError));
elements.stopButton.addEventListener("click", () => postJson("./api/stop").then(renderState).catch(showActionError));
elements.themeToggle.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
elements.resultsViewport.addEventListener("scroll", () => { followResults = nearBottom(elements.resultsViewport); });
elements.logList.addEventListener("scroll", () => { followLogs = nearBottom(elements.logList); });

pollStatus();
window.setInterval(pollStatus, 800);
