const pageSize = 50;

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
        cell.textContent = String(value);
        if (column === "抓取状态") cell.className = value === "成功" ? "is-success" : "is-failed";
        tableRow.append(cell);
      }
      return tableRow;
    }));
    elements.viewport.scrollTop = followResults ? elements.viewport.scrollHeight : previousTop;
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

  elements.viewport.addEventListener("scroll", () => { followResults = nearBottom(elements.viewport); });
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
