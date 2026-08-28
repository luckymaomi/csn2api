import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { loadToolsData } from "../helpers/browser-context";
import { resolveFromDist, resolveFromRoot } from "../helpers/paths";

type RuntimeManifest = {
  schemaVersion: number;
  tools: Array<{ entry: string; name: string; package: string; systemId: string }>;
};

const tools = loadToolsData() || [];

describe("LAN runtime delivery contract", () => {
  it("generates one runtime manifest from the registered tool list", () => {
    const manifest = JSON.parse(
      fs.readFileSync(resolveFromDist("runtime-tools.json"), "utf8")
    ) as RuntimeManifest;

    expect(manifest.schemaVersion).toBe(1);
    expect(manifest.tools.map((tool) => tool.entry)).toEqual(tools.map((tool) => tool.entry));
    manifest.tools.forEach((tool) => {
      expect(tool.name).toBeTruthy();
      expect(tool.package).toMatch(/^[a-z0-9_]+$/);
      expect(tool.systemId).toMatch(/^[a-z0-9-]+$/);
    });
  });

  it.each(tools)("generates the static $entry landing without a dedicated shell", (tool) => {
    const sourceDirectory = resolveFromRoot("src", "tool", "app", tool.entry);
    const sourceLanding = resolveFromRoot("public", "tool", "app", tool.entry, "index.html");
    const builtLanding = resolveFromDist("tool", "app", tool.entry, "index.html");

    expect(fs.existsSync(path.join(sourceDirectory, "shell.ts"))).toBe(false);
    expect(fs.existsSync(sourceLanding)).toBe(false);
    expect(fs.readFileSync(builtLanding, "utf8")).toContain(`download="${tool.entry}.zip"`);
  });

  it("uses relative API URLs so every runtime can be mounted below a prefix", () => {
    const appRoot = resolveFromRoot("public", "tool", "app");
    const scripts = fs.readdirSync(appRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .flatMap((entry) => {
        const webRoot = path.join(appRoot, entry.name, "web");
        const roots = [path.join(appRoot, entry.name), webRoot];
        return roots.flatMap((root) => fs.existsSync(root)
          ? fs.readdirSync(root)
            .filter((name) => name === "app.mjs" || name === "results_table.mjs")
            .map((name) => path.join(root, name))
          : []);
      });

    scripts.forEach((script) => {
      const source = fs.readFileSync(script, "utf8");
      expect(source, script).not.toMatch(/["'`]\/api(?:\/|["'`])/);
    });
  });

  it("keeps every independent workbench on one shared launcher contract", () => {
    const starts = tools.map((tool) => fs.readFileSync(
      resolveFromRoot("public", "tool", "app", tool.entry, "start.py"),
      "utf8"
    ));
    expect(new Set(starts).size).toBe(1);
    expect(starts[0]).toContain("csn2api_runtime.single_app");
  });
});
