import { materializeCatalogModule } from "./catalog-normalize.mjs";
import {
    buildCurlExample,
    buildPythonExample,
    escapeHtml,
    renderCookieDocument,
    renderEndpointDocument
} from "./catalog-view.mjs";
import {
    collectParameters as collectParameterValues,
    editableParameters,
    renderParameterForm as renderParameterFields,
    updateParameterAvailability
} from "./parameter-form.mjs";
import {
    bindResponseTabs,
    clearResponse,
    renderResponse,
    renderResponseError
} from "./response-view.mjs";
import { buildApiDocsMarkdown, downloadMarkdown } from "./markdown-export.mjs";
import { createToast, renderEndpointNavigation, renderSessionStatus } from "./ui-shell.mjs";

const state = {
    systems: [],
    modules: [],
    endpointRecords: new Map(),
    selectedView: "cookie",
    selectedId: "",
    search: "",
    backendAvailable: false,
    activeExecution: null,
    sessions: new Map(),
    savedCredentials: new Map(),
    credentialDrafts: new Map(),
    options: new Map(),
    codeLanguage: "curl"
};

const elements = {
    endpointList: document.getElementById("systemNavigation"),
    cookieNav: document.getElementById("cookieNav"),
    document: document.getElementById("endpointDocument"),
    search: document.getElementById("endpointSearch"),
    exportMarkdownButton: document.getElementById("exportMarkdownButton"),
    themeToggle: document.getElementById("themeToggle"),
    sessionPanel: document.getElementById("sessionPanel"),
    sessionPanels: document.getElementById("sessionPanels"),
    endpointConsole: document.getElementById("endpointConsole"),
    endpointSessionLabel: document.getElementById("endpointSessionLabel"),
    sessionState: document.getElementById("sessionState"),
    sessionDetail: document.getElementById("sessionDetail"),
    manageSessionButton: document.getElementById("manageSessionButton"),
    parameterForm: document.getElementById("parameterForm"),
    sendRequestButton: document.getElementById("sendRequestButton"),
    responseSection: document.getElementById("responseSection"),
    responseMeta: document.getElementById("responseMeta"),
    responseTable: document.getElementById("responseTable"),
    responseJson: document.getElementById("responseJson"),
    responseRaw: document.getElementById("responseRaw"),
    responseHeaders: document.getElementById("responseHeaders"),
    toast: document.getElementById("toast")
};
const showToast = createToast(elements.toast);
let followProgressiveResponse = true;

function isNearBottom(element) {
    return element.scrollHeight - element.scrollTop - element.clientHeight < 20;
}

function scrollProgressiveResponseToBottom() {
    if (followProgressiveResponse && elements.responseTable) {
        elements.responseTable.scrollTop = elements.responseTable.scrollHeight;
    }
}

async function fetchJson(path, options) {
    const response = await fetch(path, { cache: "no-store", ...options });
    let payload;
    try {
        payload = await response.json();
    } catch (_error) {
        throw new Error(`请求返回 HTTP ${response.status}`);
    }
    if (!response.ok) throw new Error(payload.error || `请求返回 HTTP ${response.status}`);
    return payload;
}

