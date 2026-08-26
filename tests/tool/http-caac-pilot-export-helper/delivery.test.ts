import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { resolveFromRoot } from "../../helpers/paths";

describe("CAAC pilot export delivery", () => {
  it("publishes the app, catalog and dynamic read-only workflow", () => {
    const root = resolveFromRoot("public/tool/app/http-caac-pilot-export-helper");
    const page = readFileSync(`${root}/web/index.html`, "utf8");
    const browser = readFileSync(`${root}/web/app.mjs`, "utf8");
    const server = readFileSync(`${root}/caac_pilot_export/server.py`, "utf8");
    const app = readFileSync(`${root}/caac_pilot_export/portal_client.py`, "utf8");
    const catalog = readFileSync(resolveFromRoot("public/tool/app/api-docs/catalog/caac-pilot-export.json"), "utf8");
    expect(page).toContain("全量抓取");
    expect(page).toContain("名单抓取");
    expect(page).toContain("下载名单模板");
    expect(page).toContain("复制凭据");
    expect(browser).toContain('./results_table.mjs');
    expect(server).toContain('"/results_table.mjs"');
    expect(app).toContain("fetch_all_pilots");
    expect(app).toContain("queryPilotDetails");
    expect(app).not.toContain("range(1, 42)");
    expect(catalog).toContain("queryPilotByParamForPage");
    expect(catalog).toContain("queryPilotDetails");
    expect(catalog).not.toContain("不能写死");
    expect(catalog).not.toContain("不下载图片");
  });
});
