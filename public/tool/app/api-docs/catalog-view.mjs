import {
    resolveEndpointExecution,
    resolveModuleRelatedRequests,
    resolveSystemSessionRequests
} from "./catalog-normalize.mjs";

export function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function table(headers, rows, className = "") {
    const body = rows.length
        ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")
        : `<tr><td colspan="${headers.length}" class="empty-cell">暂无数据</td></tr>`;
    return `<div class="doc-table-shell"><table class="doc-table ${className}">
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>${body}</tbody>
    </table></div>`;
}

function requirement(parameter) {
    if (parameter.fixed || parameter.derived || parameter.derivedFrom || parameter.auto) return "自动生成";
    if (parameter.required) return `<span class="required">必填</span>`;
    if (parameter.requiredWhen) {
        const [name, value] = Object.entries(parameter.requiredWhen)[0] || [];
        return `<span class="conditional">${escapeHtml(`${name}=${value} 时必填`)}</span>`;
    }
    return "可选";
}

function parameterValue(parameter) {
    if (parameter.auto) return `执行时生成 ${parameter.auto}`;
    if (parameter.derivedFrom) return `根据 ${parameter.derivedFrom.parameter}.${parameter.derivedFrom.field} 生成`;
    if (parameter.derived) return "由前置请求或业务输入计算";
    if (parameter.default !== undefined) return String(parameter.default);
    return "";
}

function shellSingleQuote(value) {
    return `'${String(value).replaceAll("'", `'"'"'`)}'`;
}

function exampleValue(parameter, supplied) {
    if (parameter.auto) return `<${parameter.auto}>`;
    if (parameter.derivedFrom) return `<根据 ${parameter.derivedFrom.parameter} 自动生成>`;
    if (parameter.derived) return `<执行器自动生成>`;
    const value = supplied[parameter.name] ?? parameter.default;
    if (value !== undefined && value !== "") return String(value);
    return parameter.placeholder ? `<${parameter.placeholder}>` : "";
}

function exampleValues(parameter, supplied) {
    const value = exampleValue(parameter, supplied);
    const suppliedValue = supplied[parameter.name];
    if (!parameter.repeatable || suppliedValue === undefined || String(suppliedValue).trim() === "") return [value];
    return String(suppliedValue).split(/[,，\n]+/).map((item) => item.trim()).filter(Boolean);
}

function exampleJsonValue(parameter, supplied) {
    const value = supplied[parameter.name] ?? parameter.default;
    if (value === null) return null;
    if (parameter.type === "number" && String(value ?? "").trim() !== "") {
        const numeric = Number(value);
        return Number.isSafeInteger(numeric) ? numeric : String(value);
    }
    return exampleValue(parameter, supplied);
}

function cookieExample(module) {
    const cookies = module.cookies || [];
    return cookies.length
        ? cookies.map((cookie) => `${cookie.name}=<value>`).join("; ")
        : "<current-system-cookie>";
}

function parameterLocation(value) {
    return ({ query: "Query", form: "Form", json: "JSON", workflow: "本地工作流" })[value] || value;
}

