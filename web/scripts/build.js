'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
const assets = ['index.html', 'styles.css', 'app.js'];

function requireFile(relativePath) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
    throw new Error(`required asset is missing: ${relativePath}`);
  }
  return absolutePath;
}

const packageJson = JSON.parse(fs.readFileSync(requireFile('package.json'), 'utf8'));
const sourcePaths = assets.map(requireFile);
const sourceHtml = fs.readFileSync(sourcePaths[0], 'utf8');

for (const reference of ['styles.css', 'app.js']) {
  if (!sourceHtml.includes(reference)) {
    throw new Error(`index.html does not reference ${reference}`);
  }
}

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });
sourcePaths.forEach((sourcePath, index) => {
  fs.copyFileSync(sourcePath, path.join(dist, assets[index]));
});

console.log(`Forge build: ${packageJson.name}@${packageJson.version}`);
console.log(`Forge build: copied ${assets.length} files to dist/`);
console.log('Forge build: entrypoint index.html verified');
