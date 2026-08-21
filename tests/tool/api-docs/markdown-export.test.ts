import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

import { resolveFromPublic } from "../../helpers/paths";

const appRoot = resolveFromPublic("tool", "app", "api-docs");

async function loadExporter(): Promise<{
  buildApiDocsMarkdown: (modules: unknown[], systems?: unknown[]) => string;
}> {
  return await import(pathToFileURL(`${appRoot}/markdown-export.mjs`).href) as {
    buildApiDocsMarkdown: (modules: unknown[], systems?: unknown[]) => string;
  };
}

function loadCatalog(): { systems: unknown[]; modules: unknown[] } {
  const index = JSON.parse(readFileSync(`${appRoot}/catalog/index.json`, "utf8"));
  return {
    systems: index.systems,
    modules: index.modules.map((item: { source: string }) => (
      JSON.parse(readFileSync(`${appRoot}/catalog/${item.source.replace(/^\.\//, "")}`, "utf8"))
    ))
  };
}

describe("API docs Markdown export", () => {
  it("exports one human-readable document with complete machine facts", async () => {
    const { buildApiDocsMarkdown } = await loadExporter();
    const catalog = loadCatalog();
    const markdown = buildApiDocsMarkdown(catalog.modules, catalog.systems);

    expect(markdown).toContain("# csn2api API 文档");
    expect(markdown).toContain("documentType: csn2api-api-catalog");
    expect(markdown).toContain("## 认证与会话");
    expect(markdown).toContain("`JSESSIONID`");
    expect(markdown).toContain("https://ieb.csair.com/newieb/flytime/showFlytimeManyQueryList");
    expect(markdown).toContain("https://ieb.csair.com/newieb/nonproductionTask/showNonproductionTaskImportResultPage");
    expect(markdown).toContain("https://ieb.csair.com/newieb/hrInfo/showEmpInfo");
    expect(markdown).toContain("https://ieb.csair.com/newieb/basics/trainingRecordList");
    expect(markdown).toContain("https://work.csair.com/oaw/work/my-dealt-with/schedule-list?sourceType=wait");
    expect(markdown).toContain("https://work.csair.com/oai/work/box/query/waiting");
    expect(markdown).toContain("https://work.csair.com/oai/doc/pc/form/sw/haveRead");
    expect(markdown).toContain("Copy as cURL");
    expect(markdown).toContain("本地组合工作流");
    expect(markdown).toContain("获取全部 OA 数量");
    expect(markdown).toContain("每条完成后立即追加结果");
    expect(markdown).toContain("`staffNum`");
    expect(markdown).toContain("`lockDaysNum`");
    expect(markdown).toContain("`/newieb/nonproductionTask/vaildStaffNum`");
    expect(markdown).toContain("`/newieb/nonproductionTask/importNonproductionTaskLockListToSoc`");
    expect(markdown).toContain("## 附录：机器可读原始目录");
    expect(markdown).toContain('"schemaVersion": 1');
    expect(markdown).toContain('"internalRequests"');
  });
});
