# Forge evidence site

A dependency-free static evidence snapshot for the Forge submission. The npm package builds the browser assets into `dist/` and includes a tiny Node static server for local preview or a Node-based host.

## Scripts

```sh
npm ci --ignore-scripts
npm run build    # validate and copy the site into dist/
npm start        # serve dist/ (PORT and HOST are supported)
npm run serve    # alias for npm start
npm run preview  # build, then serve on port 4173
npm pack --dry-run
```

No runtime dependency installation is required beyond Node.js 18 or newer.

## Vercel deployment

This package is deployed as a static Vercel project from the Forge repository root. The browser source package remains under `web/`; the root build copies it into `public/` for Vercel's static output contract.

```text
Root directory: .
Framework: Other / null
Install command: npm ci --ignore-scripts
Build command: npm run build
Output directory: public
Production URL: https://web-rust-three-63.vercel.app
```

The repository workflow is `.github/workflows/deploy-forge-web.yml`. It runs on pushes that change `web/**` or manually through `workflow_dispatch`:

```text
npm ci --ignore-scripts
npm run build
asset checks + node --check
npx vercel deploy --prebuilt --prod
```

Configure these GitHub Actions secrets before relying on the workflow:

```text
VERCEL_ORG_ID
VERCEL_PROJECT_ID
VERCEL_TOKEN
```

The Vercel project is linked through the CLI and should not require committing `.vercel/`; that directory is ignored.

## Other static hosts

The same package can deploy to Netlify, Cloudflare Pages, GitHub Pages, or another static host:

- Build command: `npm run build`
- Publish/output directory: `dist`

For a Node host, run `npm run build` during release and start with `npm start`. The server accepts `HOST` and `PORT` environment variables.

## Evidence boundary

This package is a static evidence snapshot. It does not connect to a live Forge backend. AO lifecycle, new runs, and fresh evidence remain unverified until an explicit backend connection is added.
