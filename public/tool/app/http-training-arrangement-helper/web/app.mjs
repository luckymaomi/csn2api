const $ = (id) => document.getElementById(id);
const elements = {
  statusBadge: $("statusBadge"), statusMessage: $("statusMessage"), credentials: $("credentials"), verifyButton: $("verifyButton"),
  savedCredentialsPanel: $("savedCredentialsPanel"), savedCredentials: $("savedCredentials"), copyCredentialsButton: $("copyCredentialsButton"),
  sessionVerified: $("sessionVerified"), sessionVerifiedAt: $("sessionVerifiedAt"), sessionIdentity: $("sessionIdentity"), sessionCookieCount: $("sessionCookieCount"),
  keepAliveRing: $("keepAliveRing"), keepAliveCountdown: $("keepAliveCountdown"), keepAliveStatus: $("keepAliveStatus"), keepAliveDetail: $("keepAliveDetail"),
  categorySelect: $("categorySelect"), dateRange: $("dateRange"), endDate: $("endDate"), metadataButton: $("metadataButton"), runButton: $("runButton"), areaRunButton: $("areaRunButton"), stopButton: $("stopButton"), areaDefaultStatus: $("areaDefaultStatus"), areaDefaultCount: $("areaDefaultCount"), areaDefaultCatalog: $("areaDefaultCatalog"),
  resultSummary: $("resultSummary"), progressBar: $("progressBar"), progressText: $("progressText"), summaryTable: $("summaryTable"), resultsViewport: $("resultsViewport"), resultsEmpty: $("resultsEmpty"), resultsTable: $("resultsTable"), excelDownload: $("excelDownload"), logList: $("logList"), themeToggle: $("themeToggle"),
};

let savedCredentials = "";
let followResults = true;
let followLogs = true;
let lastResultsSignature = "";
let lastAreaDefaultsSignature = "";
let keepAliveTimer = () => ({ active: false, remaining: 0, total: 0 });
let keepAliveRenderer = null;

void import("./session_keepalive.mjs").then((module) => {
  keepAliveRenderer = module.renderKeepAlive;
  keepAliveTimer = module.createKeepAliveTimer();
});

const phaseLabels = {
  waiting_credentials: "等待验证", verifying_credentials: "验证中", credentials_ready: "凭据有效", ready: "已就绪",
  running: "查询中", stopping: "停止中", completed: "已完成", terminated: "已停止", failed: "失败", session_expired: "会话失效",
};

function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function escapeText(value) { return String(value ?? ""); }

async function postJson(path, payload = {}) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `请求失败：HTTP ${response.status}`);
  return data;
}

function showError(error) {
  elements.statusBadge.textContent = "操作失败";
  elements.statusBadge.className = "status-badge is-failed";
  elements.statusMessage.textContent = `核心功能仍可使用；${error.message || String(error)}`;
}

function renderOptions(options = []) {
  elements.categorySelect.replaceChildren(new Option("请选择训练类别", ""), ...options.map((item) => new Option(item.label, item.value)));
  elements.categorySelect.disabled = options.length === 0;
}

function renderAreaDefaults(areaDefaults = {}) {
  const categories = Array.isArray(areaDefaults.categories) ? areaDefaults.categories : [];
  const subjectCount = categories.reduce((sum, category) => sum + (Array.isArray(category.subjects) ? category.subjects.length : 0), 0);
  elements.areaDefaultCount.textContent = categories.length ? `${categories.length} 个类型 · ${subjectCount} 个科目` : "暂无配置";
  const signature = JSON.stringify(categories);
  if (signature === lastAreaDefaultsSignature) return;
  lastAreaDefaultsSignature = signature;
  if (!categories.length) {
    const empty = document.createElement("span");
    empty.className = "area-default-empty";
    empty.textContent = "暂无默认类型和科目";
    elements.areaDefaultCatalog.replaceChildren(empty);
    return;
  }
  elements.areaDefaultCatalog.replaceChildren(...categories.map((category) => {
    const item = document.createElement("div");
    item.className = "area-default-item";
    const name = document.createElement("strong");
    name.textContent = `${escapeText(category.name)}：`;
    const subjects = document.createElement("span");
    subjects.className = "area-default-subjects";
    subjects.textContent = (Array.isArray(category.subjects) ? category.subjects : []).map(escapeText).join("、");
    item.append(name, subjects);
    return item;
  }));
}