export function buildCurlExample(record, supplied) {
    const { module, endpoint } = record;
    if (endpoint.execution?.kind === "local-workflow") {
        const parameters = Object.fromEntries(
            (endpoint.parameters || []).map((parameter) => [parameter.name, exampleJsonValue(parameter, supplied)])
        );
        const body = JSON.stringify({
            endpointId: record.fullId,
            parameters,
            ...(endpoint.progressive ? { progressive: true } : {})
        });
        const lines = [
            `curl --request POST ${shellSingleQuote("http://127.0.0.1:<port>/api/execute")} \\`,
            `  --header ${shellSingleQuote("Content-Type: application/json")} \\`,
            `  --data-raw ${shellSingleQuote(body)}`
        ];
        if (endpoint.progressive) {
            lines.push(
                "",
                "# 从启动响应取得 taskId 后，重复读取快照直到 state 不再是 running",
                `curl ${shellSingleQuote("http://127.0.0.1:<port>/api/execute/<taskId>")}`
            );
        }
        return lines.join("\n");
    }
    const query = [];
    const form = [];
    const jsonBody = {};
    (endpoint.parameters || []).forEach((parameter) => {
        if (parameter.in === "json") {
            jsonBody[parameter.name] = exampleJsonValue(parameter, supplied);
        } else {
            const target = parameter.in === "query" ? query : form;
            exampleValues(parameter, supplied).forEach((value) => target.push([parameter.name, value]));
        }
    });
    const queryText = query.length
        ? `?${query.map(([name, value]) => `${encodeURIComponent(name)}=${encodeURIComponent(value)}`).join("&")}`
        : "";
    const lines = [
        `curl --request ${endpoint.method} ${shellSingleQuote(module.baseUrl + endpoint.path + queryText)}`,
        `  --header ${shellSingleQuote(`Cookie: ${cookieExample(module)}`)}`
    ];
    [...(module.commonHeaders || []), ...(endpoint.headers || [])]
        .forEach((header) => lines.push(`  --header ${shellSingleQuote(`${header.name}: ${header.value}`)}`));
    form.forEach(([name, value]) => lines.push(`  --data-urlencode ${shellSingleQuote(`${name}=${value}`)}`));
    if (Object.keys(jsonBody).length) {
        lines.push(`  --data-raw ${shellSingleQuote(JSON.stringify(jsonBody))}`);
    }
    return lines.map((line, index) => index === lines.length - 1 ? line : `${line} \\`).join("\n");
}

export function buildPythonExample(record, supplied) {
    const { module, endpoint } = record;
    if (endpoint.execution?.kind === "local-workflow") {
        const parameters = Object.fromEntries(
            (endpoint.parameters || []).map((parameter) => [parameter.name, exampleJsonValue(parameter, supplied)])
        );
        const requestBody = {
            endpointId: record.fullId,
            parameters,
            ...(endpoint.progressive ? { progressive: true } : {})
        };
        const formattedBody = JSON.stringify(requestBody, null, 4).replaceAll("\n", "\n    ");
        if (endpoint.progressive) {
            return `import time\nimport requests\n\nbase_url = "http://127.0.0.1:<port>"\ntask = requests.post(\n    f"{base_url}/api/execute",\n    json=${formattedBody},\n    timeout=30,\n).json()\nshown = 0\nwhile True:\n    rows = ((task.get("result") or {}).get("data") or {}).get("tables", [{}])[0].get("rows", [])\n    for row in rows[shown:]:\n        print(row)\n    shown = len(rows)\n    if task["state"] != "running":\n        break\n    time.sleep(0.3)\n    task = requests.get(f"{base_url}/api/execute/{task['taskId']}", timeout=30).json()\nprint(task)`;
        }
        return `import requests\n\nresponse = requests.post(\n    "http://127.0.0.1:<port>/api/execute",\n    json=${formattedBody},\n    timeout=None,\n)\nprint(response.status_code)\nprint(response.text)`;
    }
    const params = [];
    const data = [];
    const jsonBody = {};
    (endpoint.parameters || []).forEach((parameter) => {
        if (parameter.in === "json") {
            jsonBody[parameter.name] = exampleJsonValue(parameter, supplied);
        } else {
            const target = parameter.in === "query" ? params : data;
            exampleValues(parameter, supplied).forEach((value) => target.push([parameter.name, value]));
        }
    });
    const headers = Object.fromEntries(
        [...(module.commonHeaders || []), ...(endpoint.headers || [])]
            .map((header) => [header.name, header.value])
    );
    headers.Cookie = cookieExample(module);
    const args = [
        `    ${JSON.stringify(module.baseUrl + endpoint.path)},`,
        `    headers=${JSON.stringify(headers, null, 4).replaceAll("\n", "\n    ")},`
    ];
    if (params.length) args.push(`    params=${JSON.stringify(params, null, 4).replaceAll("\n", "\n    ")},`);
    if (data.length) args.push(`    data=${JSON.stringify(data, null, 4).replaceAll("\n", "\n    ")},`);
    if (Object.keys(jsonBody).length) args.push(`    json=${JSON.stringify(jsonBody, null, 4).replaceAll("\n", "\n    ")},`);
    args.push("    timeout=30,", ")");
    return `import requests\n\nresponse = requests.${endpoint.method.toLowerCase()}(\n${args.join("\n")}\nprint(response.status_code)\nprint(response.text)`;
}

