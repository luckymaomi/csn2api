import fs from "node:fs/promises";
import path from "node:path";

import ts from "typescript";

import { readProtocolCoreDefinitions } from "./protocol-cores.mjs";
import { isRuntimeGeneratedPath } from "./tool-exports.mjs";

export type ToolCatalogItem = {
  name: string;
  description: string;
  entry: string;
};

type DeliveryRoots = {
  staticRoot: string;
  distRoot: string;
  tools: ToolCatalogItem[];
};

function readObjectStringProperty(node: ts.ObjectLiteralExpression, propertyName: string): string {
  for (const property of node.properties) {
    if (!ts.isPropertyAssignment(property)) continue;
    const name = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)
      ? property.name.text
      : "";
    if (name !== propertyName || !ts.isStringLiteralLike(property.initializer)) continue;
    return property.initializer.text;
  }
  return "";
}

export async function readToolCatalog(sourceRoot: string): Promise<ToolCatalogItem[]> {
  const sourcePath = path.join(sourceRoot, "tool", "tools-data.ts");
  const sourceText = await fs.readFile(sourcePath, "utf8");
  const sourceFile = ts.createSourceFile(sourcePath, sourceText, ts.ScriptTarget.Latest, true);
  let catalog: ToolCatalogItem[] = [];

  sourceFile.forEachChild((node) => {
    if (!ts.isVariableStatement(node)) return;
    for (const declaration of node.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || declaration.name.text !== "tools") continue;
      if (!declaration.initializer || !ts.isArrayLiteralExpression(declaration.initializer)) continue;
      catalog = declaration.initializer.elements.flatMap((element) => {
        if (!ts.isObjectLiteralExpression(element)) return [];
        const name = readObjectStringProperty(element, "name");
        const description = readObjectStringProperty(element, "desc");
        const entry = readObjectStringProperty(element, "entry");
        return name && entry ? [{ name, description, entry }] : [];
      });
    }
  });

  if (!catalog.length) throw new Error("无法从 src/tool/tools-data.ts 读取工具清单。");
  return catalog;
}

