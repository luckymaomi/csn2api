import { escapeHtml } from "./catalog-view.mjs";

export function createToast(element) {
    let timer = 0;
    return (message, isError = false) => {
        if (!(element instanceof HTMLElement)) return;
        window.clearTimeout(timer);
        element.textContent = message;
        element.classList.toggle("is-error", isError);
        element.hidden = false;
        timer = window.setTimeout(() => { element.hidden = true; }, 2600);
    };
}

export function renderEndpointNavigation(container, systems, modules, records, selection, search) {
    const visible = records.filter((record) => {
        if (!search) return true;
        const value = `${record.endpoint.name} ${record.endpoint.path} ${record.endpoint.summary}`.toLowerCase();
        return value.includes(search);
    });
    if (!visible.length) {
        container.innerHTML = `<p class="empty-parameters">没有匹配接口</p>`;
        return;
    }
    const renderRecord = (record) => `<button class="endpoint-nav${record.fullId === selection.endpointId ? " is-active" : ""}" type="button" data-endpoint-id="${escapeHtml(record.fullId)}">
        <span class="method${record.endpoint.method === "POST" ? " is-post" : ""}">${escapeHtml(record.endpoint.method)}</span>
        <span class="endpoint-nav-name">${escapeHtml(record.endpoint.name.replace(/接口$/, ""))}</span>
    </button>`;
    const grouped = systems.map((system) => {
        const systemRecords = visible.filter((record) => record.module.systemId === system.id);
        if (!systemRecords.length) return "";
        const groups = [];
        systemRecords.forEach((record) => {
            const groupName = String(record.module.navigationGroup || record.module.name || "业务接口");
            let group = groups.find((item) => item.name === groupName);
            if (!group) {
                group = { name: groupName, records: [] };
                groups.push(group);
            }
            group.records.push(record);
        });
        const groupHtml = groups.map((group) => {
            const active = group.records.some((record) => record.fullId === selection.endpointId);
            const endpointHtml = group.records.map(renderRecord).join("");
            return `<details class="nav-module"${active || !search ? " open" : ""}>
                <summary><span class="nav-summary-label">${escapeHtml(group.name)}</span><span class="nav-count">${group.records.length}</span></summary>
                <div class="nav-module-items">${endpointHtml}</div>
            </details>`;
        }).join("");
        const navigationHtml = system.id === "oa"
            ? systemRecords.map(renderRecord).join("")
            : groupHtml;
        const active = systemRecords.some((record) => record.fullId === selection.endpointId);
        return `<details class="nav-system"${active || !search ? " open" : ""}>
            <summary><span class="nav-summary-label">${escapeHtml(system.name || system.id)}</span><span class="nav-count">${systemRecords.length}</span></summary>
            <div class="nav-system-items">${navigationHtml}</div>
        </details>`;
    }).join("");
    container.innerHTML = grouped || `<p class="empty-parameters">没有匹配接口</p>`;
}

function checkedTime(value) {
    const match = String(value || "").match(/T(\d{2}:\d{2}:\d{2})/);
    return match ? match[1] : "尚未检查";
}

export function renderSessionStatus(elements, status, systemName = "当前系统", countdown = null) {
    const keepAlive = status?.keepAlive || {};
    const identity = status?.identity || {};
    let statusText = "Cookie 未验证";
    let detailText = "验证后每 30-60 秒自动检查一次";
    let visualState = "idle";
    if (keepAlive.state === "expired") {
        statusText = "Cookie 已失效";
        detailText = `最近检查 ${checkedTime(keepAlive.lastCheckedAt)}`;
        visualState = "expired";
    } else if (status?.ready && keepAlive.state === "checking") {
        statusText = "正在验证 Cookie";
        detailText = `最近有效 ${checkedTime(keepAlive.lastCheckedAt)}`;
        visualState = "healthy";
    } else if (status?.ready && keepAlive.state === "error") {
        statusText = "自动验证请求异常";
        detailText = `${keepAlive.error || `连接${systemName}失败`}，将在下一轮重试`;
        visualState = "error";
    } else if (status?.ready) {
        statusText = "Cookie 有效";
        detailText = `最近验证 ${checkedTime(keepAlive.lastCheckedAt)} · 每 30-60 秒自动检查`;
        visualState = "healthy";
    }
    if (elements.credentialStatus) elements.credentialStatus.dataset.state = visualState;
    if (elements.credentialStatusText) elements.credentialStatusText.textContent = statusText;
    if (elements.credentialStatusDetail) elements.credentialStatusDetail.textContent = detailText;
    if (elements.sessionState) elements.sessionState.textContent = statusText;
    if (elements.sessionDetail) elements.sessionDetail.textContent = detailText;
    const identityText = status?.ready && identity.staffNumber && identity.name
        ? `当前使用人 ${identity.staffNumber} · ${identity.name}`
        : "当前使用人 未识别";
    if (elements.credentialIdentity) elements.credentialIdentity.textContent = identityText;
    if (elements.sessionIdentity) elements.sessionIdentity.textContent = identityText;
    const ring = elements.keepAliveRing;
    const countdownText = elements.keepAliveCountdown;
    const activeCountdown = status?.ready === true && countdown && Number(countdown.total) > 0;
    if (ring) {
        ring.hidden = !activeCountdown;
        ring.dataset.state = visualState;
        const total = Number(countdown?.total || 0);
        const remaining = Math.max(0, Number(countdown?.remaining || 0));
        ring.style.setProperty("--keepalive-progress", activeCountdown ? String(((total - remaining) / total) * 100) : "0");
        ring.setAttribute("aria-label", activeCountdown ? `下次保活将在 ${Math.ceil(remaining)} 秒后发送` : "等待 Cookie 验证");
    }
    if (countdownText) countdownText.textContent = activeCountdown ? String(Math.ceil(Math.max(0, Number(countdown.remaining)))) : "--";
}
