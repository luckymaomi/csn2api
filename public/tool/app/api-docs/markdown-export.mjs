import {
    materializeCatalogModule,
    resolveEndpointExecution,
    resolveModuleRelatedRequests,
    resolveSystemSessionRequests
} from "./catalog-normalize.mjs";

function text(value) {
    return String(value ?? "");
}

function inlineCode(value) {
    return `\`${text(value).replaceAll("`", "\\`")}\``;
}

function markdownTable(headers, rows) {
    const cell = (value) => text(value).replaceAll("|", "\\|").replace(/\r?\n/g, "<br>");
    const lines = [
        `| ${headers.map(cell).join(" | ")} |`,
        `| ${headers.map(() => "---").join(" | ")} |`
    ];
    if (rows.length) rows.forEach((row) => lines.push(`| ${row.map(cell).join(" | ")} |`));
    else lines.push(`| ${["无", ...headers.slice(1).map(() => "")].join(" | ")} |`);
    return lines.join("\n");
}

function requirement(parameter) {
    if (parameter.fixed || parameter.derived || parameter.derivedFrom || parameter.auto) return "自动生成";
    if (parameter.required) return "必填";
    if (parameter.requiredWhen) {
        const [name, value] = Object.entries(parameter.requiredWhen)[0] || [];
        return `${name}=${value} 时必填`;
    }
    return "可选";
}

function parameterSource(parameter) {
    if (parameter.auto) return `执行时生成 ${parameter.auto}`;
    if (parameter.derivedFrom) return `根据 ${parameter.derivedFrom.parameter}.${parameter.derivedFrom.field} 生成`;
    if (parameter.derived) return "由前置请求或业务输入计算";
    if (parameter.default !== undefined) return text(parameter.default);
    return "";
}

function parameterRules(parameter) {
    const rules = [];
    if (parameter.fixed) rules.push("固定字段");
    if (parameter.repeatable) rules.push("重复同名字段");
    if (parameter.includeWhenEmpty) rules.push("空值也发送");
    if (parameter.maxlength) rules.push(`最多 ${parameter.maxlength} 字符`);
    if (parameter.optionSource) rules.push(`动态选项：${parameter.optionSource}`);
    if (parameter.options?.length) rules.push(`选项：${parameter.options.map((item) => `${item.value}=${item.label}`).join("；")}`);
    return rules.join("；");
}

function parameterLocation(value) {
    return ({ query: "Query", form: "Form", json: "JSON", workflow: "本地工作流" })[value] || value;
}

function canonicalModule(module) {
    const { catalogSource: _catalogSource, ...source } = module;
    return source;
}

function sourceName(module) {
    const configured = text(module.catalogSource).split("/").pop();
    return configured || `${module.id}.json`;
}

function moduleIndex(modules, systems) {
    return {
        schemaVersion: 2,
        systems,
        modules: modules.map((module) => ({
            id: module.id,
            name: module.name,
            description: module.description,
            source: `./${sourceName(module)}`
        }))
    };
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
    return (request.parameters || []).map((parameter) => typeof parameter === "string" ? parameter : parameter.name).filter(Boolean);
}

function requestRole(item) {
    const roles = [
        ...(item.roles || []).map((role) => roleLabels[role] || role),
        item.role ? roleLabels[item.role] || item.role : "",
        item.cardinality ? cardinalityLabels[item.cardinality] || item.cardinality : "",
        item.kind ? relatedKindLabels[item.kind] || item.kind : "",
    ].filter(Boolean);
    return roles.join("、");
}

