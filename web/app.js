(() => {
  "use strict";

  const inkPalettes = {
    light: {
      ink: "#1f2922",
      paper: "#fffdf7",
      green: "#176b45",
      pencil: "#8f9589",
      amber: "#a36f17",
      red: "#b64038",
      blue: "#396c9e",
    },
    dark: {
      ink: "#edf0e6",
      paper: "#282c25",
      green: "#8dd3a5",
      pencil: "#788174",
      amber: "#d4a33f",
      red: "#e4867d",
      blue: "#8db4da",
    },
  };

  const refreshDrawablyTheme = () => {
    const palette = inkPalettes[document.documentElement.dataset.theme === "dark" ? "dark" : "light"];
    document.querySelectorAll(".drawably-host").forEach((element) => {
      const tone = element.dataset.forgeInk || "ink";
      const color = palette[tone] || palette.ink;
      element.style.setProperty("--drawably-stroke", color);
      element.style.setProperty("--drawably-ink", color);
      element.style.setProperty("--drawably-fill", tone === "green" ? (document.documentElement.dataset.theme === "dark" ? "#314c38" : "#dcebdc") : palette.paper);
      element.style.setProperty("--drawably-paper", palette.paper);
    });
  };
  window.forgeRefreshInk = refreshDrawablyTheme;

  const themeControls = [...document.querySelectorAll("[data-theme-toggle]")];
  const setTheme = (theme, persist = true) => {
    const next = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    document.documentElement.style.colorScheme = next;
    const themeMeta = document.querySelector('meta[name="theme-color"]');
    if (themeMeta) themeMeta.setAttribute("content", next === "dark" ? "#1d211d" : "#f7f2e8");
    themeControls.forEach((control) => {
      control.checked = next === "dark";
      control.setAttribute("aria-checked", String(control.checked));
      control.setAttribute("aria-label", control.checked ? "Switch to light theme" : "Switch to dark theme");
    });
    if (persist) {
      try { localStorage.setItem("forge-theme", next); } catch { /* storage may be unavailable */ }
    }
    refreshDrawablyTheme();
  };
  themeControls.forEach((control) => control.addEventListener("change", () => setTheme(control.checked ? "dark" : "light")));
  setTheme(document.documentElement.dataset.theme || "light", false);

  const menuButton = document.querySelector(".menu-toggle");
  const mobileMenu = document.querySelector("#mobile-menu");

  if (menuButton && mobileMenu) {
    const setMenu = (open) => {
      menuButton.setAttribute("aria-expanded", String(open));
      menuButton.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
      mobileMenu.hidden = !open;
    };
    menuButton.addEventListener("click", () => {
      const isOpen = menuButton.getAttribute("aria-expanded") === "true";
      setMenu(!isOpen);
    });

    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        setMenu(false);
      });
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
        setMenu(false);
        menuButton.focus();
      }
    });
  }

  const demoTabs = [...document.querySelectorAll("[data-demo-state]")];
  const selectDemoTab = (button) => {
      const demo = document.querySelector("[data-static-demo]");
      if (!demo) return;
      const state = button.dataset.demoState || "baseline";
      const copy = {
        baseline: { label: "baseline / failed", title: "Frozen verifier found the break.", result: "EXIT 1", detail: "4 frozen checks failed", live: "baseline evidence" },
        repair: { label: "repair / bounded", title: "One repair, inside the budget.", result: "1 ATTEMPT", detail: "c0_target.py changed", live: "bounded recovery" },
        verdict: { label: "verdict / observed", title: "The artifact earned a result.", result: "EXIT 0", detail: "4 frozen checks passed", live: "verifier-backed result" },
      }[state] || null;
      if (!copy) return;
      demo.dataset.state = state;
      demo.setAttribute("aria-labelledby", button.id);
      button.parentElement?.querySelectorAll("[data-demo-state]").forEach((tab) => {
        const active = tab === button;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
      });
      const setText = (selector, value) => {
        const node = demo.querySelector(selector);
        if (node) node.textContent = value;
      };
      setText("[data-demo-label]", copy.label);
      setText("[data-demo-title]", copy.title);
      setText("[data-demo-result]", copy.result);
      setText("[data-demo-detail]", copy.detail);
      setText("[data-demo-live]", copy.live);
  };

  demoTabs.forEach((button, index) => {
    button.tabIndex = button.classList.contains("is-active") ? 0 : -1;
    button.addEventListener("click", () => {
      selectDemoTab(button);
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? demoTabs.length - 1 : (index + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + demoTabs.length) % demoTabs.length;
      demoTabs[next].focus();
      selectDemoTab(demoTabs[next]);
    });
  });

  document.querySelectorAll("[data-copy]").forEach((button) => {
    const original = button.textContent;
    button.addEventListener("click", async () => {
      const value = button.dataset.copy || "";
      try {
        await navigator.clipboard.writeText(value);
        button.textContent = "Copied";
        button.setAttribute("aria-label", "Copied to clipboard");
      } catch {
        button.textContent = "Select manually";
        button.setAttribute("aria-label", "Clipboard unavailable; select the code manually");
      }
      window.setTimeout(() => {
        button.textContent = original;
        button.removeAttribute("aria-label");
      }, 1600);
    });
  });

  const header = document.querySelector(".site-header");
  if (header) {
    const updateHeader = () => header.classList.toggle("is-scrolled", window.scrollY > 10);
    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });
  }
})();
