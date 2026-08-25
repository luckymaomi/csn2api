import { readFileSync, readdirSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { assertJavaScriptSyntax } from "../../helpers/syntax";
import { resolveFromPublic, resolveFromRoot } from "../../helpers/paths";

const root = resolveFromPublic("tool", "app", "api-docs");

describe("API docs delivery", () => {
  it("exposes API docs from the top navigation instead of the tool catalog", () => {
    const toolIndex = readFileSync(resolveFromPublic("tool", "index.html"), "utf8");
    const toolCatalog = readFileSync(resolveFromRoot("src", "tool", "tools-data.ts"), "utf8");
    expect(toolIndex).toContain('href="./app/api-docs/index.html"');
    expect(toolIndex).toContain('title="API 文档"');
    expect(toolCatalog).toContain('entry: "http-qualification-query-helper"');
  });

  it("presents cross-system cookie management and the documented API entries", () => {
    const html = readFileSync(`${root}/index.html`, "utf8");
    expect(html).toContain("Cookie 管理");
    expect(html).toContain('id="sessionPanels"');
    expect(html).toContain('id="sendRequestButton"');
    expect(html).toContain('id="exportMarkdownButton"');
    expect(html).toContain('data-response-view="table"');
    expect(html).toContain('data-response-view="json"');
    expect(html).toContain('data-response-view="raw"');
    expect(html).toContain('data-response-view="headers"');
    const app = readFileSync(`${root}/app.mjs`, "utf8");
    expect(app).toContain('data-session-panel');
    expect(app).toContain("state.systems.map");
    expect(app).toContain('data-session-action="load"');
    expect(app).toContain('data-session-action="clear"');
    expect(app).toContain('data-session-action="copy"');
  });

  it("keeps the current business catalogs and v2 request roles", () => {
    const index = JSON.parse(readFileSync(`${root}/catalog/index.json`, "utf8"));
    expect(index.modules.map((module: { name: string }) => module.name)).toEqual(expect.arrayContaining([
      "飞行经历查询接口",
      "飞行人员锁班接口",
      "飞行人员信息查询接口",
      "OA 公文已阅接口",
      "SOC 随机置位申请接口",
      "CAAC 飞行员全量信息接口"
    ]));
    expect(index.systems.map((system: { id: string }) => system.id)).toEqual(["flight-portal", "oa", "soc", "caac-fsop"]);
    expect(index.systems[0].navigationUrl).toBe("https://ieb.csair.com/index/index");
    expect(index.systems[1].credentialRequestUrl).toBe("https://work.csair.com/oai/work/box/query/waiting");
    const lockCatalog = JSON.parse(readFileSync(`${root}/catalog/lock-entry.json`, "utf8"));
    expect(lockCatalog.endpoints).toHaveLength(1);
    expect(JSON.stringify(lockCatalog)).toContain("showNonproductionTaskImportPage");
    expect(JSON.stringify(lockCatalog)).toContain("importNonproductionTaskLockListToSoc");
    const personnelCatalog = JSON.parse(readFileSync(`${root}/catalog/personnel-info.json`, "utf8"));
    expect(personnelCatalog.groups.map((group: { name: string }) => group.name)).toEqual([
      "基础信息",
      "技术等级",
      "运行资格",
      "训练检查记录"
    ]);
    expect(personnelCatalog.endpoints).toHaveLength(5);
    const oaCatalog = JSON.parse(readFileSync(`${root}/catalog/oa-read.json`, "utf8"));
    expect(oaCatalog.endpoints.map((endpoint: { id: string }) => endpoint.id)).toEqual([
      "count",
      "read"
    ]);
    expect(oaCatalog.schemaVersion).toBe(2);
    expect(oaCatalog.endpoints[0].execution.kind).toBe("local-workflow");
    expect(oaCatalog.endpoints[1].execution.kind).toBe("local-workflow");
    expect(oaCatalog.endpoints[1].progressive).toBe(true);
    expect(oaCatalog.endpoints[1].execution.steps.map((step: { id: string }) => step.id)).toEqual([
      "scan-waiting",
      "mark-read",
    ]);
    expect(lockCatalog.relatedRequests.some((item: { kind: string }) => item.kind === "state-action")).toBe(true);
  });

  it("keeps browser responsibilities in syntax-valid ESM modules", () => {
    const modules = readdirSync(root).filter((name) => name.endsWith(".mjs"));
    expect(modules.length).toBeGreaterThanOrEqual(3);
    modules.forEach((name) => assertJavaScriptSyntax(`${root}/${name}`));
    const app = readFileSync(`${root}/app.mjs`, "utf8");
    expect(app).toContain("setInterval(refreshSessionStatus, 3000)");
    expect(app).toContain("Cookie 已验证");
    expect(app).toContain('fetchJson("/api/session", { method: "DELETE" })');
    expect(app).toContain("pollProgressiveExecution");
    expect(app).toContain("followProgressiveResponse");
    expect(app).toContain("scrollProgressiveResponseToBottom");
    expect(app).toContain('elements.responseTable?.addEventListener("scroll"');
  });

  it("renders v2 execution and related request facts", () => {
    const catalogView = readFileSync(`${root}/catalog-view.mjs`, "utf8");
    expect(catalogView).toContain("真实执行链路");
    expect(catalogView).toContain("模块相关请求");
    expect(catalogView).toContain("请求参数");
    expect(catalogView).toContain("用途");
    expect(catalogView).toContain("响应契约");
  });

  it("renders the portal hierarchy as expandable navigation", () => {
    const shell = readFileSync(`${root}/ui-shell.mjs`, "utf8");
    expect(shell).toContain("<details class=\"nav-system\"");
    expect(shell).toContain("<details class=\"nav-module\"");
    expect(shell).toContain("system.id === \"oa\"");
    expect(shell).toContain("data-endpoint-id");
    expect(shell).not.toContain("员工号未识别");
  });
});
