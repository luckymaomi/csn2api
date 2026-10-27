import fs from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { pathToFileURL } from "node:url";

export const DOCUMENTATION_FILENAME = "csn2api-development-documentation.md";
const execFileAsync = promisify(execFile);

type SourceDocument = {
    path: string;
    anchor: string;
    text: string;
    headings: Map<string, string>;
};

export type DocumentationOptions = {
    projectRoot: string;
    outputFile: string;
};

export type DocumentationResult = {
    files: string[];
};

// Git discovers new documents as well as tracked ones and excludes local credentials.
async function collectFiles(projectRoot: string): Promise<string[]> {
    const { stdout } = await execFileAsync("git", ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "spec"], {
        cwd: projectRoot, encoding: "utf8", maxBuffer: 4 * 1024 * 1024
    });
    const files = [...new Set(stdout.split("\0").filter((name) => path.extname(name).toLowerCase() === ".md"))].sort();
    const existing: string[] = [];
    for (const file of files) {
        try {
            const entry = await fs.lstat(path.join(projectRoot, file));
            if (entry.isSymbolicLink()) throw new Error(`Documentation symbolic link is not supported: ${file}`);
            if (entry.isFile()) existing.push(file);
        } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        }
    }
    return existing;
}

// Process prose only. Fenced examples must never be interpreted as headings or links.
function mapProse(source: string, transform: (line: string) => string): string {
    let fence = "";
    return source.replace(/\r\n/g, "\n").split("\n").map((line) => {
        const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
        if (fence) {
            if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = "";
            return line;
        }
        if (marker) {
            fence = marker[1];
            return line;
        }
        if (/^(?: {4}|\t)/.test(line)) return line;
        return transform(line);
    }).join("\n");
}

function headingSlug(text: string): string {
    return text.trim().toLowerCase().replace(/<[^>]*>/g, "")
        .replace(/[^\p{L}\p{N}\p{M}_\-\s]/gu, "").replace(/\s/g, "-");
}

function withHeadingAnchors(document: SourceDocument): string {
    const used = new Set<string>();
    return mapProse(document.text, (line) => {
        const heading = line.match(/^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$/);
        if (!heading) return line;
        const base = headingSlug(heading[1]);
        let slug = base;
        let suffix = 0;
        while (used.has(slug)) slug = `${base}-${++suffix}`;
        used.add(slug);
        const anchor = `${document.anchor}-h${used.size}`;
        document.headings.set(slug, anchor);
        return `<a id="${anchor}"></a>\n\n${line}`;
    });
}

function rewriteLinks(source: string, document: SourceDocument, documents: Map<string, SourceDocument>): string {
    return mapProse(source, (line) => line.split(/(`+[^`]*`+)/g).map((part, index) => {
        if (index % 2) return part;
        return part.replace(/(!?\[[^\]\n]*\])\((<[^>\n]+>|[^)\s]+)(\s+(?:"[^"]*"|'[^']*'))?\)/g,
            (_match: string, label: string, rawTarget: string, title = "") => {
                const target = rawTarget.replace(/^<|>$/g, "");
                if (/^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(target)) return `${label}(${rawTarget}${title})`;
                const [rawFile, ...fragmentParts] = target.split("#");
                const file = rawFile ? path.posix.normalize(path.posix.join(path.posix.dirname(document.path), decodeURIComponent(rawFile))) : document.path;
                const destination = documents.get(file);
                if (!destination) throw new Error(`Broken documentation link in ${document.path}: ${target}`);
                if (label.startsWith("!")) throw new Error(`Local documentation images require a text description: ${document.path}: ${target}`);
                const fragment = decodeURIComponent(fragmentParts.join("#"));
                const anchor = fragment ? destination.headings.get(fragment) : destination.anchor;
                if (!anchor) throw new Error(`Unknown documentation heading in ${document.path}: ${target}`);
                return `${label}(#${anchor}${title})`;
            });
    }).join(""));
}

