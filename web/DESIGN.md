# Forge Product Site Design Contract

## 0. Research log

- `https://hermes-agent.nousresearch.com/` — took the clear promise, visible install path, feature chapters, and direct route to documentation.
- `https://hermes-agent.nousresearch.com/docs/` — took the documentation-first information architecture: getting started, features, troubleshooting, and an explicit setup vocabulary.
- `https://nousresearch.com/` — took the editorial restraint, large statements, sparse navigation, and technical research tone.
- `https://portal.nousresearch.com/` — took the product-story sequence: one clear promise, visual feature panels, then a concrete get-started path.
- `https://opencode.ai/` and `https://opencode.ai/docs` — took the terminal-native code panel, concise capability list, open-source framing, and install/configure/initialize progression.
- Local `omh design data --kind palette --context dev-tool`, `--kind font --context docs`, and `--kind ux --context docs` — selected layered dark surfaces, readable sans body text, mono technical labels, labelled/copyable code, and constrained reading measure.
- Existing Forge site capture — retained the evidence-first voice and green signal color, but removed dashboard-like status chrome from the public entry point.
- `https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/package.json` and README — verified the official docs site uses Docusaurus 3.10.2 + React 19 and static output; Forge keeps its own dependency-light static package.
- `https://drawably.dev/`, `https://github.com/Danilaa1/drawably`, and the public README/source — took the principle of native controls plus aria-hidden sketch decoration, seeded roughness, stateful controls, and reduced-motion freezing. Forge uses the published `drawably@0.3.10` runtime for the proof surface; it does not copy the upstream site, wordmark, or exact layout.

## 1. Atmosphere & identity

- **Primary direction:** paper-and-ink product notebook.
- **Reads as:** tactile, precise, human, inspectable.
- **Audience:** builders evaluating Forge as a learning/evidence layer for agent fleets; contributors who need to install and inspect the project.
- **Signature:** every surface reads like a working research notebook: paper cards, ink annotations, checked states, and explicit evidence labels. The C0 run, candidate skill, and evidence boundary remain illustrations—not live dashboards.
- **Borrowed elements:** Drawably's native-control/SVG-chrome grammar, Hermes/Nous product chapters and installation-first navigation, and OpenCode's concise technical references. No third-party logo, copy, or proprietary image is reproduced.

## 2. Color

- Paper canvas: `#f7f2e8`
- Paper alternate: `#eee7d8`
- Paper card: `#fffdf7`
- Ink: `#1f2922`
- Body ink: `#4f5a50`
- Quiet ink: `#7b8177`
- Pencil line: `#c9c0ae`
- Strong line: `#8f9589`
- Forge green: `#176b45`
- Forge green light: `#dcebdc`
- Candidate amber: `#a36f17`
- Baseline red: `#b64038`
- Reference blue: `#396c9e`
- Accent budget: green marks verified/action states; red marks failure; amber marks candidate/open; blue marks reference/navigation.
- Contrast floor: WCAG AA target for body text and interactive labels; quiet ink is decorative only.

## 3. Typography

- Human-readable type: `Inter`, `ui-sans-serif`, system sans; use weight and ink color for hierarchy.
- Technical type: `JetBrains Mono`, `ui-monospace`, `SFMono-Regular`, Consolas, monospace.
- Notebook annotation: system cursive only for short labels, never for instructions or long prose.
- Display: clamp 3rem–6.75rem, weight 650–750, line-height 0.98–1.05, tight tracking.
- Section heading: 2.25rem–3.5rem, weight 650–750, tight tracking.
- Body: 1rem–1.125rem, line-height 1.65; reading measure capped near 70 characters.
- Labels/code: 0.7rem–0.8rem mono, positive tracking, never used for long prose.
- CJK fallback: system CJK fallback; body stays at least 14px with line-height 1.6.

## 4. Spacing & layout

- Base unit: 8px.
- Scale: 4, 8, 12, 16, 24, 32, 48, 64, 80, 112.
- Container: max 1180px; horizontal padding 24px mobile, 32px tablet, 48px desktop.
- Header: sticky paper strip with a hand-drawn divider; navigation is distinct from status.
- Hero: asymmetric two-column notebook spread with a pinned artifact visual on the right.
- Content chapters: alternating notes, artifact cards, and ruled lists; no equal-card grid as the default.
- Docs pages: paper sidebar plus a ruled reading column above 900px; single column below.
- Scroll owner: document body; no scroll hijacking.

## 5. Components and states

- `site-header`: default, scrolled, mobile-open; keyboard focus-visible state.
- `button`: Drawably outline/solid/scribble variants; hover, focus-visible, active, disabled, loading, success, error.
- `code-block`: language/intent label, copy button, copied state, error fallback.
- `artifact-panel`: observed, candidate, target/open; each state is named in copy and colored with ink marks.
- `chapter`: heading, explanatory copy, artifact or code visual.
- `docs-sidebar`: active route, hover, focus-visible, mobile collapsed.
- `notice`: neutral, amber boundary, red failure; hand-drawn top rule; no animated status polling.
- `details` support item: closed, open, focus-visible.

## 6. Motion & interaction

- Motion communicates navigation, copy confirmation, and a restrained proof-surface sketch boil only; it never represents live runtime state.
- Transitions: 140ms ease-out; no bounce, parallax, or scroll-triggered spectacle.
- Code copy buttons use a short `Copied` state and `aria-live` message.
- Mobile navigation opens as a normal disclosure panel.
- `prefers-reduced-motion: reduce` disables transforms and smooth scrolling.

## 7. Depth & surface

- Paper surfaces use thin pencil lines, small rotations, corner notches, and restrained offset shadows.
- Screenshots/artifact panels may use a notebook shadow: `5px 7px 0 rgba(31,41,34,.12)`.
- No glass blur, no gradient mesh, no decorative floating blobs, and no fake live charts.
- Rounded corners are irregular and modest; Drawably SVG chrome supplies the hand-drawn edge on interactive/card surfaces.

## 8. Accessibility constraints & accepted debt

- All navigation and controls are native links/buttons with visible focus rings.
- Images have meaningful alt text; SVG artifacts are labelled by surrounding copy.
- Code blocks provide copy controls and remain readable without JavaScript.
- Headings follow one H1 per page and ordered H2/H3 chapters.
- Static site has no backend form processing; support routes to GitHub issues/docs instead.
- Accepted debt: visual QA is performed against rendered captures, but no automated Lighthouse or axe runner is part of this dependency-light package yet.
