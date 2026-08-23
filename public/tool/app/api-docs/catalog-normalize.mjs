export function materializeCatalogModule(source) {
  const module = source && typeof source === "object" ? source : {};
  const defaults = module.endpointDefaults && typeof module.endpointDefaults === "object"
    ? module.endpointDefaults
    : {};
  const commonParameters = Array.isArray(module.commonParameters) ? module.commonParameters : [];
  const endpoints = (Array.isArray(module.endpoints) ? module.endpoints : []).map((endpoint) => {
    const merged = { ...defaults, ...endpoint };
    const ownParameters = Array.isArray(endpoint.parameters) ? endpoint.parameters : [];
    const names = new Set(ownParameters.map((parameter) => parameter.name));
    merged.parameters = [...ownParameters, ...commonParameters.filter((parameter) => !names.has(parameter.name))];
    return merged;
  });
  return { ...module, endpoints };
}
