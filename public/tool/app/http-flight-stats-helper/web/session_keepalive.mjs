export function createKeepAliveTimer() {
    let key = "";
    let startedAt = 0;
    return (session, now = Date.now()) => {
        const keepAlive = session?.keepAlive || {};
        const total = Number(keepAlive.nextIntervalSeconds || 0);
        const active = session?.verified === true && keepAlive.running === true && total > 0;
        if (!active) {
            key = "";
            startedAt = 0;
            return { active: false, total: 0, remaining: 0 };
        }
        const nextKey = `${keepAlive.lastCheckedAt || ""}|${total}`;
        if (nextKey !== key) {
            key = nextKey;
            startedAt = now;
        }
        return {
            active: true,
            total,
            remaining: Math.max(0, total - (now - startedAt) / 1000),
        };
    };
}

export function renderKeepAlive(elements, session, timer) {
    const keepAlive = session?.keepAlive || {};
    const countdown = timer(session);
    const ring = elements?.ring;
    const number = elements?.countdown;
    const status = elements?.status;
    const detail = elements?.detail;
    const state = keepAlive.state || (session?.verified ? "healthy" : "idle");
    if (ring) {
        ring.hidden = !countdown.active;
        ring.dataset.state = state;
        const progress = countdown.active
            ? ((countdown.total - countdown.remaining) / countdown.total) * 100
            : 0;
        ring.style.setProperty("--keepalive-progress", String(Math.max(0, Math.min(100, progress))));
        ring.setAttribute(
            "aria-label",
            countdown.active
                ? `下次保活将在 ${Math.ceil(countdown.remaining)} 秒后发送`
                : "等待 Cookie 验证",
        );
    }
    if (number) number.textContent = countdown.active ? String(Math.ceil(countdown.remaining)) : "--";
    if (status) status.textContent = state === "expired" ? "会话已失效" : state === "error" ? "保活请求异常" : countdown.active || session?.verified ? "保活运行中" : "保活未启动";
    if (!detail) return;
    if (state === "expired") {
        detail.textContent = "保活检查失败，会话已失效，请重新验证";
    } else if (state === "error") {
        detail.textContent = `${keepAlive.error || "保活检查请求异常"}，将在下一轮重试`;
    } else if (countdown.active) {
        detail.textContent = `保活独立检查 · 下次检查约 ${Math.ceil(countdown.remaining)} 秒`;
    } else if (session?.verified) {
        detail.textContent = "保活独立检查已启动 · 每 30-60 秒一次";
    } else {
        detail.textContent = "验证后启动保活独立检查";
    }
}
