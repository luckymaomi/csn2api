document.querySelector("pre")?.addEventListener("click", async (event) => {
  const command = (event.currentTarget as HTMLElement).innerText.trim();
  if (command) await navigator.clipboard.writeText(command).catch(() => undefined);
});