function renderResults(results = []) {
  const signature = JSON.stringify(results);
  const total = results.reduce((sum, item) => sum + Number(item.rows?.length || 0), 0);
  elements.resultSummary.textContent = results.length ? `${results.length} 个时间周期 · ${total} 条记录` : "尚无结果";
  elements.resultsEmpty.hidden = results.length > 0;
  elements.resultsTable.hidden = results.length === 0;
  if (signature === lastResultsSignature) return;
  lastResultsSignature = signature;
  elements.resultsTable.replaceChildren(...results.map((result) => {
    const section = document.createElement("section");
    section.className = "period-result";
    const heading = document.createElement("div");
    heading.className = "period-heading";
    const title = [result.category, result.label].filter(Boolean).join(" / ");
    heading.textContent = `${escapeText(title)}（${escapeText(result.startDate)} 至 ${escapeText(result.endDate)}） · ${result.rows?.length || 0} 条 / ${result.pages || 0} 页`;
    const viewport = document.createElement("div");
    viewport.className = "period-table-viewport";
    const table = document.createElement("table");
    table.className = "result-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    (result.headers || []).forEach((header) => { const th = document.createElement("th"); th.textContent = escapeText(header); headRow.append(th); });
    head.append(headRow);
    const body = document.createElement("tbody");
    (result.rows || []).forEach((values) => {
      const row = document.createElement("tr");
      (result.headers || []).forEach((header) => { const td = document.createElement("td"); td.textContent = escapeText(values[header]); row.append(td); });
      body.append(row);
    });
    table.append(head, body); viewport.append(table); section.append(heading, viewport); return section;
  }));
  if (followResults) elements.resultsViewport.scrollTop = elements.resultsViewport.scrollHeight;
}

function renderSummary(rows = []) {
  elements.summaryTable.hidden = rows.length === 0;
  if (!rows.length) { elements.summaryTable.replaceChildren(); return; }
  const table = document.createElement("table");
  table.className = "summary-table";
  const headers = ["类型", "本周（人/通过率）", "本月（人/通过率）", "年度（人/通过率）"];
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  headers.forEach((header) => { const cell = document.createElement("th"); cell.textContent = header; headRow.append(cell); });
  head.append(headRow);
  const body = document.createElement("tbody");
  rows.forEach((item) => {
    const row = document.createElement("tr");
    const type = document.createElement("td"); type.textContent = escapeText(item.type); row.append(type);
    ["week", "month", "year"].forEach((key) => {
      const period = item[key] || {};
      const cell = document.createElement("td");
      const count = Number(period.count || 0);
      const rate = period.rate == null ? "/" : `${period.rate}%`;
      cell.textContent = `${count}人次 / ${rate}`;
      row.append(cell);
    });
    body.append(row);
  });
  table.append(head, body);
  elements.summaryTable.replaceChildren(table);
}

function renderLogs(logs = []) {
  if (!logs.length) { elements.logList.replaceChildren(Object.assign(document.createElement("li"), { className: "is-muted", textContent: "尚无运行记录" })); return; }
  elements.logList.replaceChildren(...logs.map((log) => { const li = document.createElement("li"); li.className = `is-${log.level || "info"}`; li.textContent = `${log.time ? `[${log.time}] ` : ""}${log.message || ""}`; return li; }));
  if (followLogs) elements.logList.scrollTop = elements.logList.scrollHeight;
}

