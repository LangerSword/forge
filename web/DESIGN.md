# Forge Product Site Design Contract

## 0. Research log

- `https://hermes-agent.nousresearch.com/` — took the clear promise, visible install path, feature chapters, and direct route to documentation.
- `https://hermes-agent.nousresearch.com/docs/` — took the documentation-first information architecture: getting started, features, troubleshooting, and an explicit setup vocabulary.
- `https://nousresearch.com/` — took the editorial restraint, large statements, sparse navigation, and technical research tone.
- `https://portal.nousresearch.com/` — took the product-story sequence: one clear promise, visual feature panels, then a concrete get-started path.
- `https://opencode.ai/` and `https://opencode.ai/docs` — took the terminal-native code panel, concise capability list, open-source framing, and install/configure/initialize progression.
- Local `omh design data --kind palette --context dev-tool`, `--kind font --context docs`, and `--kind ux --context docs` — selected layered dark surfaces, readable sans body text, mono technical labels, labelled/copyable code, and constrained reading measure.
- Existing Forge site capture — retained the evidence-first voice and green signal color, but removed dashboard-like status chrome from the public entry point.

## 1. Atmosphere & identity

- **Primary direction:** bold technical-editorial.
- **Reads as:** precise, open, consequential.
- **Audience:** builders evaluating Forge as a learning/evidence layer for agent fleets; contributors who need to install and inspect the project.
- **Signature:** real evidence artifacts are presented as product illustrations: the C0 run, the candidate skill, and the evidence boundary. They are not live dashboards.
- **Borrowed elements:** terminal-native code panels from OpenCode; product chapters and installation-first navigation from Hermes/Nous Portal; documentation readability from Mintlify-like docs surfaces. No third-party logo, copy, or proprietary image is reproduced.

## 2. Color

- Canvas: `#0b0d0c`
- Canvas alternate: `#101412`
- Surface: `#151a17`
- Elevated surface: `#1b221d`
- Primary text: `#f1f4ed`
- Body text: `#c4cbc1`
- Muted text: `#8c978c`
- Quiet text: `#667066`
- Accent green: `#a8e6b8`
- Accent green deep: `#4c8c60`
- Amber candidate/open: `#edc879`
- Red baseline/error: `#f09b8f`
- Border: `#29332c`
- Strong border: `#3b493e`
- Accent budget: roughly 8% of visual area; green is reserved for action, proof, and verified states.
- Contrast floor: WCAG AA target for body text and interactive labels.

## 3. Typography

- Human-readable type: `Inter`, `ui-sans-serif`, `system-ui`, `-apple-system`, `"Segoe UI"`, sans-serif.
- Technical type: `JetBrains Mono`, `ui-monospace`, `SFMono-Regular`, `Consolas`, monospace.
- Display: clamp 3rem–6.75rem, weight 500–600, line-height 0.98–1.05, tight tracking.
- Section heading: 2.25rem–3.5rem, weight 500–600, tight tracking.
- Body: 1rem–1.125rem, line-height 1.6; reading measure capped near 70 characters.
- Labels/code: 0.7rem–0.8rem mono, positive tracking, never used for long prose.
- CJK fallback: system CJK fallback; body stays at least 14px with line-height 1.6.

## 4. Spacing & layout

- Base unit: 8px.
- Scale: 4, 8, 12, 16, 24, 32, 48, 64, 80, 112.
- Container: max 1180px; horizontal padding 24px mobile, 32px tablet, 48px desktop.
- Header: sticky, solid canvas, 1px bottom border; navigation is distinct from status.
- Hero: asymmetric two-column grid with product artifact visual on the right.
- Content chapters: alternating text/artifact layouts; no equal-card grid as the default.
- Docs pages: two-column reading layout above 900px; single column below.
- Scroll owner: document body; no scroll hijacking.

## 5. Components and states

- `site-header`: default, scrolled, mobile-open; keyboard focus-visible state.
- `button`: primary, secondary, text; hover, focus-visible, active, disabled.
- `code-block`: language/intent label, copy button, copied state, error fallback.
- `artifact-panel`: observed, candidate, target/open; each state is named in copy.
- `chapter`: heading, explanatory copy, artifact or code visual.
- `docs-sidebar`: active route, hover, focus-visible, mobile collapsed.
- `notice`: neutral, amber boundary, red failure; no animated status polling.
- `details` support item: closed, open, focus-visible.

## 6. Motion & interaction

- Motion communicates navigation and copy confirmation only.
- Transitions: 140ms ease-out; no bounce, parallax, or scroll-triggered spectacle.
- Code copy buttons use a short `Copied` state and `aria-live` message.
- Mobile navigation opens as a normal disclosure panel.
- `prefers-reduced-motion: reduce` disables transforms and smooth scrolling.

## 7. Depth & surface

- Mostly flat surfaces with thin borders and two background levels.
- Screenshots/artifact panels may use a restrained outer shadow: `0 24px 70px rgba(0,0,0,.28)`.
- No glass blur, no gradient mesh, no decorative floating blobs, and no fake live charts.
- Rounded corners: 4px code blocks, 8px controls, 14px artifact panels, 18px featured visual.

## 8. Accessibility constraints & accepted debt

- All navigation and controls are native links/buttons with visible focus rings.
- Images have meaningful alt text; SVG artifacts are labelled by surrounding copy.
- Code blocks provide copy controls and remain readable without JavaScript.
- Headings follow one H1 per page and ordered H2/H3 chapters.
- Static site has no backend form processing; support routes to GitHub issues/docs instead.
- Accepted debt: visual QA is performed against rendered captures, but no automated Lighthouse or axe runner is part of this dependency-free package yet.
