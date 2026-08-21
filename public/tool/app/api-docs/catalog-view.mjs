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
    if (endpoint.executionKind === "local-workflow") {
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
    if (endpoint.executionKind === "local-workflow") {
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

function validationRequest(system, modules) {
    const [moduleId, requestId] = String(system.validationRequestId || "").split(".");
    const module = modules.find((item) => item.id === moduleId) || {};
    const request = (module.internalRequests || []).find((item) => item.id === requestId) || {};
    return { module, request };
}

function systemCookieGuide(system, modules) {
    const systemModules = modules.filter((module) => module.systemId === system.id);
    const cookies = systemModules[0]?.cookies || [];
    const validation = validationRequest(system, modules);
    return `<section class="doc-section cookie-system-guide">
        <div class="section-heading-row"><h2>${escapeHtml(system.name)}</h2><span class="scope-badge">${escapeHtml(system.shortName || system.name)}</span></div>
        <div class="address-block">
            <div class="address-row"><span class="address-label">登录入口</span><a href="${escapeHtml(system.navigationUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(system.navigationUrl)}</a></div>
            <div class="address-row"><span class="address-label">抓取请求</span><a href="${escapeHtml(system.credentialRequestUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(system.credentialRequestUrl)}</a></div>
        </div>
        <h3>认证字段</h3>
        ${table(["Cookie", "要求", "技术事实"], cookies.map((cookie) => [
            `<code>${escapeHtml(cookie.name)}</code>`,
            cookie.required ? `<span class="required">必填</span>` : "按当前请求保留",
            escapeHtml(cookie.description || "")
        ]))}
        <h3>获取方法</h3>
        <ol class="fact-list ordered">${(system.credentialSteps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
        <p class="fact-note cookie-guide-note">${escapeHtml(system.credentialNote || "")}</p>
        <h3>会话验证请求</h3>
        ${table(["方法", "请求地址", "有效响应"], [[
            `<span class="method${validation.request.method === "POST" ? " is-post" : ""}">${escapeHtml(validation.request.method || "")}</span>`,
            `<code>${escapeHtml((validation.module.baseUrl || "") + (validation.request.path || ""))}</code>`,
            escapeHtml(validation.request.response || "")
        ]])}
    </section>`;
}

export function renderCookieDocument(systems, modules) {
    return `
        <div class="breadcrumb">HTTP 系统 / 身份验证</div>
        <div class="endpoint-title-row"><h1>Cookie 管理</h1><span class="scope-badge">按系统隔离</span></div>
        <p class="endpoint-summary">IEB 与 OA 分别维护自己的 Cookie、Session 和保活请求。凭据只保存在当前页面和 Python 进程内存中，刷新即清除，不在系统之间共享。</p>
        ${systems.map((system) => systemCookieGuide(system, modules)).join("")}
        <section class="doc-section">
            <h2>机器可读目录</h2>
            <p class="machine-source"><a href="./catalog/index.json" target="_blank" rel="noopener noreferrer"><code>./catalog/index.json</code></a><span>接口模块索引，与页面展示和本地执行器同源。</span></p>
        </section>`;
}

function internalRequestList(module) {
    return `<div class="internal-request-list">${(module.internalRequests || []).map((request, index) => `
        <article class="internal-request" data-internal-request-id="${escapeHtml(request.id)}">
            <header class="internal-request-header">
                <span class="request-order">${String(index + 1).padStart(2, "0")}</span>
                <span class="request-identity"><strong>${escapeHtml(request.name)}</strong><code>${escapeHtml(request.id)}</code></span>
                <span class="method${request.method === "POST" ? " is-post" : ""}">${escapeHtml(request.method)}</span>
                <code class="request-url">${escapeHtml(module.baseUrl + request.path)}</code>
            </header>
            <div class="internal-request-details">
                <section class="request-detail-block" aria-label="${escapeHtml(request.name)}请求 Headers">
                    <h3>请求 Headers <span>${[...(module.commonHeaders || []), ...(request.headers || [])].length} 项</span></h3>
                    ${table(["名称", "值", "说明"], [...(module.commonHeaders || []), ...(request.headers || [])].map((header) => [
                        `<code>${escapeHtml(header.name)}</code>`,
                        `<code>${escapeHtml(header.value)}</code>`,
                        escapeHtml(header.description || "")
                    ]))}
                </section>
                <section class="request-detail-block" aria-label="${escapeHtml(request.name)}请求参数">
                    <h3>请求参数 <span>${(request.parameters || []).length} 项</span></h3>
                    ${(request.parameters || []).length
                        ? `<ul class="request-parameter-list">${request.parameters.map((parameter) => `<li><code>${escapeHtml(parameter)}</code></li>`).join("")}</ul>`
                        : `<p class="request-empty-value">无请求参数</p>`}
                </section>
                <section class="request-detail-block request-contract" aria-label="${escapeHtml(request.name)}用途与响应契约">
                    <div class="contract-item"><h3>用途</h3><p>${escapeHtml(request.purpose || "")}</p></div>
                    <div class="contract-item"><h3>响应契约</h3><p>${escapeHtml(request.response || "")}</p></div>
                </section>
            </div>
        </article>`).join("")}</div>`;
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
                <span class="address-label">${endpoint.executionKind === "local-workflow" ? "本地执行" : "HTTP 请求"}</span>
                <span class="method${endpoint.method === "POST" ? " is-post" : ""}">${escapeHtml(endpoint.method)}</span>
                <code>${escapeHtml(endpoint.executionKind === "local-workflow" ? "/api/execute" : module.baseUrl + endpoint.path)}</code>
            </div>
            <div class="address-row">
                <span class="address-label">机器可读 JSON</span>
                <a href="${escapeHtml(module.catalogSource)}" target="_blank" rel="noopener noreferrer"><code>${escapeHtml(module.catalogSource)}</code></a>
                <span class="address-description">页面与本地执行器共用的完整事实源</span>
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
            <h3>脱敏示例</h3>
            <pre class="example-block">${escapeHtml(endpoint.response?.example || "")}</pre>
        </section>

        <section class="doc-section">
            <h2>内部请求链路</h2>
            <p class="section-description">这些请求是当前业务接口的组成事实，不作为独立业务入口。</p>
            ${internalRequestList(module)}
        </section>

        <section class="doc-section">
            <h2>技术说明</h2>
            <ul class="fact-list">${(module.technicalNotes || []).map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>
        </section>`;
}