async function loadCatalog() {
    const index = await fetchJson("./catalog/index.json");
    state.systems = Array.isArray(index.systems) ? index.systems : [];
    state.modules = await Promise.all(index.modules.map(async (item) => {
        const source = String(item.source || "").replace(/^\.\//, "");
        const module = materializeCatalogModule(await fetchJson(`./catalog/${source}`));
        return { ...module, catalogSource: `./catalog/${source}` };
    }));
    state.endpointRecords.clear();
    state.modules.forEach((module) => {
        (module.endpoints || []).forEach((endpoint) => {
            const fullId = `${module.id}.${endpoint.id}`;
            const system = state.systems.find((item) => item.id === module.systemId) || null;
            state.endpointRecords.set(fullId, { module, endpoint, system, fullId });
        });
    });
}

function selectedRecord() {
    return state.endpointRecords.get(state.selectedId) || null;
}

function systemById(systemId) {
    return state.systems.find((system) => system.id === systemId) || null;
}

function activeSystemId() {
    return selectedRecord()?.module.systemId || state.systems[0]?.id || "";
}

function activeSessionStatus() {
    return state.sessions.get(activeSystemId()) || null;
}

function activeSessionReady() {
    return activeSessionStatus()?.ready === true;
}

function renderNavigation() {
    if (!(elements.endpointList instanceof HTMLElement)) return;
    renderEndpointNavigation(
        elements.endpointList,
        state.systems,
        [...state.endpointRecords.values()],
        state.selectedId,
        state.search,
    );
    elements.cookieNav?.classList.toggle("is-active", state.selectedView === "cookie");
}

function renderParameterForm() {
    const record = selectedRecord();
    if (!record || !(elements.parameterForm instanceof HTMLElement)) return;
    renderParameterFields(elements.parameterForm, record, state.options, handleParameterChange);
    updateRuntimeControls();
}

function collectParameters() {
    return collectParameterValues(elements.parameterForm);
}

function handleParameterChange() {
    updateRuntimeControls();
    renderCodeExample();
}

function exportMarkdown() {
    if (!state.modules.length) return;
    downloadMarkdown(buildApiDocsMarkdown(state.modules, state.systems));
    showToast("API 文档 Markdown 已导出");
}

function renderCodeExample() {
    const record = selectedRecord();
    const target = document.getElementById("codeExample");
    if (!record || !(target instanceof HTMLElement)) return;
    target.textContent = state.codeLanguage === "python"
        ? buildPythonExample(record, collectParameters())
        : buildCurlExample(record, collectParameters());
}

function renderDocument() {
    if (!(elements.document instanceof HTMLElement)) return;
    elements.document.innerHTML = state.selectedView === "cookie"
        ? renderCookieDocument(state.systems, state.modules)
        : renderEndpointDocument(selectedRecord(), state.codeLanguage, collectParameters());
}

function applySessionStatus(systemId, status, notifyExpiry = false) {
    const wasReady = state.sessions.get(systemId)?.ready === true;
    state.sessions.set(systemId, status || null);
    const ready = status?.ready === true;
    if (wasReady && !ready) {
        state.options.clear();
        if (notifyExpiry) showToast(`${systemById(systemId)?.name || systemId} Cookie 已失效`, true);
    }
    if (!ready) setSavedCredentials(systemId, "");
    updateRuntimeControls();
}

function applySessionStatuses(statuses, notifyExpiry = false) {
    state.systems.forEach((system) => applySessionStatus(system.id, statuses?.[system.id] || null, notifyExpiry));
}

function setSavedCredentials(systemId, credentials) {
    const value = String(credentials || "");
    if (value) state.savedCredentials.set(systemId, value);
    else state.savedCredentials.delete(systemId);
    updateSessionPanel(systemId);
}

function renderSessionPanels() {
    if (!(elements.sessionPanels instanceof HTMLElement)) return;
    elements.sessionPanels.innerHTML = state.systems.map((system) => `
        <section class="console-panel credential-section system-session-panel" data-session-panel data-system-id="${escapeHtml(system.id)}">
            <div class="console-heading">
                <div><span class="console-kicker">${escapeHtml(system.shortName || system.id)}</span><h2>${escapeHtml(system.name)} Cookie</h2></div>
                <button class="text-button" type="button" data-session-action="clear" disabled>清除</button>
            </div>
            <label class="field-label" for="credential-${escapeHtml(system.id)}">${escapeHtml(system.credentialInputLabel || "Cookie Header 或 Copy as cURL")}</label>
            <textarea id="credential-${escapeHtml(system.id)}" rows="8" autocomplete="off" spellcheck="false" placeholder="${escapeHtml(system.credentialPlaceholder || "粘贴完整 Cookie Header 或 Copy as cURL")}" data-session-field="input" disabled></textarea>
            <button class="primary-button full-button" type="button" data-session-action="load" disabled>验证 Cookie</button>
            <div class="credential-status" data-session-field="status" data-state="idle">
                <strong data-session-field="status-text">Cookie 未验证</strong>
                <span data-session-field="status-detail">验证后每 1-60 秒自动检查一次</span>
            </div>
            <div class="saved-credential-panel" data-session-field="saved-panel" hidden>
                <div class="saved-credential-heading">
                    <label class="field-label" for="saved-credential-${escapeHtml(system.id)}">当前页 Cookie</label>
                    <button class="text-button" type="button" data-session-action="copy">复制</button>
                </div>
                <textarea id="saved-credential-${escapeHtml(system.id)}" class="saved-credential-text" rows="4" readonly spellcheck="false" data-session-field="saved-text"></textarea>
                <span class="saved-credential-note">刷新页面或清除 Cookie 后立即删除</span>
            </div>
        </section>
    `).join("");
    state.systems.forEach((system) => updateSessionPanel(system.id));
}

function sessionPanelBySystem(systemId) {
    if (!(elements.sessionPanels instanceof HTMLElement)) return null;
    return [...elements.sessionPanels.querySelectorAll("[data-session-panel]")]
        .find((panel) => panel.dataset.systemId === systemId) || null;
}

function sessionPanelElements(systemId) {
    const panel = sessionPanelBySystem(systemId);
    if (!panel) return null;
    return {
        panel,
        credentialInput: panel.querySelector('[data-session-field="input"]'),
        loadSessionButton: panel.querySelector('[data-session-action="load"]'),
        clearSessionButton: panel.querySelector('[data-session-action="clear"]'),
        credentialStatus: panel.querySelector('[data-session-field="status"]'),
        credentialStatusText: panel.querySelector('[data-session-field="status-text"]'),
        credentialStatusDetail: panel.querySelector('[data-session-field="status-detail"]'),
        savedCredentialPanel: panel.querySelector('[data-session-field="saved-panel"]'),
        savedCredentialText: panel.querySelector('[data-session-field="saved-text"]'),
    };
}

function updateSessionPanel(systemId) {
    const panelElements = sessionPanelElements(systemId);
    if (!panelElements) return;
    const system = systemById(systemId) || { name: systemId };
    const status = state.sessions.get(systemId) || null;
    const ready = status?.ready === true;
    const saved = state.savedCredentials.get(systemId) || "";
    if (panelElements.credentialInput) panelElements.credentialInput.disabled = !state.backendAvailable;
    if (panelElements.loadSessionButton) panelElements.loadSessionButton.disabled = !state.backendAvailable;
    if (panelElements.clearSessionButton) panelElements.clearSessionButton.disabled = !state.backendAvailable || !ready;
    if (panelElements.savedCredentialText) panelElements.savedCredentialText.value = saved;
    if (panelElements.savedCredentialPanel) panelElements.savedCredentialPanel.hidden = !saved;
    renderSessionStatus(panelElements, status, system.name);
}

function updateRuntimeControls() {
    const systemId = activeSystemId();
    const system = systemById(systemId) || { name: systemId };
    const status = activeSessionStatus();
    const ready = status?.ready === true;
    state.systems.forEach((item) => updateSessionPanel(item.id));
    if (elements.endpointSessionLabel) elements.endpointSessionLabel.textContent = `${system.name}会话`;
    renderSessionStatus({ sessionState: elements.sessionState, sessionDetail: elements.sessionDetail }, status, system.name);
    updateParameterAvailability(elements.parameterForm, ready);
    if (elements.sendRequestButton) {
        elements.sendRequestButton.disabled = !ready || state.activeExecution !== null;
        elements.sendRequestButton.textContent = selectedRecord()?.endpoint.executionKind === "local-workflow"
            ? selectedRecord()?.endpoint.name || "执行本地工作流"
            : "发送真实请求";
    }
}

function showSelectedView() {
    const cookieSelected = state.selectedView === "cookie";
    if (elements.sessionPanel) elements.sessionPanel.hidden = !cookieSelected;
    if (elements.endpointConsole) elements.endpointConsole.hidden = cookieSelected;
}

function selectCookie(systemId = "") {
    state.selectedView = "cookie";
    state.selectedId = "";
    renderNavigation();
    showSelectedView();
    renderDocument();
    updateRuntimeControls();
    if (systemId && systemById(systemId)) {
        window.requestAnimationFrame(() => sessionPanelBySystem(systemId)?.scrollIntoView({ block: "nearest" }));
    }
}

async function selectEndpoint(endpointId) {
    if (!state.endpointRecords.has(endpointId)) return;
    followProgressiveResponse = true;
    state.selectedView = "endpoint";
    state.selectedId = endpointId;
    renderNavigation();
    showSelectedView();
    renderParameterForm();
    renderDocument();
    clearResponse(elements);
    const record = selectedRecord();
    elements.sendRequestButton?.classList.toggle("is-write", record?.endpoint.risk === "write");
    await ensureDynamicOptions();
}

async function ensureDynamicOptions() {
    const sources = [...new Set(editableParameters(selectedRecord()).map((item) => item.optionSource).filter(Boolean))];
    if (!activeSessionReady() || !sources.length) return;
    try {
        for (const source of sources) {
            if (state.options.has(source)) continue;
            const payload = await fetchJson(`/api/options/${encodeURIComponent(source)}`);
            state.options.set(source, payload.options || []);
        }
        renderParameterForm();
        renderDocument();
    } catch (error) {
        showToast(error.message || String(error), true);
    }
}

async function detectBackend() {
    try {
        const health = await fetchJson("/api/health");
        state.backendAvailable = health.available === true;
        if (!state.backendAvailable) throw new Error("本地执行器不可用");
        const cleared = await fetchJson("/api/session", { method: "DELETE" });
        state.savedCredentials.clear();
        state.credentialDrafts.clear();
        applySessionStatuses(cleared.sessions);
        showToast("已连接本地执行器");
    } catch (_error) {
        state.backendAvailable = false;
        applySessionStatuses(null);
    }
    updateRuntimeControls();
    await ensureDynamicOptions();
    if (state.backendAvailable) window.setInterval(refreshSessionStatus, 3000);
}

async function refreshSessionStatus() {
    try {
        const health = await fetchJson("/api/health");
        state.backendAvailable = health.available === true;
        applySessionStatuses(health.sessions, true);
    } catch (_error) {
        state.backendAvailable = false;
        applySessionStatuses(null);
    }
}

async function loadSession(systemId) {
    const panelElements = sessionPanelElements(systemId);
    if (!state.backendAvailable || !(panelElements?.credentialInput instanceof HTMLTextAreaElement)) return;
    const system = systemById(systemId);
    try {
        panelElements.loadSessionButton.disabled = true;
        const payload = await fetchJson("/api/session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ systemId, credentials: panelElements.credentialInput.value })
        });
        const { credentials, ...sessionStatus } = payload;
        applySessionStatus(systemId, sessionStatus);
        setSavedCredentials(systemId, credentials);
        state.options.clear();
        state.credentialDrafts.delete(systemId);
        panelElements.credentialInput.value = "";
        updateRuntimeControls();
        showToast(`${system?.name || systemId} Cookie 已验证`);
        await ensureDynamicOptions();
    } catch (error) {
        applySessionStatus(systemId, null);
        showToast(error.message || String(error), true);
    } finally {
        updateRuntimeControls();
    }
}

