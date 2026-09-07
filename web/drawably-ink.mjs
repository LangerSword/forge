import {
  drawablyBadge,
  drawablyButton,
  drawablyCard,
  drawablyCircle,
  drawablyHighlight,
  drawablyList,
  drawablyToggle,
  drawablyUnderline,
} from "/vendor/drawably/index.js";

const dark = document.documentElement.dataset.theme === "dark";
const palette = dark
  ? { ink: "#edf0e6", paper: "#282c25", green: "#8dd3a5", pencil: "#788174", amber: "#d4a33f", red: "#e4867d", blue: "#8db4da" }
  : { ink: "#1f2922", paper: "#fffdf7", green: "#176b45", pencil: "#8f9589", amber: "#a36f17", red: "#b64038", blue: "#396c9e" };

const base = {
  stroke: palette.ink,
  fill: palette.paper,
  paper: palette.paper,
  width: 1.5,
  roughness: 0.9,
  boil: 0.3,
};

const attach = (selector, fn) => {
  document.querySelectorAll(selector).forEach((element) => fn(element));
};
const tone = (element, name) => {
  element.dataset.forgeInk = name;
  return element;
};

attach(".theme-toggle-control", (element) => {
  tone(element, "green");
  drawablyToggle(element, { ...base, stroke: palette.green, fill: palette.green, paper: palette.paper, width: 1.4 });
});

attach("a.button, button.button, .mobile-install", (element) => {
  const solid = element.classList.contains("button--accent") || element.classList.contains("mobile-install");
  tone(element, solid ? "green" : "ink");
  drawablyButton(element, {
    ...base,
    stroke: solid ? palette.green : palette.ink,
    fill: solid ? palette.green : palette.paper,
    paper: solid ? palette.paper : palette.ink,
    variant: solid ? "solid" : "outline",
  });
});

attach(".copy-button", (element) => {
  tone(element, "blue");
  drawablyButton(element, { ...base, stroke: palette.blue, fill: palette.paper, paper: palette.paper, width: 1.25, variant: "outline" });
});

attach(".ink-tab", (element) => {
  tone(element, "green");
  drawablyButton(element, {
    ...base,
    stroke: palette.green,
    fill: element.classList.contains("is-active") ? (dark ? "#314c38" : "#dcebdc") : palette.paper,
    paper: palette.ink,
    width: 1.35,
    variant: element.classList.contains("is-active") ? "scribble" : "outline",
  });
});

attach(
  ".visual-window, .evidence-demo, .support-card, .support-cta, .resource-link, .doc-link-grid > a, .boundary-panel, .doc-callout, .state-card, .doc-next > a, .code-block, .chapter-row, .command-item",
  (element) => {
    const isBoundary = element.classList.contains("boundary-panel") || element.classList.contains("doc-callout--amber");
    const isFailure = element.classList.contains("state-card--red");
    tone(element, isBoundary ? "amber" : isFailure ? "red" : "pencil");
    drawablyCard(element, {
      ...base,
      stroke: isBoundary ? palette.amber : isFailure ? palette.red : palette.pencil,
      fill: palette.paper,
      paper: palette.paper,
      width: 1.35,
    });
  },
);

attach(".source-list, .boundary-list, .requirement-list", (element) => {
  tone(element, element.classList.contains("boundary-list") ? "amber" : "green");
  drawablyList(element, {
    ...base,
    stroke: element.classList.contains("boundary-list") ? palette.amber : palette.green,
    width: 1.5,
    marker: element.classList.contains("source-list") ? "dash" : "check",
  });
});

attach(".section-kicker, .support-number, .chapter-tag", (element) => {
  tone(element, "green");
  drawablyBadge(element, {
    ...base,
    stroke: palette.green,
    fill: dark ? "#314c38" : "#dcebdc",
    paper: palette.paper,
    width: 1.1,
    variant: element.classList.contains("support-number") ? "scribble" : "outline",
  });
});

attach(
  ".hero h1 em, .section-intro h2 em, .boundary-section h2 em, .install-section h2 em, .doc-content h1 em, .support-hero h1 em, .faq-section h2 em, .evidence-demo-copy .ink-underline",
  (element) => {
    tone(element, "green");
    drawablyUnderline(element, { ...base, stroke: palette.green, width: 1.6, boil: 0.2 });
  },
);

attach(".doc-callout strong, .boundary-state strong", (element) => {
  tone(element, "amber");
  drawablyHighlight(element, { ...base, stroke: palette.amber, fill: palette.amber, width: 2, boil: 0 });
});

attach(".tone-green, .tone-amber, .tone-red", (element) => {
  const stroke = element.classList.contains("tone-red") ? palette.red : element.classList.contains("tone-amber") ? palette.amber : palette.green;
  tone(element, element.classList.contains("tone-red") ? "red" : element.classList.contains("tone-amber") ? "amber" : "green");
  drawablyCircle(element, { ...base, stroke, width: 1.25, boil: 0.2 });
});

window.forgeRefreshInk?.();
