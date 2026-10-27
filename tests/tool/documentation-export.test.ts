import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildDocumentation, DOCUMENTATION_FILENAME } from "../../scripts/documentation-export.mjs";
import { bindDocumentationDownloads, documentationDownloadName } from "../../src/tool/documentation-download";
import { tools } from "../../src/tool/tools-data";
import { resolveFromDist, resolveFromRoot } from "../helpers/paths";

const run = promisify(execFile);
const roots: string[] = [];

async function write(root: string, name: string, content: string | Uint8Array): Promise<void> {
    const file = path.join(root, name);
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, content);
}

async function fixture(): Promise<{ projectRoot: string; outputFile: string }> {
    const projectRoot = await fs.mkdtemp(path.join(os.tmpdir(), "csn2api-docs-test-"));
    roots.push(projectRoot);
    await run("git", ["init", "--quiet"], { cwd: projectRoot });
    await write(projectRoot, ".gitignore", "spec/**/*.local.md\n");
    await write(projectRoot, "spec/README.md", "# 目录\n\n[操作](user/example/manual.md#操作)\n");
    await write(projectRoot, "spec/user/example/manual.md", "# 用户手册\n\n## 操作\n中文员工号 001234。\n");
    const apiRoot = "public/tool/app/api-docs";
    await fs.mkdir(path.join(projectRoot, apiRoot), { recursive: true });
    for (const name of ["catalog", "markdown-export.mjs", "catalog-normalize.mjs"]) {
        await fs.cp(resolveFromRoot(apiRoot, name), path.join(projectRoot, apiRoot, name), { recursive: true });
    }
    return { projectRoot, outputFile: path.join(projectRoot, "downloads", DOCUMENTATION_FILENAME) };
}

afterEach(async () => {
    vi.useRealTimers();
    await Promise.all(roots.splice(0).map((root) => fs.rm(root, { recursive: true, force: true })));
});