async function clearSession(systemId) {
    if (!state.backendAvailable) return;
    const system = systemById(systemId);
    try {
        const payload = await fetchJson(`/api/session?systemId=${encodeURIComponent(systemId)}`, { method: "DELETE" });
        applySessionStatuses(payload.sessions);
        setSavedCredentials(systemId, "");
        state.credentialDrafts.delete(systemId);
        const input = sessionPanelElements(systemId)?.credentialInput;
        if (input) input.value = "";
        state.options.clear();
        showToast(`${system?.name || systemId} Cookie 已清除`);
    } catch (error) {
        showToast(error.message || String(error), true);
    }
}

function renderProgressiveExecution(task, endpointId) {
    if (state.selectedId !== endpointId) return;
    const result = task?.result;
    if (result) {
        renderResponse(elements, result);
        scrollProgressiveResponseToBottom();
    }
    const summary = result?.data?.summary || {};
    const completed = Number(summary.success || 0) + Number(summary.failed || 0);
    const target = Number(summary.target || 0);
    if (task?.state === "running") {
        elements.responseMeta.textContent = result
            ? `执行中 · ${completed}/${target}`
            : "扫描全部 OA 中";
    } else if (task?.state === "completed") {
        elements.responseMeta.textContent = `已完成 · ${completed}/${target}`;
    }
}