function appendRequestFact(lines, item, index) {
    const { module, request } = item;
    const headers = [...(module.commonHeaders || []), ...(request.headers || [])];
    const parameters = requestParameters(request);
    lines.push(
        `#### ${index + 1}. ${text(request.name)}`,
        "",
        `- 请求引用：${inlineCode(item.requestRef || "$endpoint")}`,
        `- 角色：${text(requestRole(item))}`,
        ...(request.risk === "write" ? ["- 风险：写操作"] : []),
        `- 方法：${inlineCode(request.method)}`,
        `- 完整 URL：${inlineCode(module.baseUrl + request.path)}`,
        `- 用途：${text(request.purpose || request.summary || "执行当前业务接口")}`,
        ...(item.condition ? [`- 触发条件：${text(item.condition)}`] : []),
        ...(item.stopCondition ? [`- 停止条件：${text(item.stopCondition)}`] : []),
        ...(item.description ? [`- 关系说明：${text(item.description)}`] : []),
        "- 请求 Headers：",
        ...(headers.length ? headers.map((header) => `  - ${inlineCode(header.name)}: ${inlineCode(header.value)}${header.description ? ` - ${text(header.description)}` : ""}`) : ["  - 无"]),
        "- 请求参数：",
        ...(parameters.length ? parameters.map((parameter) => `  - ${inlineCode(parameter)}`) : ["  - 无"]),
        `- 响应契约：${text(request.response?.format || request.response || "按当前端点响应契约处理")}`,
        ""
    );
}

function appendSystemGuide(lines, system, modules) {
    const module = modules.find((item) => item.systemId === system.id) || {};
    const sessions = resolveSystemSessionRequests(system, modules);
    lines.push(
        `### ${system.name}`,
        "",
        `- 系统 ID：${inlineCode(system.id)}`,
        `- 登录入口：${inlineCode(system.navigationUrl)}`,
        `- 建议抓取请求：${inlineCode(system.credentialRequestUrl)}`,
        "",
        markdownTable(["Cookie", "要求", "技术事实"], (module.cookies || []).map((cookie) => [
            inlineCode(cookie.name), cookie.required ? "必填" : "按当前请求保留", cookie.description || ""
        ])),
        "",
        "获取方法：",
        "",
    );
    (system.credentialSteps || []).forEach((step, index) => lines.push(`${index + 1}. ${text(step)}`));
    lines.push("", `说明：${text(system.credentialNote)}`, "", "会话请求：", "");
    sessions.forEach((request, index) => appendRequestFact(lines, request, index));
}

function appendEndpoint(lines, module, endpoint, index, modules) {
    const headers = [...(module.commonHeaders || []), ...(endpoint.headers || [])];
    const executionKind = endpoint.execution?.kind;
    lines.push(
        `### ${index + 1}. ${endpoint.name}`,
        "",
        `- 技术 ID：${inlineCode(`${module.id}.${endpoint.id}`)}`,
        `- 风险：${endpoint.risk === "write" ? "写操作" : "只读"}`,
        `- 方法：${inlineCode(endpoint.method)}`,
        `- 执行类型：${executionKind === "local-workflow" ? "本地组合工作流" : "生产 HTTP 请求"}`,
        ...(endpoint.progressive ? ["- 结果交付：本地任务快照；每条完成后立即追加结果"] : []),
        `- 完整 URL：${inlineCode(executionKind === "local-workflow" ? "http://127.0.0.1:<port>/api/execute" : module.baseUrl + endpoint.path)}`,
        `- 响应格式：${text(endpoint.response?.format)}`,
        "",
        text(endpoint.summary),
        "",
        "#### 请求 Headers",
        "",
        markdownTable(["名称", "值", "说明"], headers.map((header) => [inlineCode(header.name), inlineCode(header.value), header.description || ""])),
        "",
        "#### 请求参数",
        "",
        markdownTable(["名称", "位置", "类型", "要求", "默认或来源", "约束与选项", "说明"], (endpoint.parameters || []).map((parameter) => [
            inlineCode(parameter.name), parameterLocation(parameter.in), inlineCode(parameter.type || "text"), requirement(parameter), parameterSource(parameter), parameterRules(parameter), parameter.description || ""
        ])),
        "",
        "#### 响应状态",
        "",
        markdownTable(["HTTP 状态", "业务含义"], (endpoint.response?.statuses || []).map((status) => [inlineCode(status.code), status.description || ""])),
        "",
        "#### 响应字段",
        "",
        markdownTable(["名称", "类型", "说明"], (endpoint.response?.fields || []).map((field) => [inlineCode(field.name), inlineCode(field.type), field.description || ""])),
        ""
    );
    if (endpoint.response?.example) {
        lines.push("#### 脱敏响应示例", "", "```json", text(endpoint.response.example), "```", "");
    }
    lines.push("#### 真实执行链路", "");
    resolveEndpointExecution(module, endpoint, modules).forEach((request, requestIndex) => appendRequestFact(lines, request, requestIndex));
}

