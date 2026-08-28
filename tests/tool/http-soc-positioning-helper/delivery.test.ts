import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { loadToolsData } from "../../helpers/browser-context";
import { resolveFromDist, resolveFromRoot } from "../../helpers/paths";

describe("SOC positioning delivery", () => {
  it("publishes the standalone workbench and dictionary template", () => {
    const root = resolveFromRoot("public", "tool", "app", "http-soc-positioning-helper");
    const landing = readFileSync(resolveFromDist("tool/app/http-soc-positioning-helper/index.html"), "utf8");
    const page = readFileSync(`${root}/web/index.html`, "utf8");
    const app = readFileSync(`${root}/web/app.mjs`, "utf8");
    const template = readFileSync(`${root}/template.xlsx`);
    const tool = loadToolsData()?.find((item) => item.entry === "http-soc-positioning-helper");
    expect(tool).toBeTruthy();
    expect(landing).toContain(tool!.name);
    expect(landing).toContain('download="http-soc-positioning-helper.zip"');
    expect(page).not.toContain("下载录入模板");
    expect(page).toContain("数据检查");
    expect(page).toContain("开始录入");
    expect(page).toContain("申请原因");
    expect(template.byteLength).toBeGreaterThan(1000);
    expect(app).toContain("session_keepalive.mjs");
    expect(app).not.toContain("员工号未识别");
    expect(readFileSync(resolveFromRoot("src", "tool", "tools-data.ts"), "utf8")).toContain("http-soc-positioning-helper");
  });
});
