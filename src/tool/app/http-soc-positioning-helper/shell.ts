document.addEventListener("DOMContentLoaded", () => {
  const link = document.querySelector<HTMLAnchorElement>('a[download]');
  link?.addEventListener("click", () => {
    const original = link.textContent || "下载录入模板";
    link.textContent = "已触发下载";
    window.setTimeout(() => { link.textContent = original; }, 1500);
  });
});
