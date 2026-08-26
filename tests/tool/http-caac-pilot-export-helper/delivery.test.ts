import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { resolveFromRoot } from "../../helpers/paths";
import { isRuntimeGeneratedPath } from "../../../scripts/tool-exports.mjs";

describe("CAAC pilot export delivery", () => {
  it("publishes the app, catalog and dynamic read-only workflow", () => {
    const root = resolveFromRoot("public/tool/app/http-caac-pilot-export-helper");
    const page = readFileSync(`${root}/web/index.html`, "utf8");
    const browser = readFileSync(`${root}/web/app.mjs`, "utf8");
    const resultTable = readFileSync(`${root}/web/results_table.mjs`, "utf8");
    const styles = readFileSync(`${root}/web/styles.css`, "utf8");
    const server = readFileSync(`${root}/caac_pilot_export/server.py`, "utf8");
    const app = readFileSync(`${root}/caac_pilot_export/portal_client.py`, "utf8");
    const protocol = readFileSync(resolveFromRoot("public/tool/app/_shared/caac_protocol/client.py"), "utf8");
    const apiAdapter = readFileSync(resolveFromRoot(
      "public/tool/app/api-docs/api_docs/systems/caac/adapter.py"
    ), "utf8");
    const catalog = readFileSync(resolveFromRoot("public/tool/app/api-docs/catalog/caac-pilot-export.json"), "utf8");
    expect(page).toContain("全量抓取");
    expect(page).toContain("名单抓取");
    expect(page).toContain("下载名单模板");
    expect(page).toContain("复制凭据");
    expect(browser).toContain('./results_table.mjs');
    expect(styles).toMatch(/\.result-viewport\s*\{[^}]*height:\s*460px;[^}]*overflow:\s*auto;/s);
    expect(resultTable).toContain('querySelector("tbody tr:last-child")');
    expect(resultTable).not.toContain("elements.viewport.scrollHeight");
    expect(server).toContain('"/results_table.mjs"');
    expect(app).toContain("fetch_all_pilots");
    expect(app).toContain("CaacProtocolClient");
    expect(app).not.toContain("queryPilotDetails");
    expect(app).not.toContain("range(1, 42)");
    expect(apiAdapter).toContain("CaacProtocolClient");
    expect(protocol).toContain('DETAIL_PATH = "/yzzzm/rygl/queryPilotDetails"');
    expect(protocol).toContain("resolve_by_name");
    expect(catalog).toContain("queryPilotByParamForPage");
    expect(catalog).toContain("queryPilotDetails");
    expect(catalog).toContain("按姓名查询单个飞行员详情");
    expect(catalog).not.toContain("不能写死");
    expect(catalog).not.toContain("不下载图片");
  });

  it("limits long result cells to 100 Unicode characters in the browser only", async () => {
    const root = resolveFromRoot("public/tool/app/http-caac-pilot-export-helper");
    const module = await import(pathToFileURL(`${root}/web/results_table.mjs`).href) as {
      formatResultCell(value: unknown): { fullText: string; text: string; truncated: boolean };
    };

    expect(module.formatResultCell("甲".repeat(100))).toEqual({
      fullText: "甲".repeat(100),
      text: "甲".repeat(100),
      truncated: false,
    });
    expect(module.formatResultCell("乙".repeat(101))).toEqual({
      fullText: "乙".repeat(101),
      text: `${"乙".repeat(100)}...`,
      truncated: true,
    });
    expect(module.formatResultCell("😀".repeat(100)).truncated).toBe(false);
  });

  it("keeps local runtime results out of every build output", () => {
    const build = readFileSync(resolveFromRoot("scripts/build.mts"), "utf8");

    expect(isRuntimeGeneratedPath("tool/app/http-caac-pilot-export-helper/results/run/result.xlsx")).toBe(true);
    expect(isRuntimeGeneratedPath("tool/app/http-caac-pilot-export-helper/__pycache__/server.pyc")).toBe(true);
    expect(isRuntimeGeneratedPath("tool/app/http-caac-pilot-export-helper/web/results_table.mjs")).toBe(false);
    expect(build).toContain("isRuntimeGeneratedPath");
  });
});
