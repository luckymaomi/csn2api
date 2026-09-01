const byId = (id) => document.getElementById(id);
const elements = Object.fromEntries([
  "statusMessage", "statusBadge", "themeToggle", "credentials", "verifyButton", "savedCredentialsPanel",
  "savedCredentials", "copyCredentialsButton", "sessionStatus", "sessionVerified", "sessionVerifiedAt",
  "sessionIdentity", "keepAliveRing", "keepAliveCountdown", "keepAliveStatus", "keepAliveDetail", "queryMode",
  "excelPanel", "pastePanel", "excelFile", "pastedText", "dataCheckButton", "runButton", "stopButton",
  "dataCheckResult", "dataCheckErrors", "progressBar", "progressText", "totalCount", "completedCount",
  "successCount", "failedCount", "currentRecord", "resultDownload", "resultsCount", "resultsViewport",
  "resultsEmpty", "resultsTable", "resultsPreviousPage", "resultsNextPage", "resultsPageText",
  "detailCount", "detailViewport", "detailEmpty", "detailTable", "detailPreviousPage", "detailNextPage", "detailPageText", "logList",
].map((id) => [id, byId(id)]));

const DETAIL_HEADERS = ["序号", "姓名", "员工号", "航班号", "机型", "日期", "左座", "右座", "操纵", "观察", "离场", "到达", "飞行时间", "夜航", "飞行阶段", "人工飞行时间", "人工飞行方式"];
const phaseLabels = { waiting_credentials: "待验证", verifying_credentials: "验证中", credentials_ready: "凭据有效", data_checked: "数据已检查", running: "查询中", stopping: "终止中", completed: "已完成", terminated: "已终止", session_expired: "会话失效", failed: "失败" };
let keepAliveTimer = () => ({ active: false });
let renderKeepAlive = () => undefined;
let savedCredentials = "";
let followLogs = true;
let lastRunId = "";

void import("./session_keepalive.mjs").then((module) => {
  keepAliveTimer = module.createKeepAliveTimer();
  renderKeepAlive = module.renderKeepAlive;
  return refreshStatus();
}).catch((error) => {
  elements.keepAliveRing.hidden = true;
  elements.keepAliveStatus.textContent = "保活组件加载失败";
  elements.keepAliveDetail.textContent = "核心功能仍可使用，请重新下载安装包";
  showError(error);
});

function inputMode() { return document.querySelector('input[name="inputMode"]:checked')?.value || "excel"; }
function fileBase64(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error("读取 Excel 文件失败")); reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || ""); reader.readAsDataURL(file); }); }
async function payload() {
  const mode = inputMode();
  const value = { inputMode: mode, excelName: "", excelBase64: "", pastedText: elements.pastedText.value };
  if (mode === "excel") {
    const file = elements.excelFile.files[0];
    if (!file) throw new Error("请选择 Excel 文件");
    value.excelName = file.name;
    value.excelBase64 = await fileBase64(file);
  }
  return value;
}
async function post(path, body = {}) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(value.error || `请求失败：HTTP ${response.status}`);
  return value;
}
function nearBottom(node) { return node.scrollHeight - node.scrollTop - node.clientHeight < 20; }
function setSaved(value) { savedCredentials = String(value || ""); elements.savedCredentials.value = savedCredentials; elements.savedCredentialsPanel.hidden = !savedCredentials; }
function setDownload(enabled) { elements.resultDownload.classList.toggle("disabled", !enabled); elements.resultDownload.setAttribute("aria-disabled", enabled ? "false" : "true"); if (enabled) elements.resultDownload.href = "./api/download/result"; else elements.resultDownload.removeAttribute("href"); }

