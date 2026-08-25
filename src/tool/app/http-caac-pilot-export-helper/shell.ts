document.addEventListener("DOMContentLoaded", () => {
  const downloadLink = document.querySelector<HTMLAnchorElement>('a[download$=".zip"]');
  const commandBlock = document.querySelector<HTMLElement>("pre");
  downloadLink?.addEventListener("click", () => {
    const original = downloadLink.textContent || "下载独立应用";
    downloadLink.textContent = "已触发下载";
    window.setTimeout(() => { downloadLink.textContent = original; }, 1500);
  });
  commandBlock?.addEventListener("click", async () => {
    const command = commandBlock.innerText.trim();
    if (command) await navigator.clipboard.writeText(command).catch(() => undefined);
  });
});
