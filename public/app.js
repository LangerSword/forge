(() => {
  "use strict";

  const menuButton = document.querySelector(".menu-toggle");
  const mobileMenu = document.querySelector("#mobile-menu");

  if (menuButton && mobileMenu) {
    menuButton.addEventListener("click", () => {
      const isOpen = menuButton.getAttribute("aria-expanded") === "true";
      menuButton.setAttribute("aria-expanded", String(!isOpen));
      mobileMenu.hidden = isOpen;
    });

    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        menuButton.setAttribute("aria-expanded", "false");
        mobileMenu.hidden = true;
      });
    });
  }

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