const roleLabels = {
    validation: "会话验证",
    identity: "当前使用人",
    keepAlive: "后台保活",
    primary: "主请求",
    prerequisite: "前置请求",
    "page-loop": "分页循环",
    "item-loop": "逐项循环",
    postcondition: "结果核对"
};

const cardinalityLabels = {
    once: "1 次",
    "zero-or-one": "0 或 1 次",
    "one-or-more": "1 次或多次",
    "zero-or-more": "0 次或多次"
};

const relatedKindLabels = {
    metadata: "模块元数据",
    "option-source": "动态选项",
    export: "原生导出",
    "reference-query": "相关查询",
    "state-action": "状态动作"
};

function requestParameters(request) {
    return (request.parameters || []).map((parameter) => (
        typeof parameter === "string" ? parameter : parameter.name
    )).filter(Boolean);
}

function requestBadges(item) {
    const badges = [];
    (item.roles || []).forEach((role) => badges.push(roleLabels[role] || role));
    if (item.role) badges.push(roleLabels[item.role] || item.role);
    if (item.cardinality) badges.push(cardinalityLabels[item.cardinality] || item.cardinality);
    if (item.kind) badges.push(relatedKindLabels[item.kind] || item.kind);
    return badges;
}

function requestList(items) {
    return `<div class="request-fact-list">${items.map((item, index) => {
        const { module, request } = item;
        const headers = [...(module.commonHeaders || []), ...(request.headers || [])];
        const parameters = requestParameters(request);
        const context = [
            item.condition ? `触发条件：${item.condition}` : "",
            item.stopCondition ? `停止条件：${item.stopCondition}` : "",
            item.description ? `关系说明：${item.description}` : "",
        ].filter(Boolean);
        return `<article class="request-fact" data-request-ref="${escapeHtml(item.requestRef || "$endpoint")}">
            <header class="request-fact-header">
                <span class="request-order">${String(index + 1).padStart(2, "0")}</span>
                <span class="request-identity"><strong>${escapeHtml(request.name)}</strong><code>${escapeHtml(item.requestRef || "$endpoint")}</code></span>
                <span class="method${request.method === "POST" ? " is-post" : ""}">${escapeHtml(request.method)}</span>
                <code class="request-url">${escapeHtml(module.baseUrl + request.path)}</code>
                <span class="request-context-badges">${requestBadges(item).map((label) => `<span>${escapeHtml(label)}</span>`).join("")}</span>
                ${request.risk === "write" ? `<span class="risk-badge is-write">写操作</span>` : ""}
            </header>
            <div class="request-fact-details">
                ${context.length ? `<section class="request-context" aria-label="执行条件">${context.map((line) => `<p>${escapeHtml(line)}</p>`).join("")}</section>` : ""}
                <section class="request-detail-block" aria-label="${escapeHtml(request.name)}请求 Headers">
                    <h3>请求 Headers <span>${headers.length} 项</span></h3>
                    ${table(["名称", "值", "说明"], headers.map((header) => [
                        `<code>${escapeHtml(header.name)}</code>`,
                        `<code>${escapeHtml(header.value)}</code>`,
                        escapeHtml(header.description || "")
                    ]))}
                </section>
                <section class="request-detail-block" aria-label="${escapeHtml(request.name)}请求参数">
                    <h3>请求参数 <span>${parameters.length} 项</span></h3>
                    ${parameters.length
                        ? `<ul class="request-parameter-list">${parameters.map((parameter) => `<li><code>${escapeHtml(parameter)}</code></li>`).join("")}</ul>`
                        : `<p class="request-empty-value">无请求参数</p>`}
                </section>
                <section class="request-detail-block request-contract" aria-label="${escapeHtml(request.name)}用途与响应契约">
                    <div class="contract-item"><h3>用途</h3><p>${escapeHtml(request.purpose || request.summary || "执行当前业务接口")}</p></div>
                    <div class="contract-item"><h3>响应契约</h3><p>${escapeHtml(request.response?.format || request.response || "按当前端点响应契约处理")}</p></div>
                </section>
            </div>
        </article>`;
    }).join("")}</div>`;
}

