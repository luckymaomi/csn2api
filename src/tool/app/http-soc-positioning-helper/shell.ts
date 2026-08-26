document.addEventListener("DOMContentLoaded", () => {
  const link = document.querySelector<HTMLAnchorElement>('a[download$=".zip"]');
  link?.addEventListener("click", () => {
    const original = link.textContent || "下载独立应用";
    link.textContent = "已触发下载";
    window.setTimeout(() => { link.textContent = original; }, 1500);
  });
});
