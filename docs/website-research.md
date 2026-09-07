# Forge site research: Hermes Agent × Drawably

**Status:** observed research input for the Forge UI pass
**Scope:** official public landing/docs surfaces and the official Drawably repository
**Boundary:** this document records source observations and design implications. It is not implementation or visual-QA evidence.

## Sources inspected

- Hermes landing: <https://hermes-agent.nousresearch.com/>
- Hermes docs: <https://hermes-agent.nousresearch.com/docs/>
- Hermes installation: <https://hermes-agent.nousresearch.com/docs/getting-started/installation>
- Drawably landing: <https://drawably.dev/>
- Drawably repository: <https://github.com/Danilaa1/drawably>
- Drawably package manifest: <https://raw.githubusercontent.com/Danilaa1/drawably/main/package.json>
- Drawably README: <https://raw.githubusercontent.com/Danilaa1/drawably/main/README.md>

## Hermes observations

### Product and information architecture

- The landing promise is direct: **The Agent That Grows With You**.
- The primary path is visible immediately: desktop download or terminal installation.
- Product capabilities are presented as numbered chapters: connect, remember, schedule, delegate, search, experiment.
- The docs surface leads with installation, quickstart, feature exploration, and troubleshooting rather than internal runtime telemetry.
- The landing page links into docs, source, community, and product/support surfaces.

### Framework/build evidence

- The official Hermes website package is Docusaurus `3.10.2` with React `19.2.7`, `@mdx-js/react`, Mermaid support, and a static `docusaurus build` output according to the repository's `website/package.json` and README.
- The deployed landing page is served through a Next/Vercel-style production bundle with static chunks and Turbopack markers; this is deployment output, not the source-site framework claim.
- The HTML preloads custom font assets including `CourierPrime`, `RulesVariable`, and `Sigurd`.
- This distinction matters: Forge should borrow the product sequencing and docs structure, not copy the Hermes implementation stack into its dependency-light static package.

### Design implications for Forge

- Keep one product promise above the fold.
- Make installation and docs first-class actions.
- Use numbered chapters to explain the learning system.
- Show product artifacts and clear states instead of a fake live-control dashboard.
- Borrow the clarity and sequencing, not the brand copy, fonts, logo, or assets.

## Drawably observations

### Product and interaction model

- The public page presents hand-drawn controls as the product itself: buttons, radios, checkboxes, input, checklist, and annotations.
- The README describes a zero-runtime-dependency package with native inputs kept in the DOM and decorative SVG sketches layered underneath.
- Sketches are generated from seeded randomness; controls support roughness and a CSS “boil” effect.
- Hover/press interactions can re-sketch controls; button states include idle, loading, error, and success.
- `prefers-reduced-motion` freezes the sketch to a static frame.
- The package exposes both vanilla functions and React wrappers, but Forge does not need to adopt React for this pass.

### Design implications for Forge

- Use native links/buttons/inputs as the interaction truth.
- Add a small original ink layer to Forge buttons, evidence annotations, and one local product artifact.
- Convey state with text and semantics first; roughness is a visual reinforcement, not the only signal.
- Keep the effect sparse so the product remains technical and readable.
- Create original Forge marks, stroke shapes, colors, and labels. The site uses the published `drawably@0.3.10` browser runtime, but does not copy the Drawably site, wordmark, or exact layout.

## Forge-specific constraints

- Current website source is static HTML/CSS/JS under `web/`, with the published Drawably runtime installed as the sole website dependency and vendored into build output.
- Existing routes must remain available: `/`, `/docs/`, `/docs/installation.html`, `/docs/architecture.html`, `/docs/cli.html`, `/support/`.
- Vercel output is generated into root `public/` by `scripts/build-web.js`.
- The public site must not imply live AO sessions, live worker counts, hosted Forge state, cross-harness transfer, or Supermemory integration.
- Existing evidence labels—observed, candidate, and unverified—remain authoritative.
- Any hand-drawn interaction must support focus-visible and reduced-motion behavior.

## Open questions

- Exact Hermes source repository architecture beyond the deployed landing bundle is not necessary for the Forge static-site implementation and should not be inferred from the landing HTML alone.
- Formal Lighthouse/axe results are not yet observed for the Forge redesign.
- Visual PASS remains blocked until fresh rendered captures are reviewed after implementation.