function systemCookieGuide(system, modules) {
    const systemModules = modules.filter((module) => module.systemId === system.id);
    const cookies = systemModules[0]?.cookies || [];
    const sessionRequests = resolveSystemSessionRequests(system, modules);
    return `<section class="doc-section cookie-system-guide">
        <div class="section-heading-row"><h2>${escapeHtml(system.name)}</h2><span class="scope-badge">${escapeHtml(system.shortName || system.name)}</span></div>
        <div class="address-block">
            <div class="address-row"><span class="address-label">登录入口</span><a href="${escapeHtml(system.navigationUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(system.navigationUrl)}</a></div>
            <div class="address-row"><span class="address-label">抓取请求</span><a href="${escapeHtml(system.credentialRequestUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(system.credentialRequestUrl)}</a></div>
        </div>
        <h3>认证字段</h3>
        ${table(["Cookie", "要求", "说明"], cookies.map((cookie) => [
            `<code>${escapeHtml(cookie.name)}</code>`,
            cookie.required ? `<span class="required">必填</span>` : "按当前请求保留",
            escapeHtml(cookie.description || "")
        ]))}
        <h3>获取方法</h3>
        <ol class="fact-list ordered">${(system.credentialSteps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
        <p class="fact-note cookie-guide-note">${escapeHtml(system.credentialNote || "")}</p>
        <h3>会话请求</h3>
        ${requestList(sessionRequests)}
    </section>`;
}

export function renderCookieDocument(systems, modules) {
    return `
        <div class="breadcrumb">HTTP 系统 / 身份验证</div>
        <div class="endpoint-title-row"><h1>Cookie 管理</h1><span class="scope-badge">按系统隔离</span></div>
        <p class="endpoint-summary">IEB 与 OA 分别维护自己的 Cookie、Session 和保活请求。凭据只保存在当前页面和 Python 进程内存中，刷新即清除，不在系统之间共享。</p>
        ${systems.map((system) => systemCookieGuide(system, modules)).join("")}`;
}

export function renderModuleDocument(module, system, modules) {
    const related = resolveModuleRelatedRequests(module, modules);
    const endpointCount = (module.endpoints || []).length;
    return `
        <div class="breadcrumb">${escapeHtml(system?.name || module.systemId)} / 模块概览</div>
        <div class="endpoint-title-row"><h1>${escapeHtml(module.name)}</h1><span class="scope-badge">${endpointCount} 个接口</span></div>
        <p class="endpoint-summary">${escapeHtml(module.description || "")}</p>
        <section class="address-block" aria-label="模块地址">
            <div class="address-row"><span class="address-label">门户导航</span><a href="${escapeHtml(module.navigationUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(module.navigationUrl)}</a></div>
            <div class="address-row"><span class="address-label">基础地址</span><code>${escapeHtml(module.baseUrl)}</code></div>
        </section>
        ${related.length ? `<section class="doc-section"><h2>模块相关请求</h2>${requestList(related)}</section>` : ""}`;
}

