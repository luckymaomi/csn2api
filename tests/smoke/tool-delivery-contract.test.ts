import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import JSZip from "jszip";
import { describe, expect, it } from "vitest";

import { loadToolsData } from "../helpers/browser-context";
import { resolveFromDist, resolveFromRoot } from "../helpers/paths";

type ToolManifest = {
  format: string;
  schemaVersion: number;
  entry: string;
  name: string;
  root: string;
  files: string[];
};

const tools = loadToolsData() || [];

function relativeAssetReferences(html: string): string[] {
  return [...html.matchAll(/(?:href|src)=["']([^"']+)["']/gi)]
    .map((match) => match[1].split(/[?#]/, 1)[0])
    .filter((reference) => {
      if (!reference || /^(?:[a-z]+:|\/|#|data:|mailto:)/i.test(reference)) return false;
      return /\.(?:css|m?js)$/i.test(reference);
    });
}

describe("registered tool delivery contract", () => {
  it("covers every registered tool", () => {
    expect(tools.length).toBeGreaterThan(0);
  });

  it.each(tools)("publishes a complete standalone application for $entry", async (tool) => {
    const builtLandingPath = resolveFromDist("tool", "app", tool.entry, "index.html");
    const archivePath = resolveFromDist("exports", `${tool.entry}.zip`);

    expect(existsSync(builtLandingPath), `${tool.entry} 缺少详情入口页`).toBe(true);
    const expectedHref = `href="../../../exports/${tool.entry}.zip"`;
    const expectedDownload = `download="${tool.entry}.zip"`;
    for (const pagePath of [builtLandingPath]) {
      expect(existsSync(pagePath), `${tool.entry} 缺少构建后的详情入口页`).toBe(true);
      const html = readFileSync(pagePath, "utf8");
      expect(html, `${tool.entry} 详情入口没有对应 ZIP 链接`).toContain(expectedHref);
      expect(html, `${tool.entry} 详情入口没有固定下载文件名`).toContain(expectedDownload);
      expect(html, `${tool.entry} 详情入口没有下载命令`).toContain("下载独立应用");
    }

    expect(existsSync(archivePath), `${tool.entry} 缺少独立应用 ZIP`).toBe(true);
    expect(statSync(archivePath).size, `${tool.entry} 的独立应用 ZIP 为空`).toBeGreaterThan(1000);

    const zip = await JSZip.loadAsync(readFileSync(archivePath));
    const manifestFile = zip.file("csn2api-tool.json");
    expect(manifestFile, `${tool.entry} 的 ZIP 缺少 csn2api-tool.json`).not.toBeNull();
    const manifest = JSON.parse(await manifestFile!.async("string")) as ToolManifest;
    expect(manifest).toMatchObject({
      format: "csn2api-standalone-tool",
      schemaVersion: 1,
      entry: tool.entry,
      name: tool.name,
      root: "index.html",
    });

    const archiveFiles = Object.values(zip.files)
      .filter((file) => !file.dir)
      .map((file) => file.name)
      .sort((left, right) => left.localeCompare(right, "en"));
    expect(manifest.files).toEqual(archiveFiles);
    expect(zip.file(manifest.root), `${tool.entry} 的 manifest root 不存在`).not.toBeNull();

    const sourceWorkbenchPath = resolveFromRoot("public", "tool", "app", tool.entry, "web", "index.html");
    if (existsSync(sourceWorkbenchPath)) {
      expect(zip.file("start.py"), `${tool.entry} 的 ZIP 缺少统一启动入口`).not.toBeNull();
      expect(zip.file("csn2api_runtime/single_app.py"), `${tool.entry} 的 ZIP 缺少共享启动运行时`).not.toBeNull();
      expect(zip.file("csn2api_runtime/application.py"), `${tool.entry} 的 ZIP 缺少服务生命周期实现`).not.toBeNull();
      expect(zip.file("credential_text/__init__.py"), `${tool.entry} 的 ZIP 缺少共享凭据文本规范化`).not.toBeNull();
      const workbench = await zip.file("web/index.html")?.async("string");
      expect(workbench, `${tool.entry} 的 ZIP 缺少 Python 工作台入口`).toBeTruthy();
      expect(workbench).toContain('<script src="./theme.js"></script>');
      expect(workbench).toContain('<link rel="stylesheet" href="./libs/bootstrap.min.css">');
      expect(workbench).toContain('<link rel="stylesheet" href="./theme.css">');
      expect(workbench).toContain('<link rel="stylesheet" href="./styles.css">');
    }

    for (const htmlPath of archiveFiles.filter((file) => file.endsWith(".html"))) {
      const html = await zip.file(htmlPath)!.async("string");
      for (const reference of relativeAssetReferences(html)) {
        const assetPath = path.posix.normalize(path.posix.join(path.posix.dirname(htmlPath), reference));
        expect(assetPath.startsWith("../"), `${htmlPath} 的资源引用越出 ZIP：${reference}`).toBe(false);
        const asset = zip.file(assetPath);
        expect(asset, `${htmlPath} 引用了 ZIP 中不存在的资源：${reference}`).not.toBeNull();
        expect((await asset!.async("uint8array")).byteLength, `${assetPath} 为空`).toBeGreaterThan(20);
      }
    }
  });
});