export async function buildDocumentation(options: DocumentationOptions): Promise<DocumentationResult> {
    const projectRoot = path.resolve(options.projectRoot);
    const specRoot = path.join(projectRoot, "spec");
    const relativeOutput = path.relative(specRoot, path.resolve(options.outputFile));
    if (!relativeOutput.startsWith(`..${path.sep}`) && relativeOutput !== ".." && !path.isAbsolute(relativeOutput)) {
        throw new Error("Documentation output must be outside spec to avoid recursive inclusion.");
    }
    const paths = await collectFiles(projectRoot);
    const readmeIndex = paths.indexOf("spec/README.md");
    if (readmeIndex >= 0) paths.unshift(...paths.splice(readmeIndex, 1));
    if (!paths.length) throw new Error("No documentation files found.");

    const documents = new Map<string, SourceDocument>();
    for (const relativePath of paths) {
        const bytes = await fs.readFile(path.join(projectRoot, relativePath));
        if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) throw new Error(`Remove UTF-8 BOM from ${relativePath}`);
        let text: string;
        try {
            text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
        } catch {
            throw new Error(`Invalid UTF-8 in ${relativePath}`);
        }
        if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(text)) throw new Error(`Cannot merge binary documentation: ${relativePath}`);
        documents.set(relativePath, {
            path: relativePath, anchor: `doc-${documents.size + 1}`,
            text, headings: new Map()
        });
    }

    const catalogPath = "public/tool/app/api-docs/catalog/index.json";
    const apiRoot = path.join(projectRoot, "public/tool/app/api-docs");
    const index = JSON.parse(await fs.readFile(path.join(projectRoot, catalogPath), "utf8")) as {
        systems: unknown[]; modules: Array<{ id: string; source: string }>;
    };
    const modules = await Promise.all(index.modules.map(async (reference) => {
        const catalogRoot = path.join(apiRoot, "catalog");
        const file = path.resolve(catalogRoot, reference.source);
        const relative = path.relative(catalogRoot, file);
        if (relative.startsWith("..") || path.isAbsolute(relative) || path.extname(file) !== ".json") {
            throw new Error(`Invalid API catalog source: ${reference.source}`);
        }
        const module = JSON.parse(await fs.readFile(file, "utf8")) as { id: string };
        if (module.id !== reference.id) throw new Error(`API catalog module ID mismatch: ${reference.id}`);
        return module;
    }));
    const { buildApiDocsMarkdown } = await import(pathToFileURL(path.join(apiRoot, "markdown-export.mjs")).href) as {
        buildApiDocsMarkdown: (modules: unknown[], systems: unknown[]) => string;
    };
    documents.set(catalogPath, {
        path: catalogPath, anchor: "api-catalog", headings: new Map(),
        text: buildApiDocsMarkdown(modules, index.systems)
    });

    const markdown = new Map<string, string>();
    for (const document of documents.values()) {
        markdown.set(document.path, withHeadingAnchors(document));
    }
    const files = [...documents.values()].map(({ path: sourcePath, anchor }) => ({ path: sourcePath, anchor }));
    const sections = [
        "# csn2api 开发者文档",
        "本文件合并系统说明、APP 开发规格与用户手册，以及当前 catalog 生成的 API 文档，正文使用 UTF-8。",
        "## 目录\n\n" + files.map((file) => `- [${file.path}](#${file.anchor})`).join("\n")
    ];
    for (const document of documents.values()) {
        const content = rewriteLinks(markdown.get(document.path)!, document, documents);
        sections.push(`---\n\n<a id="${document.anchor}"></a>\n\n## Source: ${document.path}\n\n${content}`);
    }
    await fs.mkdir(path.dirname(options.outputFile), { recursive: true });
    await fs.writeFile(options.outputFile, `${sections.join("\n\n")}\n`, "utf8");
    return { files: files.map((file) => file.path) };
}
