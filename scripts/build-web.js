'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const source = path.join(root, 'web');
const output = path.join(root, 'public');
const assets = ['index.html', 'styles.css', 'app.js'];

for (const asset of assets) {
  const sourcePath = path.join(source, asset);
  if (!fs.existsSync(sourcePath) || !fs.statSync(sourcePath).isFile()) {
    throw new Error(`required web asset is missing: ${asset}`);
  }
}

const html = fs.readFileSync(path.join(source, 'index.html'), 'utf8');
for (const reference of ['styles.css', 'app.js']) {
  if (!html.includes(reference)) {
    throw new Error(`web/index.html does not reference ${reference}`);
  }
}

fs.rmSync(output, { recursive: true, force: true });
fs.mkdirSync(output, { recursive: true });
for (const asset of assets) {
  fs.copyFileSync(path.join(source, asset), path.join(output, asset));
}

console.log(`Forge root build: copied ${assets.length} static assets to public/`);
