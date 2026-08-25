import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { walkFiles } from "../helpers/fs-collect";
import { resolveFromDist } from "../helpers/paths";

describe("shared theme assets", () => {
  const toolAppHtmlFiles = walkFiles(resolveFromDist("tool", "app"), [".html"]);
  const pythonWorkbenchHtmlFiles = toolAppHtmlFiles.filter((htmlFilePath) =>
    /\/http-[^/]+-helper\/(?:web\/)?index\.html$/.test(htmlFilePath.replace(/\\/g, "/"))
  );

  it("are present in dist", () => {
    expect(fs.existsSync(resolveFromDist("theme.js"))).toBe(true);
    expect(fs.existsSync(resolveFromDist("theme.css"))).toBe(true);
  });

  it("are loaded by every tool app page", () => {
    toolAppHtmlFiles.forEach((htmlFilePath) => {
      const html = fs.readFileSync(htmlFilePath, "utf8");

      expect(html, `${htmlFilePath} does not load theme.js`).toContain("theme.js");
      expect(html, `${htmlFilePath} does not load theme.css`).toContain("theme.css");
    });
  });

  it("loads the standard stylesheet stack in every Python workbench", () => {
    pythonWorkbenchHtmlFiles.forEach((htmlFilePath) => {
      const html = fs.readFileSync(htmlFilePath, "utf8");

      expect(html, `${htmlFilePath} does not load Bootstrap`).toContain("bootstrap.min.css");
      expect(html, `${htmlFilePath} does not load the shared theme`).toContain("theme.css");
      if (htmlFilePath.replace(/\\/g, "/").endsWith("/web/index.html")) {
        expect(html, `${htmlFilePath} does not load its page styles`).toContain("./styles.css");
      }
      for (const match of html.matchAll(/(?:href|src)="([^"?#]+)["?#]?/g)) {
        const reference = match[1];
        if (/^(?:[a-z]+:|\/|#)/i.test(reference) || !/\.(?:css|m?js)$/i.test(reference)) continue;
        const assetPath = path.resolve(path.dirname(htmlFilePath), reference);
        expect(fs.existsSync(assetPath), `${htmlFilePath} references missing asset ${reference}`).toBe(true);
        expect(fs.statSync(assetPath).size, `${htmlFilePath} references empty asset ${reference}`).toBeGreaterThan(20);
      }
    });
  });

});