export function renderEndpointDocument(record, codeLanguage, supplied) {
    const { module, endpoint } = record;
    const system = record.system || { name: module.systemId };
    const cookies = module.cookies || [];
    const headers = [...(module.commonHeaders || []), ...(endpoint.headers || [])];
    const statuses = endpoint.response?.statuses || [];
    const fields = endpoint.response?.fields || [];
    const example = codeLanguage === "python"
        ? buildPythonExample(record, supplied)
        : buildCurlExample(record, supplied);
    const parameters = endpoint.parameters || [];
    const executionKind = endpoint.execution?.kind;
    const executionSteps = resolveEndpointExecution(module, endpoint, record.modules || [module]);
    const responseExample = endpoint.response?.example;
    return `
        <div class="breadcrumb">${escapeHtml(system.name)} / ${escapeHtml(module.name)}</div>
        <div class="endpoint-title-row">
            <h1>${escapeHtml(endpoint.name)}</h1>
            <span class="risk-badge${endpoint.risk === "write" ? " is-write" : ""}">${endpoint.risk === "write" ? "写操作" : "只读"}</span>
        </div>
        <p class="endpoint-summary">${escapeHtml(endpoint.summary)}</p>

        <section class="address-block" aria-label="接口地址">
            <div class="address-row">
                <span class="address-label">门户导航</span>
                <a href="${escapeHtml(module.navigationUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(module.navigationUrl)}</a>
            </div>
            <div class="address-row">
                <span class="address-label">${executionKind === "local-workflow" ? "本地执行" : "HTTP 请求"}</span>
                <span class="method${endpoint.method === "POST" ? " is-post" : ""}">${escapeHtml(endpoint.method)}</span>
                <code>${escapeHtml(executionKind === "local-workflow" ? "/api/execute" : module.baseUrl + endpoint.path)}</code>
            </div>
        </section>

        <section class="doc-section">
            <h2>Cookie</h2>
            ${table(["名称", "要求", "说明"], cookies.map((cookie) => [
                `<code>${escapeHtml(cookie.name)}</code>`,
                cookie.required ? `<span class="required">必填</span>` : "可选",
                escapeHtml(cookie.description || "")
            ]))}
        </section>

        <section class="doc-section">
            <h2>请求 Headers</h2>
            ${table(["名称", "值", "说明"], headers.map((header) => [
                `<code>${escapeHtml(header.name)}</code>`,
                `<code>${escapeHtml(header.value)}</code>`,
                escapeHtml(header.description || "")
            ]))}
        </section>

        <section class="doc-section">
            <h2>请求参数</h2>
            ${table(["名称", "位置", "控件 / 类型", "要求", "默认或来源", "说明"], parameters.map((parameter) => [
                `<code>${escapeHtml(parameter.name)}</code>`,
                escapeHtml(parameterLocation(parameter.in)),
                escapeHtml(parameter.type || "text"),
                requirement(parameter),
                `<code>${escapeHtml(parameterValue(parameter))}</code>`,
                escapeHtml(parameter.description || "")
            ]), "parameter-table")}
        </section>

        <section class="doc-section">
            <div class="section-heading-row">
                <h2>调用示例</h2>
                <div class="code-actions">
                    <div class="code-tabs" role="tablist" aria-label="示例语言">
                        <button class="code-tab${codeLanguage === "curl" ? " is-active" : ""}" type="button" data-code-language="curl" role="tab" aria-selected="${codeLanguage === "curl"}">cURL</button>
                        <button class="code-tab${codeLanguage === "python" ? " is-active" : ""}" type="button" data-code-language="python" role="tab" aria-selected="${codeLanguage === "python"}">Python</button>
                    </div>
                    <button id="copyCodeButton" class="icon-button compact" type="button" title="复制调用示例" aria-label="复制调用示例">复制</button>
                </div>
            </div>
            <pre class="example-block"><code id="codeExample">${escapeHtml(example)}</code></pre>
        </section>

        <section class="doc-section">
            <h2>响应契约</h2>
            <h3>状态码</h3>
            ${table(["状态码", "说明"], statuses.map((status) => [
                `<code>${escapeHtml(status.code)}</code>`,
                escapeHtml(status.description || "")
            ]))}
            <h3>返回字段 · ${escapeHtml(endpoint.response?.format || "")}</h3>
            ${table(["字段", "类型", "说明"], fields.map((field) => [
                `<code>${escapeHtml(field.name)}</code>`,
                escapeHtml(field.type || ""),
                escapeHtml(field.description || "")
            ]))}
            ${responseExample ? `<h3>脱敏示例</h3><pre class="example-block">${escapeHtml(responseExample)}</pre>` : ""}
        </section>

        <section class="doc-section">
            <h2>真实执行链路</h2>
            ${requestList(executionSteps)}
        </section>`;
}