function appendRelatedRequests(lines, module, modules) {
    const related = resolveModuleRelatedRequests(module, modules);
    if (!related.length) return;
    lines.push("### 模块相关请求", "");
    related.forEach((request, index) => appendRequestFact(lines, request, index));
}

function appendModule(lines, module, index, modules) {
    module = materializeCatalogModule(module);
    lines.push(
        `## ${index + 1}. ${module.name}`,
        "",
        text(module.description),
        "",
        `- 模块 ID：${inlineCode(module.id)}`,
        `- 系统 ID：${inlineCode(module.systemId)}`,
        `- 基础地址：${inlineCode(module.baseUrl)}`,
        `- 门户导航：${inlineCode(module.navigationUrl)}`,
        "",
        "### 业务接口",
        ""
    );
    (module.endpoints || []).forEach((endpoint, endpointIndex) => appendEndpoint(lines, module, endpoint, endpointIndex, modules));
    appendRelatedRequests(lines, module, modules);
    if ((module.technicalNotes || []).length) {
        lines.push("### 技术说明", "", ...(module.technicalNotes || []).map((note) => `- ${text(note)}`), "");
    }
}

export function buildApiDocsMarkdown(modules, systems = []) {
    const catalogModules = (Array.isArray(modules) ? modules : []).map(materializeCatalogModule);
    const catalogSystems = Array.isArray(systems) ? systems : [];
    const lines = [
        "---",
        "documentType: csn2api-api-catalog",
        "schemaVersion: 2",
        "system: cross-system",
        "---",
        "",
        "# csn2api API 文档",
        "",
        "> 本文件由 API 文档目录生成。正文供人连续阅读，附录保留供程序读取的同源 JSON。",
        "",
        "## 使用边界",
        "",
        "- 本文件记录 HTTP 请求事实和明确标记的本地组合工作流，不替代独立业务工作台。",
        "- 写操作仍需调用者明确确认目标、日期和动作。",
        "- 导出不包含运行时 Cookie、真实响应、人员数据或本地会话状态。",
        "",
        "## 认证与会话",
        "",
        "IEB 与 OA 的 Cookie、Session 和保活请求彼此独立。Cookie 值由调用者从当前已登录会话提供；本文档只记录字段名称和认证事实。",
        ""
    ];
    catalogSystems.forEach((system) => appendSystemGuide(lines, system, catalogModules));
    catalogModules.forEach((module, index) => appendModule(lines, module, index, catalogModules));
    lines.push(
        "## 附录：机器可读原始目录",
        "",
        "以下 JSON 与页面和本地执行器使用的目录同源，用于保留字段、条件和分层请求契约。",
        "",
        "### 模块索引",
        "",
        "````json",
        JSON.stringify(moduleIndex(catalogModules, catalogSystems), null, 2),
        "````",
        ""
    );
    catalogModules.forEach((module) => lines.push(`### ${module.name} 原始目录`, "", "````json", JSON.stringify(canonicalModule(module), null, 2), "````", ""));
    return `${lines.join("\n").trim()}\n`;
}

export function downloadMarkdown(markdown, filename = "csn2api-api-docs.md") {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}