describe("combined APP and API documentation", () => {
    it("scans current prose and catalog, excludes ignored credentials and measurements, and stays deterministic", async () => {
        const options = await fixture();
        await write(options.projectRoot, "spec/dev/secret/cookies.local.md", "PRIVATE_CREDENTIAL_SENTINEL");
        await write(options.projectRoot, "spec/dev/baseline.json", '{"coreArtifactSha256":"measurement"}');
        const first = await buildDocumentation(options);
        const original = await fs.readFile(options.outputFile);
        const merged = original.toString("utf8");
        expect(merged).toContain("中文员工号 001234。");
        expect(merged).toContain("# csn2api API 文档");
        expect(merged).toContain("https://ieb.csair.com/newieb/basics/flytimeList");
        expect(merged).not.toMatch(/PRIVATE_CREDENTIAL_SENTINEL|coreArtifactSha256|SHA-256|Source commit:/);
        expect(first.files).toContain("spec/user/example/manual.md");
        expect(original.subarray(0, 3)).not.toEqual(Buffer.from([239, 187, 191]));
        await buildDocumentation(options);
        expect(await fs.readFile(options.outputFile)).toEqual(original);

        await write(options.projectRoot, "spec/dev/新增.md", "# 新规格\n自动收录。\n");
        await fs.rm(path.join(options.projectRoot, "spec/user/example/manual.md"));
        await write(options.projectRoot, "spec/README.md", "# 目录\n");
        const next = await buildDocumentation(options);
        expect(next.files).toContain("spec/dev/新增.md");
        expect(next.files).not.toContain("spec/user/example/manual.md");
        expect(await fs.readFile(options.outputFile, "utf8")).toContain("自动收录。");
    });

    it("resolves duplicate headings and local links while preserving code examples", async () => {
        const options = await fixture();
        await write(options.projectRoot, "spec/user/example/manual.md", [
            "# 用户手册", "## 操作", "[self](#操作)", "## 操作", "[second](#操作-1)",
            "```md", "[literal](missing.md)", "## Example", "```", ""
        ].join("\n"));
        await buildDocumentation(options);
        const text = await fs.readFile(options.outputFile, "utf8");
        const links = [...text.matchAll(/\[(?:操作|self|second)\]\(#([^)]*)\)/g)].map((match) => match[1]);
        expect(links).toHaveLength(3);
        expect(links[0]).toBe(links[1]);
        expect(links[2]).not.toBe(links[1]);
        expect(text).toContain("```md\n[literal](missing.md)\n## Example\n```");
    });

    it("rejects broken links and invalid document encodings", async () => {
        const options = await fixture();
        await write(options.projectRoot, "spec/README.md", "[bad](missing.md)");
        await expect(buildDocumentation(options)).rejects.toThrow(/missing.md/);
        await write(options.projectRoot, "spec/README.md", Buffer.from([239, 187, 191, 97]));
        await expect(buildDocumentation(options)).rejects.toThrow(/BOM/);
        await write(options.projectRoot, "spec/README.md", Buffer.from([255, 254]));
        await expect(buildDocumentation(options)).rejects.toThrow(/UTF-8/);
    });

    it("includes newly indexed API modules without a separate export list", async () => {
        const options = await fixture();
        const catalog = path.join(options.projectRoot, "public/tool/app/api-docs/catalog");
        const index = JSON.parse(await fs.readFile(path.join(catalog, "index.json"), "utf8"));
        const module = JSON.parse(await fs.readFile(path.join(catalog, "flight-stats.json"), "utf8"));
        module.id = "new-module";
        module.name = "新增接口文档标记";
        index.modules.push({ id: module.id, source: "./new-module.json" });
        await write(catalog, "new-module.json", JSON.stringify(module));
        await write(catalog, "index.json", JSON.stringify(index));
        await buildDocumentation(options);
        expect(await fs.readFile(options.outputFile, "utf8")).toContain("新增接口文档标记");
    });
});

describe("published documentation download", () => {
    it("uses the local download day even when a page stays open across New Year", () => {
        expect(documentationDownloadName(new Date(2028, 1, 29))).toBe("csn2api开发者文档-2028-02-29.md");
        vi.useFakeTimers();
        vi.setSystemTime(new Date(2026, 11, 31, 23, 59));
        const link = Object.assign(new EventTarget(), { download: "" });
        bindDocumentationDownloads({ querySelectorAll: () => [link] } as unknown as ParentNode);
        expect(link.download).toBe("csn2api开发者文档-2026-12-31.md");
        vi.setSystemTime(new Date(2027, 0, 1, 0, 1));
        link.dispatchEvent(new Event("click"));
        expect(link.download).toBe("csn2api开发者文档-2027-01-01.md");
    });

    it("covers every current APP, spec and API endpoint with working document anchors", async () => {
        const merged = await fs.readFile(resolveFromDist("downloads", DOCUMENTATION_FILENAME), "utf8");
        for (const tool of tools) {
            expect(merged).toContain(`## Source: spec/dev/${tool.entry}/spec.md`);
            expect(merged).toContain(`## Source: spec/user/${tool.entry}/manual.md`);
        }
        const sources = (await run("git", ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "spec"], { cwd: resolveFromRoot() })).stdout.split("\0");
        for (const source of sources.filter((file) => file.endsWith(".md"))) expect(merged).toContain(`## Source: ${source}`);
        const catalog = resolveFromRoot("public/tool/app/api-docs/catalog");
        const index = JSON.parse(await fs.readFile(path.join(catalog, "index.json"), "utf8"));
        for (const reference of index.modules) {
            const module = JSON.parse(await fs.readFile(path.join(catalog, reference.source), "utf8"));
            for (const endpoint of module.endpoints) expect(merged).toContain(`\`${module.id}.${endpoint.id}\``);
        }
        const anchors = new Set([...merged.matchAll(/<a id="([^"]+)"><\/a>/g)].map((match) => match[1]));
        for (const link of merged.matchAll(/\]\(#([^)\s]+)\)/g)) expect(anchors.has(link[1]), link[1]).toBe(true);
        expect(merged).not.toMatch(/\b[a-f0-9]{64}\b|SHA-256|Source commit:/);
        expect(await fs.readFile(resolveFromDist("tool/index.html"), "utf8")).toContain(`href="../downloads/${DOCUMENTATION_FILENAME}" download="csn2api开发者文档.md" data-documentation-download`);
    });
});