function createPagedTable({ kind, pageSize, count, viewport, empty, table, previous, next, pageText }) {
  let page = 0;
  let total = 0;
  let requestId = 0;
  let lastVersion = -1;
  let followLatest = true;
  const draw = (payload) => {
    const columns = payload.columns || [];
    const rows = payload.rows || [];
    const header = document.createElement("tr");
    columns.forEach((column) => { const cell = document.createElement("th"); cell.textContent = column; header.append(cell); });
    table.tHead.replaceChildren(header);
    table.tBodies[0].replaceChildren(...rows.map((row) => {
      const tr = document.createElement("tr");
      columns.forEach((column) => { const td = document.createElement("td"); const value = row[column] ?? ""; td.textContent = String(value); if (column === "状态") td.className = value === "成功" ? "is-success" : value === "未查询" ? "is-muted" : "is-failed"; tr.append(td); });
      return tr;
    }));
    empty.hidden = rows.length > 0;
    table.hidden = rows.length === 0;
    count.textContent = `${total} 条`;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    pageText.textContent = `第 ${Math.min(page + 1, pages)} / ${pages} 页`;
    previous.disabled = page <= 0;
    next.disabled = page >= pages - 1;
    if (followLatest) viewport.scrollTop = viewport.scrollHeight;
  };
  const load = async () => {
    if (followLatest && total > 0) page = Math.max(0, Math.ceil(total / pageSize) - 1);
    page = Math.max(0, page);
    const current = ++requestId;
    const response = await fetch(`./api/results?kind=${kind}&offset=${page * pageSize}&limit=${pageSize}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`结果读取失败：HTTP ${response.status}`);
    const payload = await response.json();
    if (current !== requestId) return;
    total = Number(payload.total || 0);
    page = total ? Math.min(page, Math.max(0, Math.ceil(total / pageSize) - 1)) : 0;
    draw(payload);
  };
  previous.addEventListener("click", () => { followLatest = false; page -= 1; void load().catch(showError); });
  next.addEventListener("click", () => { followLatest = false; page += 1; void load().catch(showError); });
  return {
    followLatest() { followLatest = true; },
    reset() { page = 0; total = 0; followLatest = true; lastVersion = -1; requestId += 1; },
    async render(meta = {}) { total = Number(meta[`${kind}Total`] || 0); const version = Number(meta.version || 0); if (version === lastVersion) return; lastVersion = version; await load(); },
  };
}
const statusTable = createPagedTable({ kind: "status", pageSize: 50, count: elements.resultsCount, viewport: elements.resultsViewport, empty: elements.resultsEmpty, table: elements.resultsTable, previous: elements.resultsPreviousPage, next: elements.resultsNextPage, pageText: elements.resultsPageText });
const detailTable = createPagedTable({ kind: "detail", pageSize: 100, count: elements.detailCount, viewport: elements.detailViewport, empty: elements.detailEmpty, table: elements.detailTable, previous: elements.detailPreviousPage, next: elements.detailNextPage, pageText: elements.detailPageText });
function renderLogs(logs = []) {
  if (!logs.length) { const li = document.createElement("li"); li.className = "is-muted"; li.textContent = "尚无运行记录"; elements.logList.replaceChildren(li); return; }
  elements.logList.replaceChildren(...logs.map((log) => { const li = document.createElement("li"); li.className = log.level === "error" ? "is-error" : log.level === "success" ? "is-success" : ""; li.textContent = `${log.time ? `[${log.time}] ` : ""}${log.message || ""}`; return li; }));
  if (followLogs) elements.logList.scrollTop = elements.logList.scrollHeight;
}
function renderCheck(check = {}) {
  const strong = elements.dataCheckResult.querySelector("strong");
  elements.dataCheckResult.className = `health-check ${check.checked ? check.ok ? "is-ok" : "is-error" : ""}`;
  strong.textContent = check.checked ? `${check.validCount || 0} 人 · ${check.monthCount || 0} 个人员/月 · 无效 ${check.invalidCount || 0}` : "尚未检查";
  const errors = check.errors || [];
  elements.dataCheckErrors.hidden = errors.length === 0;
  elements.dataCheckErrors.replaceChildren(...errors.map((message) => { const li = document.createElement("li"); li.textContent = message; return li; }));
}
function renderState(state = {}) {
  elements.statusMessage.textContent = state.message || "";
  elements.statusBadge.textContent = phaseLabels[state.phase] || state.phase || "未知";
  elements.statusBadge.className = `status-badge is-${state.phase || "waiting_credentials"}`;
  const session = state.session || {};
  elements.sessionStatus.textContent = session.verified ? "已验证" : "尚未验证";
  elements.sessionVerified.textContent = session.verified ? "有效" : "未验证";
  elements.sessionVerifiedAt.textContent = session.verifiedAt || "-";
  elements.sessionIdentity.textContent = session.identity ? `${session.identity.name || ""} ${session.identity.staffNumber || ""}`.trim() : "-";
  elements.queryMode.textContent = state.queryMode || "按人员和月份严格串行";
  renderKeepAlive({ ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail }, session, keepAliveTimer);
  const progress = state.progress || {};
  const total = Number(progress.total || 0); const completed = Number(progress.completed || 0); const percent = total ? Math.round(completed / total * 100) : 0;
  elements.progressBar.style.width = `${percent}%`; elements.progressBar.parentElement.setAttribute("aria-valuenow", String(percent));
  elements.progressText.textContent = `${completed} / ${total}`; elements.totalCount.textContent = total; elements.completedCount.textContent = completed; elements.successCount.textContent = progress.success || 0; elements.failedCount.textContent = progress.failed || 0; elements.currentRecord.textContent = progress.current || "-";
  elements.verifyButton.disabled = state.canVerify === false; elements.dataCheckButton.disabled = state.canCheckData !== true; elements.runButton.disabled = state.canRun !== true; elements.stopButton.disabled = state.canStop !== true;
  renderCheck(state.checks?.data); renderLogs(state.logs || []); setDownload(state.downloads?.result === true);
  if (state.runId && state.runId !== lastRunId) {
    lastRunId = state.runId;
    statusTable.reset();
    detailTable.reset();
  }
  const resultTable = state.resultTable || {};
  void statusTable.render({ statusTotal: resultTable.statusTotal, version: resultTable.version }).catch(showError);
  void detailTable.render({ detailTotal: resultTable.detailTotal, version: resultTable.version }).catch(showError);
  if (!session.verified) setSaved("");
}
function showError(error) { elements.statusMessage.textContent = error.message || String(error); elements.statusBadge.textContent = "操作失败"; elements.statusBadge.className = "status-badge is-failed"; }
async function refreshStatus() { const response = await fetch("./api/status", { cache: "no-store" }); if (!response.ok) throw new Error("状态服务不可用"); renderState(await response.json()); }

elements.verifyButton.addEventListener("click", () => { const credentials = elements.credentials.value.trim(); if (!credentials) return showError(new Error("请粘贴登录凭据")); void post("./api/session/verify", { credentials }).then((state) => { setSaved(state.credentials); elements.credentials.value = ""; renderState(state); }).catch(showError); });
elements.dataCheckButton.addEventListener("click", () => void payload().then((value) => post("./api/check-data", value)).then(renderState).catch(showError));
elements.runButton.addEventListener("click", () => { statusTable.followLatest(); detailTable.followLatest(); void payload().then((value) => post("./api/run", value)).then(renderState).catch(showError); });
elements.stopButton.addEventListener("click", () => void post("./api/stop").then(renderState).catch(showError));
elements.copyCredentialsButton.addEventListener("click", () => void navigator.clipboard.writeText(savedCredentials).catch(() => showError(new Error("复制失败"))));
document.querySelectorAll('input[name="inputMode"]').forEach((input) => input.addEventListener("change", () => { const excel = inputMode() === "excel"; elements.excelPanel.hidden = !excel; elements.pastePanel.hidden = excel; }));
elements.themeToggle.addEventListener("click", () => window.CsnTheme?.toggle?.());
elements.logList.addEventListener("scroll", () => { followLogs = nearBottom(elements.logList); });
setInterval(() => void refreshStatus().catch(showError), 1000);
