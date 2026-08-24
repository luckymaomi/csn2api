import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { resolveFromRoot } from "../../helpers/paths";

describe("SOC positioning delivery", () => {
  it("publishes the standalone workbench and dictionary template", () => {
    const root = resolveFromRoot("public", "tool", "app", "http-soc-positioning-helper");
    const landing = readFileSync(`${root}/index.html`, "utf8");
    const page = readFileSync(`${root}/web/index.html`, "utf8");
    const app = readFileSync(`${root}/web/app.mjs`, "utf8");
    const template = readFileSync(`${root}/template.xlsx`);
    expect(landing).toContain("SOC 随机置位批量工作台");
    expect(landing).toContain('download="随机置位录入模板.xlsx"');
    expect(landing).toContain("下载随机置位录入模板");
    expect(page).not.toContain("下载录入模板");
    expect(page).toContain("数据检查");
    expect(page).toContain("开始录入");
    expect(page).toContain("申请原因");
    expect(template.byteLength).toBeGreaterThan(1000);
    expect(app).toContain("session_keepalive.mjs");
    expect(readFileSync(resolveFromRoot("src", "tool", "tools-data.ts"), "utf8")).toContain("http-soc-positioning-helper");
    expect(readFileSync(resolveFromRoot("scripts", "build.mts"), "utf8")).toContain("http-soc-positioning-helper");
  });
});
