import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

import { resolveFromPublic } from "../../helpers/paths";

const appRoot = resolveFromPublic("tool", "app", "api-docs");

async function loadModules() {
  const normalize = await import(pathToFileURL(`${appRoot}/catalog-normalize.mjs`).href) as {
    materializeCatalogModule: (source: Record<string, unknown>) => Record<string, any>;
    resolveEndpointExecution: (
      module: Record<string, any>,
      endpoint: Record<string, any>,
      modules: Record<string, any>[],
    ) => Record<string, any>[];
    resolveModuleRelatedRequests: (
      module: Record<string, any>,
      modules: Record<string, any>[],
    ) => Record<string, any>[];
    resolveSystemSessionRequests: (
      system: Record<string, any>,
      modules: Record<string, any>[],
    ) => Record<string, any>[];
  };
  const view = await import(pathToFileURL(`${appRoot}/catalog-view.mjs`).href) as {
    renderEndpointDocument: (record: Record<string, any>, language: string, supplied: object) => string;
    renderModuleDocument: (module: Record<string, any>, system: Record<string, any>, modules: Record<string, any>[]) => string;
  };
  return { ...normalize, ...view };
}

function fixture() {
  const requestDefinitions = [
    {
      id: "session-check",
      name: "会话检查",
      purpose: "验证会话",
      risk: "read",
      method: "GET",
      path: "/session",
      parameters: [],
      response: "有效会话 JSON",
    },
    {
      id: "metadata",
      name: "元数据",
      purpose: "读取动态选项",
      risk: "read",
      method: "GET",
      path: "/metadata",
      parameters: [],
      response: "选项数组",
    },
  ];
  const module = {
    schemaVersion: 2,
    id: "example",
    systemId: "system",
    name: "示例模块",
    description: "示例说明",
    baseUrl: "https://example.test",
    navigationUrl: "https://example.test/home",
    cookies: [],
    commonHeaders: [],
    groups: [{ id: "group", name: "默认" }],
    requestDefinitions,
    relatedRequests: [{
      requestRef: "example.metadata",
      kind: "option-source",
      sourceId: "example-options",
      description: "页面动态选项",
    }],
    endpoints: [{
      id: "query",
      groupId: "group",
      name: "示例查询",
      summary: "直接查询",
      risk: "read",
      method: "GET",
      path: "/query",
      parameters: [],
      execution: {
        kind: "direct-http",
        steps: [{ id: "request", requestRef: "$endpoint", role: "primary", cardinality: "once" }],
      },
      response: { format: "JSON", statuses: [], fields: [] },
    }],
  };
  const system = {
    id: "system",
    name: "示例系统",
    session: {
      validationRequestRef: "example.session-check",
      keepAliveRequestRef: "example.session-check",
    },
  };
  return { module, system };
}

describe("API docs catalog v2", () => {
  it("resolves session roles, endpoint steps and module relations independently", async () => {
    const api = await loadModules();
    const { module, system } = fixture();
    const materialized = api.materializeCatalogModule(module);
    const sessions = api.resolveSystemSessionRequests(system, [materialized]);
    const steps = api.resolveEndpointExecution(materialized, materialized.endpoints[0], [materialized]);
    const related = api.resolveModuleRelatedRequests(materialized, [materialized]);

    expect(sessions).toHaveLength(1);
    expect(sessions[0].roles).toEqual(["validation", "keepAlive"]);
    expect(sessions[0].request.id).toBe("session-check");
    expect(steps).toHaveLength(1);
    expect(steps[0].request.id).toBe("query");
    expect(steps[0].requestRef).toBe("$endpoint");
    expect(related).toHaveLength(1);
    expect(related[0].request.id).toBe("metadata");
    expect(related[0].kind).toBe("option-source");
  });

  it("renders a direct execution chain, module relations and no empty response example", async () => {
    const api = await loadModules();
    const { module, system } = fixture();
    const materialized = api.materializeCatalogModule(module);
    const endpoint = materialized.endpoints[0];
    const endpointHtml = api.renderEndpointDocument(
      { module: materialized, endpoint, system, fullId: "example.query", modules: [materialized] },
      "curl",
      {},
    );
    const moduleHtml = api.renderModuleDocument(materialized, system, [materialized]);

    expect(endpointHtml).toContain("真实执行链路");
    expect(endpointHtml).toContain("https://example.test/query");
    expect(endpointHtml).not.toContain("模块相关请求");
    expect(endpointHtml).not.toContain("脱敏示例");
    expect(moduleHtml).toContain("模块相关请求");
    expect(moduleHtml).toContain("https://example.test/metadata");
    expect(moduleHtml).not.toContain("发送真实请求");
  });
});