function renderState(state) {
  const phase = state.phase || "waiting_credentials";
  const session = state.session || {};
  const progress = state.progress || {};
  const results = state.results || [];
  const count = results.reduce((sum, item) => sum + Number(item.rows?.length || 0), 0);
  const areaDefaults = state.areaDefaults || {};
  elements.statusBadge.textContent = phaseLabels[phase] || phase;
  elements.statusBadge.className = `status-badge is-${phase}`;
  elements.statusMessage.textContent = state.message || "";
  elements.sessionVerified.textContent = session.verified ? "有效" : "未验证";
  elements.sessionVerifiedAt.textContent = session.verifiedAt || "-";
  const identity = session.identity || {};
  elements.sessionIdentity.textContent = session.verified ? [identity.staffNumber, identity.name].filter(Boolean).join(" · ") || "已登录" : "-";
  elements.sessionCookieCount.textContent = String(session.cookieCount || 0);
  if (keepAliveRenderer) keepAliveRenderer({ ring: elements.keepAliveRing, countdown: elements.keepAliveCountdown, status: elements.keepAliveStatus, detail: elements.keepAliveDetail }, session, keepAliveTimer);
  elements.verifyButton.disabled = !state.canVerify;
  elements.credentials.disabled = !state.canVerify;
  elements.metadataButton.disabled = !state.canLoadMetadata;
  elements.runButton.disabled = !state.canRun;
  elements.areaRunButton.disabled = !state.canRunArea;
  elements.stopButton.disabled = !state.canStop;
  elements.dateRange.disabled = !session.verified;
  elements.endDate.disabled = !session.verified;
  const completedSubjects = Number(progress.completedSubjects || 0);
  const totalSubjects = Number(progress.totalSubjects || 0);
  const percent = phase === "completed" ? 100 : (totalSubjects ? Math.round((completedSubjects / totalSubjects) * 100) : (progress.page ? 50 : 0));
  elements.progressBar.style.width = `${percent}%`;
  const subjectProgress = totalSubjects ? `已完成 ${completedSubjects} / ${totalSubjects} 个科目 · ` : "";
  elements.progressText.textContent = progress.category ? `${subjectProgress}${progress.category} / ${progress.subject || ""} / ${progress.period || ""}：第 ${progress.page || 0} 页，累计 ${progress.records || 0} 条` : (progress.period ? `${progress.period}：第 ${progress.page || 0} 页，累计 ${progress.records || 0} 条` : "等待查询");
  elements.areaDefaultStatus.textContent = areaDefaults.available
    ? `区域默认配置已就绪：${(areaDefaults.categories || []).length} 个业务类型，可一键查询周、月、年。`
    : (areaDefaults.error || "加载训练类别后自动校验区域默认配置");
  renderAreaDefaults(areaDefaults);
  renderSummary(state.summary || []);
  renderResults(results); renderLogs(state.logs || []);
  const downloadId = state.downloads?.excelId;
  elements.excelDownload.classList.toggle("disabled", !downloadId);
  elements.excelDownload.setAttribute("aria-disabled", downloadId ? "false" : "true");
  if (downloadId) elements.excelDownload.href = `./api/download/${encodeURIComponent(downloadId)}`;
  else elements.excelDownload.removeAttribute("href");
  if (state.credentials) { savedCredentials = state.credentials; elements.savedCredentials.value = savedCredentials; elements.savedCredentialsPanel.hidden = false; }
}

async function verify() { const state = await postJson("./api/session/verify", { credentials: elements.credentials.value.trim() }); elements.credentials.value = ""; renderState(state); await loadMetadata(); }
async function loadMetadata() { const state = await postJson("./api/metadata/load"); renderOptions(state.metadata?.options || []); renderState(state); }
async function run() { renderState(await postJson("./api/run", { category: elements.categorySelect.value, dateRange: elements.dateRange.value, endDate: elements.endDate.value })); }
async function runAreaDefault() { renderState(await postJson("./api/run", { mode: "area-default", endDate: elements.endDate.value })); }
async function stop() { renderState(await postJson("./api/stop")); }

elements.endDate.value = today();
elements.verifyButton.addEventListener("click", () => verify().catch(showError));
elements.metadataButton.addEventListener("click", () => loadMetadata().catch(showError));
elements.runButton.addEventListener("click", () => run().catch(showError));
elements.areaRunButton.addEventListener("click", () => runAreaDefault().catch(showError));
elements.stopButton.addEventListener("click", () => stop().catch(showError));
elements.copyCredentialsButton.addEventListener("click", async () => { try { await navigator.clipboard.writeText(savedCredentials); elements.statusMessage.textContent = "当前页 Cookie 已复制"; } catch (_error) { showError(new Error("复制失败，请手动选择当前页 Cookie")); } });
elements.themeToggle.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
elements.resultsViewport.addEventListener("scroll", () => { followResults = elements.resultsViewport.scrollHeight - elements.resultsViewport.scrollTop - elements.resultsViewport.clientHeight < 20; });
elements.logList.addEventListener("scroll", () => { followLogs = elements.logList.scrollHeight - elements.logList.scrollTop - elements.logList.clientHeight < 20; });

async function poll() { try { renderState(await (await fetch("./api/status", { cache: "no-store" })).json()); } catch (error) { if (!String(error).includes("Failed")) showError(error); } }
poll();
window.setInterval(poll, 800);
