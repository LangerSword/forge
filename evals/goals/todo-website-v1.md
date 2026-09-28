# Todo website — build plan

Repo: /home/lakshaya/projects/todo
Harness: opencode
Artifact: index.html
Max minutes: 10

## Goal

Build the first complete version of a personal todo website in this repo: a
dependency-free single-page app (`index.html` + `styles.css` + `app.js`) with
a dark editorial look — near-black background, warm off-white text, one
accent color, a real type scale, generous spacing. You can add, edit,
complete, and delete todos; filter all / active / done with live counts; and
everything persists in `localStorage` (key: `todos`). Keyboard-first: Enter
adds, Escape cancels, visible focus states everywhere. No external requests,
no frameworks, no build step. Responsive from 360px to 1440px. A designed
empty state when the list is clear.

## Acceptance

- index.html, styles.css, app.js exist; index.html links both; the page loads with zero console errors.
- Add: typing + Enter appends a todo; the input clears; the list re-renders from state.
- Toggle: clicking a todo's checkbox toggles it complete; the change survives a reload.
- Edit: editing a todo's text commits on Enter and cancels on Escape.
- Delete: a per-item delete control removes it; the removal survives a reload.
- Filters: all / active / done switch the visible list; a live count per filter is shown.
- Persistence: a reload restores identical state (localStorage key `todos`).
- Layout: usable and non-broken at 360px and 1440px widths.
- No external network requests; the whole app is small enough to read in one sitting.

## Verification

- `test -f index.html`
- `test -f styles.css`
- `test -f app.js`
- `grep -q "localStorage" app.js`
- `grep -q "todos" app.js`
- `grep -q "styles.css" index.html`

## Build phases (one phase per `forge run-graph`)

| # | Phase | Artifact(s) | Done when |
|---|-------|-------------|-----------|
| 0 | Scaffold | repo + registration | `git init` + first commit; repo added to AO (id `todo`) |
| 1 | Shell + design tokens | index.html, styles.css | page renders: header, input, empty state; tokens set (bg, text, accent, spacing, radius) |
| 2 | Store + CRUD | app.js | add / toggle / delete work against a versioned `todos` store; reload persists |
| 3 | Edit + filters + counts | app.js | edit commits on Enter, cancels on Escape; all/active/done filters; counts live |
| 4 | Polish | all three files | responsive 360→1440px; focus rings; ≤150ms transitions; honors `prefers-reduced-motion`; no layout shift |
| 5 | Tests | tests/store.test.js (+ optional Playwright e2e) | `node --test` green; e2e flow add → complete → filter → delete passes |
| 6 | Ship | README + deploy | GitHub repo pushed; site live (Pages / Cloudflare Pages); URL returns 200 |

## Notes

- Phase 0, once: `git init && git add -A && git commit -m init`, then register
  the repo with AO (`ao project add /home/lakshaya/projects/todo`; id derives
  from the path) so `forge run-graph` can target it.
- Each phase is bounded: one artifact focus, the deterministic checks above,
  no scope creep.
- Later phases re-run the same acceptance/verification; phase 5 adds its own
  test command to the `## Verification` section when it lands.