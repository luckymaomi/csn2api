const pageSize = 50;
const maxCellCharacters = 100;

export function formatResultCell(value) {
  const fullText = String(value ?? "");
  const characters = Array.from(fullText);
  const truncated = characters.length > maxCellCharacters;
  return {
    fullText,
    text: truncated ? `${characters.slice(0, maxCellCharacters).join("")}...` : fullText,
    truncated,
  };
}

function nearBottom(element) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 24;
}

export function createResultTable(showError) {
  const elements = {
    count: document.querySelector("#resultsCount"),
    viewport: document.querySelector("#resultsViewport"),
    empty: document.querySelector("#resultsEmpty"),
    table: document.querySelector("#resultsTable"),
    previous: document.querySelector("#previousPage"),
    next: document.querySelector("#nextPage"),
    pageText: document.querySelector("#pageText"),
  };
  let followResults = true;
  let lastVersion = -1;
  let page = 0;
  let requestId = 0;
  let currentMeta = {};
  let expectedScrollTop = null;

  function draw(payload) {
    const columns = payload.columns || [];
    const rows = payload.rows || [];
    const previousTop = elements.viewport.scrollTop;
    elements.empty.hidden = rows.length > 0;
    elements.table.hidden = rows.length === 0;
    elements.table.style.minWidth = `${Math.max(960, columns.length * 150)}px`;

    const headerRow = document.createElement("tr");
    for (const column of columns) {
      const cell = document.createElement("th");
      cell.textContent = column;
      headerRow.append(cell);
    }
    elements.table.querySelector("thead").replaceChildren(headerRow);
    elements.table.querySelector("tbody").replaceChildren(...rows.map((row) => {
      const tableRow = document.createElement("tr");
      for (const column of columns) {
        const cell = document.createElement("td");
        const value = row[column] ?? "";
        const display = formatResultCell(value);
        cell.textContent = display.text;
        if (display.truncated) cell.title = display.fullText;
        if (column === "抓取状态") cell.className = value === "成功" ? "is-success" : "is-failed";
        tableRow.append(cell);
      }
      return tableRow;
    }));
    if (followResults) {
      const lastRow = elements.table.querySelector("tbody tr:last-child");
      const headerHeight = elements.table.querySelector("thead")?.offsetHeight || 0;
      elements.viewport.scrollTop = Math.max(0, (lastRow?.offsetTop || 0) - headerHeight);
      expectedScrollTop = elements.viewport.scrollTop;
    } else {
      elements.viewport.scrollTop = previousTop;
    }
  }

  async function load() {
    const total = Number(currentMeta.total || 0);
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    if (followResults && total > 0) page = pageCount - 1;
    page = Math.max(0, Math.min(page, pageCount - 1));
    const currentRequest = ++requestId;
    const response = await fetch(`/api/results?offset=${page * pageSize}&limit=${pageSize}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`结果读取失败：HTTP ${response.status}`);
    const payload = await response.json();
    if (currentRequest !== requestId) return;
    draw(payload);
    const actualPages = Math.max(1, Math.ceil(Number(payload.total || 0) / pageSize));
    elements.count.textContent = `${payload.total || 0} 条`;
    elements.pageText.textContent = `第 ${page + 1} / ${actualPages} 页`;
    elements.previous.disabled = page <= 0;
    elements.next.disabled = page >= actualPages - 1;
  }

  elements.viewport.addEventListener("scroll", () => {
    if (expectedScrollTop !== null && Math.abs(elements.viewport.scrollTop - expectedScrollTop) < 1) {
      expectedScrollTop = null;
      return;
    }
    expectedScrollTop = null;
    followResults = nearBottom(elements.viewport);
  });
  elements.previous.addEventListener("click", () => {
    followResults = false;
    page -= 1;
    void load().catch(showError);
  });
  elements.next.addEventListener("click", () => {
    followResults = false;
    page += 1;
    void load().catch(showError);
  });

  return {
    followLatest() {
      followResults = true;
    },
    reset() {
      followResults = true;
      lastVersion = -1;
      page = 0;
    },
    async render(meta) {
      currentMeta = meta || {};
      const version = Number(currentMeta.version || 0);
      if (version === lastVersion) return;
      lastVersion = version;
      await load();
    },
  };
}
