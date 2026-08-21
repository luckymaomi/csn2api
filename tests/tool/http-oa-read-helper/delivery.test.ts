import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { resolveFromRoot } from "../../helpers/paths";

describe("HTTP OA read helper delivery", () => {
  it("publishes the OA workbench controls and runtime assets", () => {
    const root = resolveFromRoot("public/tool/app/http-oa-read-helper");
    const landing = readFileSync(`${root}/index.html`, "utf8");
    const workbench = readFileSync(`${root}/web/index.html`, "utf8");
    const workbenchStyles = readFileSync(`${root}/web/styles.css`, "utf8");
    const requirements = readFileSync(`${root}/requirements.txt`, "utf8");
    const buildScript = readFileSync(resolveFromRoot("scripts/build.mts"), "utf8");
    const catalog = readFileSync(resolveFromRoot("src/tool/tools-data.ts"), "utf8");
    const pythonEntries = readdirSync(root).filter((name) => name.endsWith(".py")).sort();

    expect(pythonEntries).toEqual(["start.py"]);
    expect(landing).toContain("OA 已阅助手（HTTP版）");
    expect(landing).toContain('href="../../../exports/http-oa-read-helper.zip"');
    expect(workbench).toContain("验证凭据");
    expect(workbench).toContain("扫描全部待办");
    expect(workbench).toContain("开始已阅");
    expect(workbench).toContain("不同类型跳过");
    expect(workbench).toContain("纯 HTTP 逐条处理");
    expect(workbench).toContain("指定数量");
    expect(workbench).toContain("无限模式");
    expect(workbench).toContain('id="allMode" value="all" checked');
    expect(workbenchStyles).toContain(".mode-switch .btn-check:checked + .btn");
    expect(workbenchStyles).toContain(".mode-switch .btn::before");
    expect(requirements).toContain("requests");
    expect(buildScript).toContain('"http-oa-read-helper"');
    expect(catalog).toContain('entry: "http-oa-read-helper"');
  });
});
