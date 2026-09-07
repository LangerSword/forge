(() => {
  try {
    const stored = localStorage.getItem("forge-theme");
    const preferred = stored === "dark" || stored === "light"
      ? stored
      : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = preferred;
    document.documentElement.style.colorScheme = preferred;
  } catch {
    document.documentElement.dataset.theme = "light";
  }
})();
