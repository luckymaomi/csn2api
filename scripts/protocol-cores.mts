import fs from "node:fs/promises";
import path from "node:path";


export type ProtocolCoreDefinition = {
  systemId: string;
  protocol: string;
  apiPackage: string;
  catalogModules: string[];
  targets: string[];
};

type ProtocolCoreContext = {
  projectRoot: string;
  staticRoot: string;
  registeredToolTargets: string[];
};

async function pathExists(target: string): Promise<boolean> {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

export async function readProtocolCoreDefinitions(
  context: ProtocolCoreContext
): Promise<ProtocolCoreDefinition[]> {
  const definitions = JSON.parse(await fs.readFile(
    path.join(context.projectRoot, "scripts", "protocol-cores.json"),
    "utf8"
  )) as ProtocolCoreDefinition[];
  const catalogRoot = path.join(context.staticRoot, "tool", "app", "api-docs", "catalog");
  const catalogIndex = JSON.parse(await fs.readFile(
    path.join(catalogRoot, "index.json"),
    "utf8"
  )) as { systems: Array<{ id: string }>; modules: Array<{ id: string }> };

  const declaredSystems = definitions.map((item) => item.systemId).sort();
  const catalogSystems = catalogIndex.systems.map((item) => item.id).sort();
  const declaredModules = definitions.flatMap((item) => item.catalogModules).sort();
  const catalogModules = catalogIndex.modules.map((item) => item.id).sort();
  const declaredTargets = definitions
    .flatMap((item) => item.targets)
    .filter((target) => target !== "api-docs")
    .sort();
  const registeredTargets = [...context.registeredToolTargets].sort();

  if (JSON.stringify(declaredSystems) !== JSON.stringify(catalogSystems)) {
    throw new Error("protocol core 声明未覆盖全部 API 系统。");
  }
  if (JSON.stringify(declaredModules) !== JSON.stringify(catalogModules)) {
    throw new Error("protocol core 声明未覆盖全部 catalog 模块。");
  }
  if (JSON.stringify(declaredTargets) !== JSON.stringify(registeredTargets)) {
    throw new Error("protocol core 声明未覆盖全部独立 HTTP APP。");
  }

  for (const item of definitions) {
    await fs.access(path.join(
      context.staticRoot, "tool", "app", "_shared", item.protocol, "__init__.py"
    ));
    const systemRoot = path.join(
      context.staticRoot, "tool", "app", "api-docs", "api_docs", "systems"
    );
    await fs.access(path.join(systemRoot, item.apiPackage, "__init__.py"));
    if (await pathExists(path.join(systemRoot, `${item.apiPackage}.py`))) {
      throw new Error(`API 系统 ${item.systemId} 仍保留散装兼容模块。`);
    }
    for (const moduleId of item.catalogModules) {
      const module = JSON.parse(await fs.readFile(
        path.join(catalogRoot, `${moduleId}.json`),
        "utf8"
      )) as { id?: string; systemId?: string };
      if (module.id !== moduleId || module.systemId !== item.systemId) {
        throw new Error(`catalog 模块 ${moduleId} 与 protocol core 声明不一致。`);
      }
    }
    for (const target of item.targets) {
      await fs.access(path.join(context.staticRoot, "tool", "app", target));
    }
  }
  return definitions;
}
