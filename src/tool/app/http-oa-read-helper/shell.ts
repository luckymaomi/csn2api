document.addEventListener("DOMContentLoaded", () => {
  const commandBlock = document.querySelector<HTMLElement>("pre");
  commandBlock?.addEventListener("click", async () => {
    const command = commandBlock.innerText.trim();
    if (!command) return;
    commandBlock.title = "已复制";
    await navigator.clipboard.writeText(command).catch(() => undefined);
  });
});
