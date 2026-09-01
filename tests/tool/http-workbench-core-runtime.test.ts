import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { resolveFromDist, resolveFromRoot } from "../helpers/paths";
import { assertJavaScriptSyntax } from "../helpers/syntax";


const appRoot = resolveFromRoot("public/tool/app");
const workbenches = readdirSync(appRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && /^http-.+-helper$/.test(entry.name))
  .map((entry) => entry.name)
  .filter((entry) => existsSync(path.join(appRoot, entry, "web", "index.html")))
  .sort();
const standardKeepAlivePath = path.join(appRoot, "_shared", "session_keepalive.mjs");

function findServer(root: string): string {
  const queue = [root];
  while (queue.length) {
    const current = queue.shift()!;
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const candidate = path.join(current, entry.name);
      if (entry.isDirectory() && !entry.name.startsWith(".") && entry.name !== "results" && entry.name !== "__pycache__") {
        queue.push(candidate);
      }
      if (entry.isFile() && entry.name === "server.py") return candidate;
    }
  }
  throw new Error(`${root} 缺少 server.py`);
}

describe("HTTP workbench core runtime", () => {
  it("dynamically discovers every Python HTTP workbench", () => {
    expect(workbenches.length).toBeGreaterThan(0);
  });

  it("publishes one standard keepalive module", () => {
    expect(existsSync(standardKeepAlivePath)).toBe(true);
    expect(statSync(standardKeepAlivePath).size).toBeGreaterThan(20);
  });

  it.each(workbenches)("enforces the shared UI and keepalive contract in %s", (entry) => {
    const root = resolveFromRoot(`public/tool/app/${entry}`);
    const html = readFileSync(`${root}/web/index.html`, "utf8");
    const landing = readFileSync(resolveFromDist(`tool/app/${entry}/index.html`), "utf8");
    const script = readFileSync(`${root}/web/app.mjs`, "utf8");
    const browserModules = readdirSync(`${root}/web`).filter((name) => name.endsWith(".mjs"));
    browserModules.forEach((name) => assertJavaScriptSyntax(`${root}/web/${name}`));
    const browserRuntime = browserModules
      .map((name) => readFileSync(`${root}/web/${name}`, "utf8"))
      .join("\n");
    const styles = readFileSync(`${root}/web/styles.css`, "utf8");
    const keepAlive = readFileSync(`${root}/web/session_keepalive.mjs`, "utf8");
    const server = readFileSync(findServer(root), "utf8");

    expect(html).toContain('<script src="./theme.js"></script>');
    expect(html).toContain('<link rel="stylesheet" href="./libs/bootstrap.min.css">');
    expect(html).toContain('<link rel="stylesheet" href="./theme.css">');
    expect(html).toContain('<link rel="stylesheet" href="./styles.css">');
    expect(html).toContain("当前登录人");
    expect(html).toContain('id="sessionIdentity"');
    expect(script).toMatch(/session(?:\?\.)?\.identity|session\.identity|session\?\.identity/);

    expect(script).not.toMatch(/^import\s+\{[^}]*renderKeepAlive/m);
    expect(script).toContain('void import("./session_keepalive.mjs")');
    expect(script).toContain("核心功能仍可使用");
    expect(html).toContain('id="savedCredentialsPanel"');
    expect(html).toContain('id="savedCredentials"');
    expect(html).toContain('id="copyCredentialsButton"');
    expect(script).toContain("navigator.clipboard.writeText");
    expect(script).not.toContain("localStorage");
    expect(script).not.toContain("sessionStorage");
    expect(server).toContain('"/session_keepalive.mjs"');
    expect(keepAlive).toBe(readFileSync(standardKeepAlivePath, "utf8"));

    expect(html).toContain("data-keepalive-widget");
    for (const id of ["keepAliveRing", "keepAliveCountdown", "keepAliveStatus", "keepAliveDetail"]) {
      expect(html).toContain(`id="${id}"`);
    }
    expect(html).toContain('id="logList"');
    if (existsSync(path.join(root, "template.xlsx"))) {
      expect(landing).toContain('href="./template.xlsx"');
      expect(landing).toContain("下载 Excel 模板");
      expect(existsSync(path.join(resolveFromDist(`tool/app/${entry}`), "template.xlsx"))).toBe(true);
    }
    if (html.includes('id="resultsTable"')) expect(html).toContain('id="resultsViewport"');

    const headings = [...html.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)]
      .map((match) => match[1].replace(/<[^>]+>/g, "").trim());
    const stepNumbers = headings
      .map((heading) => heading.match(/^(\d+)\./)?.[1])
      .filter(Boolean);
    expect(stepNumbers, `${entry} 的主流程缺少编号步骤`).toEqual(expect.arrayContaining(["1", "2", "3"]));
    const verifyButton = html.match(/<button[^>]*id="verifyButton"[^>]*>([\s\S]*?)<\/button>/)?.[1] || "";
    expect(verifyButton, `${entry} 的验证按钮混入了后续业务动作`).not.toContain("并");

    expect(browserRuntime).toContain('addEventListener("scroll"');
    expect(browserRuntime).toContain("scrollHeight");
    expect(browserRuntime).toContain("scrollTop");
    expect(browserRuntime).toContain("clientHeight");

    const bodyStart = styles.indexOf("body {");
    const bodyEnd = styles.indexOf("}", bodyStart);
    const keepAliveStyle = styles.indexOf(".keepalive-summary");
    expect(bodyStart).toBeGreaterThanOrEqual(0);
    expect(keepAliveStyle < bodyStart || keepAliveStyle > bodyEnd).toBe(true);

    const elementIds = [...browserRuntime.matchAll(/querySelector\("#([A-Za-z0-9_-]+)"\)/g)]
      .map((match) => match[1]);
    for (const elementId of elementIds) {
      expect(html, `${entry} 缺少 #${elementId}`).toContain(`id="${elementId}"`);
    }
  });
});