export async function copyPythonWorkbenchAssets(options: DeliveryRoots): Promise<Map<string, string>> {
  const standardKeepAlivePath = path.join(options.staticRoot, "tool", "app", "_shared", "session_keepalive.mjs");
  const sharedRuntimePath = path.join(options.staticRoot, "tool", "app", "_shared", "csn2api_runtime");
  const sharedCredentialTextPath = path.join(options.staticRoot, "tool", "app", "_shared", "credential_text");
  const sortedTools = [...options.tools].sort((left, right) => left.entry.localeCompare(right.entry, "en"));
  for (const tool of sortedTools) {
    const toolRoot = path.join(options.distRoot, "tool", "app", tool.entry);
    const workbenchRoot = path.join(toolRoot, "web");
    const libraryRoot = path.join(workbenchRoot, "libs");
    await fs.mkdir(libraryRoot, { recursive: true });
    await fs.copyFile(path.join(options.staticRoot, "theme.js"), path.join(workbenchRoot, "theme.js"));
    await fs.copyFile(path.join(options.staticRoot, "theme.css"), path.join(workbenchRoot, "theme.css"));
    await fs.copyFile(standardKeepAlivePath, path.join(workbenchRoot, "session_keepalive.mjs"));
    await fs.copyFile(
      path.join(options.staticRoot, "libs", "bootstrap.min.css"),
      path.join(libraryRoot, "bootstrap.min.css")
    );
    await fs.cp(sharedRuntimePath, path.join(toolRoot, "csn2api_runtime"), {
      recursive: true,
      force: true,
      filter: (sourcePath) => !isRuntimeGeneratedPath(path.relative(sharedRuntimePath, sourcePath))
    });
    await fs.cp(sharedCredentialTextPath, path.join(toolRoot, "credential_text"), {
      recursive: true,
      force: true,
      filter: (sourcePath) => !isRuntimeGeneratedPath(path.relative(sharedCredentialTextPath, sourcePath))
    });
  }

  const registeredToolTargets = options.tools
    .map((tool) => tool.entry)
    .filter((entry) => entry.startsWith("http-") && entry.endsWith("-helper"));
  const sharedProtocolCopies = await readProtocolCoreDefinitions({
    projectRoot: path.dirname(options.staticRoot),
    staticRoot: options.staticRoot,
    registeredToolTargets
  });
  for (const item of sharedProtocolCopies) {
    const source = path.join(options.staticRoot, "tool", "app", "_shared", item.protocol);
    for (const target of item.targets) {
      await fs.cp(source, path.join(options.distRoot, "tool", "app", target, item.protocol), {
        recursive: true,
        force: true,
        filter: (sourcePath) => !isRuntimeGeneratedPath(path.relative(source, sourcePath))
      });
    }
  }
  return new Map(sharedProtocolCopies.flatMap((item) =>
    item.targets
      .filter((target) => target !== "api-docs")
      .map((target) => [target, item.systemId] as const)
  ));
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function staticToolLanding(tool: ToolCatalogItem, hasTemplate: boolean): string {
  const name = escapeHtml(tool.name);
  const description = escapeHtml(tool.description);
  const entry = escapeHtml(tool.entry);
  const templateLink = hasTemplate
    ? `<a class="text-decoration-none" href="./template.xlsx" download="${entry}-模板.xlsx">下载 Excel 模板</a>`
    : "";
  const templateSection = hasTemplate
    ? `<section class="card mb-4"><div class="card-body">
            <h2 class="h5">输入模板</h2>
            <p>下载 Excel 模板，按表头填写后上传到工作台。</p>
            <a class="btn btn-outline-primary" href="./template.xlsx" download="${entry}-模板.xlsx">下载 Excel 模板</a>
        </div></section>`
    : "";
  return `<!DOCTYPE html>
<html lang="zh-CN" data-default-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${name}</title>
    <script src="../../../theme.js"></script>
    <link rel="stylesheet" href="../../../libs/bootstrap.min.css">
    <link rel="stylesheet" href="../../../theme.css">
</head>
<body style="background: transparent; padding: 20px;">
    <main class="container">
        <section class="card mb-4"><div class="card-body">
            <div class="d-flex justify-content-between align-items-center gap-3 flex-wrap">
                <a href="../../../index.html" class="text-decoration-none">返回首页</a>
                ${templateLink}
            </div>
            <h1 class="h4 mt-3">${name}</h1>
            <p class="text-muted mb-0">${description}</p>
        </div></section>
        ${templateSection}
        <section class="card"><div class="card-body">
            <h2 class="h5">独立应用</h2>
            <p>下载并解压后，安装依赖并运行 <code>python start.py</code>。</p>
            <a class="btn btn-primary" href="../../../exports/${entry}.zip" download="${entry}.zip">下载独立应用</a>
        </div></section>
    </main>
    <script type="module" src="./app.js"></script>
</body>
</html>
`;
}

async function pathExists(target: string): Promise<boolean> {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function findWorkbenchPackage(staticRoot: string, entry: string): Promise<string> {
  const root = path.join(staticRoot, "tool", "app", entry);
  const candidates = (await fs.readdir(root, { withFileTypes: true }))
    .filter((item) => item.isDirectory())
    .map((item) => item.name);
  const packages: string[] = [];
  for (const name of candidates) {
    if (await pathExists(path.join(root, name, "server.py"))) packages.push(name);
  }
  if (packages.length !== 1) throw new Error(`工具 ${entry} 必须包含一个 Python server 包。`);
  return packages[0];
}

export async function generateRuntimeDelivery(
  options: DeliveryRoots & { standaloneRoot: string; toolSystems: Map<string, string> }
): Promise<void> {
  const runtimeTools = [];
  for (const tool of options.tools) {
    const outputRoot = path.join(options.distRoot, "tool", "app", tool.entry);
    await fs.mkdir(outputRoot, { recursive: true });
    const hasTemplate = await pathExists(path.join(outputRoot, "template.xlsx"));
    await fs.writeFile(path.join(outputRoot, "index.html"), staticToolLanding(tool, hasTemplate), "utf8");
    await fs.copyFile(
      path.join(options.standaloneRoot, tool.entry, "app.js"),
      path.join(outputRoot, "app.js")
    );
    const systemId = options.toolSystems.get(tool.entry);
    if (!systemId) throw new Error(`工具 ${tool.entry} 缺少 protocol core 系统归属。`);
    runtimeTools.push({
      ...tool,
      package: await findWorkbenchPackage(options.staticRoot, tool.entry),
      systemId
    });
  }
  await fs.writeFile(
    path.join(options.distRoot, "runtime-tools.json"),
    `${JSON.stringify({ schemaVersion: 1, tools: runtimeTools }, null, 2)}\n`,
    "utf8"
  );
}
