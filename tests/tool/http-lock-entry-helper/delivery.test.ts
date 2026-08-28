import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { resolveFromDist, resolveFromRoot } from "../../helpers/paths";

describe("HTTP lock entry delivery", () => {
  it("publishes one direct-entry app and the staged workbench", () => {
    const root = resolveFromRoot("public/tool/app/http-lock-entry-helper");
    const landing = readFileSync(resolveFromDist("tool/app/http-lock-entry-helper/index.html"), "utf8");
    const workbench = readFileSync(`${root}/web/index.html`, "utf8");
    const browser = readFileSync(`${root}/web/app.mjs`, "utf8");
    const requirements = readFileSync(`${root}/requirements.txt`, "utf8");
    const exporter = readFileSync(resolveFromRoot("scripts/tool-exports.mts"), "utf8");
    const pythonEntries = readdirSync(root).filter((name) => name.endsWith(".py")).sort();

    expect(pythonEntries).toEqual(["start.py"]);
    expect(landing).toContain("锁班皇帝（新）");
    expect(workbench).toContain("锁班皇帝（新）");
    expect(readFileSync(`${root}/start.py`, "utf8")).toContain("csn2api_runtime.single_app");
    expect(landing).toContain('href="../../../exports/http-lock-entry-helper.zip"');
    expect(workbench).toContain("验证凭据");
    expect(workbench).toContain("数据健康检查");
    expect(workbench).toContain("开始录入");
    expect(workbench).toContain("逐条录入结果");
    expect(browser).toContain('["冲突原因", "conflictReason"]');
    expect(workbench).not.toContain("conflictRecovery");
    expect(workbench).not.toContain("智能模式");
    expect(workbench).toContain('id="approveAfterSubmit" type="checkbox"');
    expect(requirements).toContain("requests");
    expect(requirements).not.toContain("playwright");
    expect(exporter).toContain('relativePath === "web/theme.js"');
  });

  it("registers the tool and keeps local result workbooks out of delivery", () => {
    const catalog = readFileSync(resolveFromRoot("src/tool/tools-data.ts"), "utf8");
    const ignore = readFileSync(resolveFromRoot(".gitignore"), "utf8");
    const exporter = readFileSync(resolveFromRoot("scripts/tool-exports.mts"), "utf8");

    expect(catalog).toContain('entry: "http-lock-entry-helper"');
    expect(ignore).toContain("/public/tool/app/http-lock-entry-helper/results/");
    expect(exporter).toContain("!isRuntimeGeneratedPath(relativePath)");
  });
});