async function pollProgressiveExecution(initialTask, endpointId) {
    let task = initialTask;
    renderProgressiveExecution(task, endpointId);
    while (task.state === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 300));
        task = await fetchJson(`/api/execute/${encodeURIComponent(task.taskId)}`);
        renderProgressiveExecution(task, endpointId);
    }
    if (task.state === "failed") throw new Error(task.error || "本地执行任务失败");
    if (!task.result) throw new Error("本地执行任务没有返回结果");
    return task.result;
}

async function sendRequest() {
    const record = selectedRecord();
    const systemId = record?.module.systemId || "";
    if (!record || !activeSessionReady() || !elements.parameterForm?.reportValidity()) return;
    try {
        elements.sendRequestButton.disabled = true;
        elements.responseMeta.textContent = "请求中";
        const progressive = record.endpoint.progressive === true;
        if (progressive) followProgressiveResponse = true;
        const payload = await fetchJson("/api/execute", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                endpointId: record.fullId,
                parameters: collectParameters(),
                progressive,
            })
        });
        if (progressive) {
            state.activeExecution = { endpointId: record.fullId, taskId: payload.taskId };
            updateRuntimeControls();
            const result = await pollProgressiveExecution(payload, record.fullId);
            showToast(`OA 已阅完成：${result.data?.summary?.success || 0} 条`);
        } else {
            renderResponse(elements, payload);
            showToast(`请求完成：HTTP ${payload.status}`);
        }
    } catch (error) {
        const message = error.message || String(error);
        renderResponseError(elements, message);
        if (message.includes("Cookie")) {
            applySessionStatus(systemId, { ready: false, keepAlive: { state: "expired" } });
        }
        showToast(message, true);
    } finally {
        state.activeExecution = null;
        updateRuntimeControls();
    }
}

