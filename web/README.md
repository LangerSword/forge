# Forge product site

A static product, documentation, and support site for Forge with one small runtime dependency: [`drawably`](https://www.npmjs.com/package/drawably) provides accessible native-control SVG chrome and reduced-motion-aware ink effects for the local proof surface. The site remains a dependency-light static package; it does not connect to a Forge backend or live AO tracker.

## Scripts

```sh
npm ci --ignore-scripts
npm run build    # validate and copy the site into dist/
npm start        # serve dist/ (PORT and HOST are supported)
npm run preview  # build, then serve on port 4173
npm pack --dry-run
```

No runtime service is required beyond Node.js 18 or newer. The build vendors the browser-compatible Drawably ESM modules and stylesheet into the static output; React is not installed or used.

## Routes

- `/` — Forge product overview, learning-loop illustration, C0 evidence artifact, install path.
- `/docs/` — documentation overview.
- `/docs/installation.html` — Python/uv runtime installation and verification.
- `/docs/architecture.html` — execution, verification, reflection, and promotion boundaries.
- `/docs/cli.html` — local CLI reference.
- `/support/` — setup checklist, troubleshooting, and GitHub issue path.

## Vercel deployment

This package is deployed as a static Vercel project from the Forge repository root. The browser source package remains under `web/`; the root build copies the complete site into `public/` for Vercel's static output contract.

```text
Root directory: .
Framework: Other / null
Install command: npm ci --ignore-scripts
Build command: npm run build
Output directory: public
Production URL: https://web-rust-three-63.vercel.app
```

The package is published to the public npm registry as `@langersword/forge`.
The publish workflow uses npm Trusted Publishing with GitHub OIDC; users do not
need credentials to install the public package:

```text
registry: https://registry.npmjs.org
package: @langersword/forge
```

```text
VERCEL_ORG_ID
VERCEL_PROJECT_ID
VERCEL_TOKEN
```

## Other static hosts

The same package can deploy to Netlify, Cloudflare Pages, GitHub Pages, or another static host:

- Build command: `npm run build`
- Publish/output directory: `dist`
- Drawably browser runtime is copied into `dist/vendor/drawably/` during the build.

For a Node host, run `npm run build` during release and start with `npm start`. The server accepts `HOST` and `PORT` environment variables.

## Content boundary

The site uses self-authored SVG illustrations and repository-backed evidence copy. The C0 run, candidate skill, and Neatlogs claims are labeled by state. AO autonomous completion, cross-harness transfer, and Supermemory remain future proof points in the product documentation.