import "./home-pattern-gate";
import type { ToolHomepageState, ToolItem } from "./models";
import { tools } from "./tools-data";

const homepageStateLabels: Record<ToolHomepageState, string> = {
    enabled: "已启用",
    beta: "Beta 测试",
    cooling: "冷却中"
};

const toolList = document.getElementById("toolList");
const homeThemeToggle = document.getElementById("homeThemeToggle");

bindHomeThemeToggle();
renderToolList(tools);

function bindHomeThemeToggle(): void {
    if (!(homeThemeToggle instanceof HTMLButtonElement) || !window.WatchdogTheme) return;

    const syncToggle = (): void => {
        const isDark = window.WatchdogTheme?.getTheme() === "dark";
        const label = isDark ? "切换到白天模式" : "切换到暗夜模式";
        homeThemeToggle.setAttribute("aria-label", label);
        homeThemeToggle.setAttribute("aria-pressed", String(isDark));
        homeThemeToggle.title = label;
    };

    homeThemeToggle.addEventListener("click", () => {
        window.WatchdogTheme?.toggleTheme();
    });
    window.addEventListener("watchdog:themechange", syncToggle);
    syncToggle();
}

function renderToolList(rows: ToolItem[]): void {
    if (!(toolList instanceof HTMLElement)) return;

    toolList.innerHTML = rows
        .map((item) => renderToolListItem(item))
        .join("");
}

function renderToolListItem(item: ToolItem): string {
    const state = item.homepageState || "enabled";
    const enabled = state === "enabled" || state === "beta";
    const stateLabel = homepageStateLabels[state];
    const content = `
        <div class="tool-card-heading">
            <div>
                <h2 class="tool-card-title">${escapeHtml(item.name)}</h2>
                <span class="tool-state-label">${escapeHtml(stateLabel)}</span>
            </div>
            <span class="tool-status-switch" role="img" aria-label="首页入口${escapeHtml(stateLabel)}">
                <span aria-hidden="true"></span>
            </span>
        </div>
        <p class="tool-desc">${escapeHtml(item.desc)}</p>
    `;
    return `
        <article class="tool-card is-${escapeHtml(state)} ${enabled ? "is-enabled" : "is-inactive"}">
            ${enabled
                ? `<a class="tool-card-surface" href="${escapeHtml(resolveToolUrl(item))}" target="_blank" rel="noopener noreferrer">${content}</a>`
                : `<div class="tool-card-surface" aria-disabled="true">${content}</div>`}
            <a
                class="tool-card-download"
                href="${escapeHtml(resolveToolExportUrl(item))}"
                download
                aria-label="下载${escapeHtml(item.name)}独立应用"
                title="下载${escapeHtml(item.name)}独立应用"
            >
                <svg class="bi bi-file-earmark-arrow-down tool-download-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" focusable="false">
                    <path d="M8 5a.5.5 0 0 1 .5.5v3.793l1.146-1.147a.5.5 0 0 1 .708.708l-2 2a.5.5 0 0 1-.708 0l-2-2a.5.5 0 1 1 .708-.708L7.5 9.293V5.5A.5.5 0 0 1 8 5Z"/>
                    <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5L14 4.5ZM9.5 1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V5h-2a1.5 1.5 0 0 1-1.5-1.5V1Zm1 0v2.5a.5.5 0 0 0 .5.5h2.5l-3-3Z"/>
                </svg>
            </a>
        </article>
    `;
}

function resolveToolUrl(item: ToolItem): string {
    return `./app/${item.entry}/index.html`;
}

function resolveToolExportUrl(item: ToolItem): string {
    return `../exports/${item.entry}.zip`;
}

function escapeHtml(value: unknown): string {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