function bindEvents() {
    elements.cookieNav?.addEventListener("click", () => selectCookie());
    elements.sessionPanels?.addEventListener("input", (event) => {
        const input = event.target.closest('[data-session-field="input"]');
        const panel = input?.closest("[data-session-panel]");
        if (input && panel?.dataset.systemId) {
            state.credentialDrafts.set(panel.dataset.systemId, input.value);
        }
    });
    elements.sessionPanels?.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-session-action]");
        const panel = button?.closest("[data-session-panel]");
        const systemId = panel?.dataset.systemId || "";
        if (!button || !systemById(systemId)) return;
        if (button.dataset.sessionAction === "load") {
            await loadSession(systemId);
        } else if (button.dataset.sessionAction === "clear") {
            await clearSession(systemId);
        } else if (button.dataset.sessionAction === "copy") {
            const credentials = state.savedCredentials.get(systemId) || "";
            const copied = credentials
                ? await navigator.clipboard.writeText(credentials).then(() => true).catch(() => false)
                : false;
            showToast(copied ? "Cookie 已复制" : "复制失败，请手动选择", !copied);
        }
    });
    elements.endpointList?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-endpoint-id]");
        if (button) void selectEndpoint(button.dataset.endpointId || "");
    });
    elements.search?.addEventListener("input", () => {
        state.search = elements.search.value.trim().toLowerCase();
        renderNavigation();
    });
    elements.exportMarkdownButton?.addEventListener("click", exportMarkdown);
    elements.themeToggle?.addEventListener("click", () => window.WatchdogTheme?.toggleTheme());
    elements.manageSessionButton?.addEventListener("click", () => {
        selectCookie(selectedRecord()?.module.systemId || "");
    });
    elements.sendRequestButton?.addEventListener("click", sendRequest);
    elements.responseTable?.addEventListener("scroll", () => {
        followProgressiveResponse = isNearBottom(elements.responseTable);
    });
    elements.document?.addEventListener("click", async (event) => {
        const languageButton = event.target.closest("[data-code-language]");
        if (languageButton) {
            state.codeLanguage = languageButton.dataset.codeLanguage || "curl";
            renderDocument();
            return;
        }
        if (event.target.closest("#copyCodeButton")) {
            const text = document.getElementById("codeExample")?.textContent || "";
            const copied = await navigator.clipboard.writeText(text).then(() => true).catch(() => false);
            showToast(copied ? "调用示例已复制" : "复制失败，请手动选择", !copied);
        }
    });
    bindResponseTabs(elements.responseSection);
}

async function initialize() {
    bindEvents();
    try {
        await loadCatalog();
        if (elements.exportMarkdownButton) elements.exportMarkdownButton.disabled = false;
        renderSessionPanels();
        renderNavigation();
        selectCookie();
        clearResponse(elements);
    } catch (error) {
        elements.document.innerHTML = `<div class="document-loading">${escapeHtml(error.message || String(error))}</div>`;
        showToast(error.message || String(error), true);
        return;
    }
    await detectBackend();
}

initialize();
