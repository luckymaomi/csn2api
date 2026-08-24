import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { resolveFromRoot } from "../helpers/paths";


const workbenches = [
  ["http-flight-stats-helper", "http_flight_stats"],
  ["http-lock-entry-helper", "http_lock_entry"],
  ["http-oa-read-helper", "http_oa_read"],
  ["http-qualification-query-helper", "http_qualification_query"],
  ["http-qualification-monitor-helper", "http_qualification_monitor"],
] as const;


describe("HTTP workbench core runtime", () => {
  it.each(workbenches)("keeps %s controls independent from the keepalive widget", (entry, packageName) => {
    const root = resolveFromRoot(`public/tool/app/${entry}`);
    const html = readFileSync(`${root}/web/index.html`, "utf8");
    const script = readFileSync(`${root}/web/app.mjs`, "utf8");
    const styles = readFileSync(`${root}/web/styles.css`, "utf8");
    const server = readFileSync(`${root}/${packageName}/server.py`, "utf8");

    expect(script).not.toMatch(/^import\s+\{[^}]*renderKeepAlive/m);
    expect(script).toContain('void import("./session_keepalive.mjs")');
    expect(script).toContain("核心功能仍可使用");
    expect(html).toContain('id="savedCredentialsPanel"');
    expect(html).toContain('id="savedCredentials"');
    expect(html).toContain('id="copyCredentialsButton"');
    expect(script).toContain("state.credentials");
    expect(script).toContain("navigator.clipboard.writeText(savedCredentials)");
    expect(script).not.toContain("localStorage");
    expect(script).not.toContain("sessionStorage");
    expect(server).toContain('"/session_keepalive.mjs": web_root / "session_keepalive.mjs"');

    const credentialStart = html.indexOf('class="work-panel credential-panel"');
    const credentialEnd = html.indexOf("</section>", credentialStart);
    const keepAliveWidget = html.indexOf("data-keepalive-widget", credentialStart);
    expect(credentialStart).toBeGreaterThanOrEqual(0);
    expect(keepAliveWidget).toBeGreaterThan(credentialStart);
    expect(keepAliveWidget).toBeLessThan(credentialEnd);

    const bodyStart = styles.indexOf("body {");
    const bodyEnd = styles.indexOf("}", bodyStart);
    const keepAliveStyle = styles.indexOf(".keepalive-summary");
    expect(bodyStart).toBeGreaterThanOrEqual(0);
    expect(keepAliveStyle < bodyStart || keepAliveStyle > bodyEnd).toBe(true);

    const elementIds = [...script.matchAll(/querySelector\("#([A-Za-z0-9_-]+)"\)/g)]
      .map((match) => match[1]);
    for (const elementId of elementIds) {
      expect(html, `${entry} 缺少 #${elementId}`).toContain(`id="${elementId}"`);
    }
  });
});
