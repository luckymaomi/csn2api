export function materializeCatalogModule(source) {
    const module = source && typeof source === "object" ? source : {};
    const defaults = module.endpointDefaults && typeof module.endpointDefaults === "object"
        ? module.endpointDefaults
        : {};
    const commonParameters = Array.isArray(module.commonParameters) ? module.commonParameters : [];
    const endpoints = (Array.isArray(module.endpoints) ? module.endpoints : []).map((endpoint) => {
        const merged = { ...structuredClone(defaults), ...endpoint };
        const ownParameters = Array.isArray(endpoint.parameters) ? endpoint.parameters : [];
        const names = new Set(ownParameters.map((parameter) => parameter.name));
        merged.parameters = [
            ...ownParameters,
            ...(endpoint.inheritCommonParameters === false
                ? []
                : commonParameters.filter((parameter) => !names.has(parameter.name))),
        ];
        return merged;
    });
    return { ...module, endpoints };
}

export function resolveRequestDefinition(requestRef, modules) {
    const [moduleId, requestId] = String(requestRef || "").split(".");
    const module = (modules || []).find((item) => item.id === moduleId);
    const request = (module?.requestDefinitions || []).find((item) => item.id === requestId);
    return module && request ? { module, request, requestRef } : null;
}

export function resolveSystemSessionRequests(system, modules) {
    const entries = [
        ["validation", system?.session?.validationRequestRef],
        ["identity", system?.session?.identityRequestRef],
        ["keepAlive", system?.session?.keepAliveRequestRef],
    ];
    const grouped = new Map();
    entries.forEach(([role, requestRef]) => {
        if (!requestRef) return;
        const existing = grouped.get(requestRef) || { roles: [], ...resolveRequestDefinition(requestRef, modules) };
        if (!existing.module || !existing.request) return;
        existing.roles.push(role);
        grouped.set(requestRef, existing);
    });
    return [...grouped.values()];
}

export function resolveEndpointExecution(module, endpoint, modules) {
    return (endpoint?.execution?.steps || []).map((step) => {
        if (step.requestRef === "$endpoint") {
            return { ...step, module, request: endpoint };
        }
        const resolved = resolveRequestDefinition(step.requestRef, modules);
        return resolved ? { ...step, ...resolved } : null;
    }).filter(Boolean);
}

export function resolveModuleRelatedRequests(module, modules) {
    return (module?.relatedRequests || []).map((relation) => {
        const resolved = resolveRequestDefinition(relation.requestRef, modules);
        return resolved ? { ...relation, ...resolved } : null;
    }).filter(Boolean);
}
