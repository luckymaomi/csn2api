import { existsSync, readFileSync } from "node:fs";
import JSZip from "jszip";
import { describe, expect, it } from "vitest";
import { tools } from "../../src/tool/tools-data";
import { resolveFromDist, resolveFromRoot } from "../helpers/paths";

type ProtocolCoreDefinition = {
  systemId: string;
  protocol: string;
  apiPackage: string;
  catalogModules: string[];
  targets: string[];
};

const definitions = JSON.parse(
  readFileSync(resolveFromRoot("scripts", "protocol-cores.json"), "utf8")
) as ProtocolCoreDefinition[];

describe("protocol core delivery contract", () => {
  it("keeps one system package and one declared core per production system", () => {
    expect(definitions.map((item) => item.systemId).sort()).toEqual([
      "caac-fsop", "flight-portal", "oa", "soc"
    ]);
    for (const item of definitions) {
      expect(existsSync(resolveFromRoot(
        "public", "tool", "app", "_shared", item.protocol, "__init__.py"
      ))).toBe(true);
      expect(existsSync(resolveFromRoot(
        "public", "tool", "app", "api-docs", "api_docs", "systems", item.apiPackage, "__init__.py"
      ))).toBe(true);
      expect(existsSync(resolveFromRoot(
        "public", "tool", "app", "api-docs", "api_docs", "systems", `${item.apiPackage}.py`
      ))).toBe(false);
    }
  });

  it("keeps catalog ownership aligned with the central declaration", () => {
    const index = JSON.parse(readFileSync(resolveFromRoot(
      "public", "tool", "app", "api-docs", "catalog", "index.json"
    ), "utf8")) as {
      systems: Array<{ id: string }>;
      modules: Array<{ id: string }>;
    };
    expect(definitions.map((item) => item.systemId).sort()).toEqual(
      index.systems.map((item) => item.id).sort()
    );
    expect(definitions.flatMap((item) => item.catalogModules).sort()).toEqual(
      index.modules.map((item) => item.id).sort()
    );
    for (const item of definitions) {
      for (const moduleId of item.catalogModules) {
        const catalog = JSON.parse(readFileSync(resolveFromRoot(
          "public", "tool", "app", "api-docs", "catalog", `${moduleId}.json`
        ), "utf8")) as { id: string; systemId: string };
        expect(catalog.id).toBe(moduleId);
        expect(catalog.systemId).toBe(item.systemId);
      }
    }
  });

  it("vendors every declared core into each built standalone target and ZIP", async () => {
    const declaredApps = definitions
      .flatMap((item) => item.targets)
      .filter((target) => target !== "api-docs")
      .sort();
    const registeredApps = tools
      .map((tool) => tool.entry)
      .filter((entry) => entry.startsWith("http-") && entry.endsWith("-helper"))
      .sort();
    expect(declaredApps).toEqual(registeredApps);
    for (const item of definitions) {
      for (const target of item.targets) {
        expect(existsSync(resolveFromRoot("public", "tool", "app", target))).toBe(true);
        expect(existsSync(resolveFromDist(
          "tool", "app", target, item.protocol, "__init__.py"
        ))).toBe(true);
        if (target === "api-docs") continue;
        const zip = await JSZip.loadAsync(readFileSync(resolveFromDist(
          "exports", `${target}.zip`
        )));
        expect(zip.file(`${item.protocol}/__init__.py`)).not.toBeNull();
      }
    }
  });
});
