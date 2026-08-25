import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { resolveFromRoot } from "../../helpers/paths";

describe("CAAC pilot export delivery", () => {
  it("publishes the app, catalog and dynamic read-only workflow", () => {
    const root = resolveFromRoot("public/tool/app/http-caac-pilot-export-helper");
    const page = readFileSync(`${root}/web/index.html`, "utf8");
    const app = readFileSync(`${root}/caac_pilot_export/portal_client.py`, "utf8");
    const catalog = readFileSync(resolveFromRoot("public/tool/app/api-docs/catalog/caac-pilot-export.json"), "utf8");
    expect(page).toContain("开始全量抓取");
    expect(page).toContain("复制凭据");
    expect(app).toContain("fetch_all_pilots");
    expect(app).toContain("queryPilotDetails");
    expect(app).not.toContain("range(1, 42)");
    expect(catalog).toContain("queryPilotByParamForPage");
    expect(catalog).toContain("queryPilotDetails");
  });
});
