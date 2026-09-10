import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { resolveFromDist, resolveFromRoot } from "../../helpers/paths";


describe("HTTP training arrangement delivery", () => {
  it("publishes the standalone workbench and Excel flow", () => {
    const root = resolveFromRoot("public/tool/app/http-training-arrangement-helper");
    const landing = readFileSync(resolveFromDist("tool/app/http-training-arrangement-helper/index.html"), "utf8");
    const html = readFileSync(`${root}/web/index.html`, "utf8");
    const script = readFileSync(`${root}/web/app.mjs`, "utf8");
    const requirements = readFileSync(`${root}/requirements.txt`, "utf8");

    expect(landing).toContain("训练安排查询（HTTP版）");
    expect(landing).toContain('href="../../../exports/http-training-arrangement-helper.zip"');
    expect(html).toContain("验证登录凭据");
    expect(html).toContain("设置查询条件");
    expect(html).toContain("加载训练类别");
    expect(html).toContain("导出 Excel");
    expect(html).toContain("一键导出区域默认配置");
    expect(html).toContain('id="summaryTable"');
    expect(script).toContain("/api/metadata/load");
    expect(script).toContain("/api/run");
    expect(script).toContain('mode: "area-default"');
    expect(script).toContain("renderSummary");
    expect(script).toContain("navigator.clipboard.writeText");
    expect(requirements).toContain("requests");
    expect(requirements).toContain("openpyxl");
    expect(requirements).not.toContain("playwright");
  });
});
