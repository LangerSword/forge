'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
const packageJson = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const ignored = new Set(['node_modules', 'dist', '.git', '.vercel', '.gitignore', 'package.json', 'package-lock.json', 'README.md', 'DESIGN.md', 'server.js', 'vercel.json', 'scripts']);
const drawablySource = path.join(root, 'node_modules', 'drawably');
const drawablyFiles = ['dist/index.js', 'dist/controls.js', 'dist/rough.js', 'dist/prng.js', 'style.css', 'LICENSE'];

function copyDrawably(targetRoot) {
  const target = path.join(targetRoot, 'vendor', 'drawably');
  fs.mkdirSync(target, { recursive: true });
  if (!fs.existsSync(drawablySource)) throw new Error('drawably is missing; run npm ci before building');
  for (const relative of drawablyFiles) {
    const source = path.join(drawablySource, relative);
    if (!fs.existsSync(source)) throw new Error(`drawably asset is missing: ${relative}`);
    fs.copyFileSync(source, path.join(target, path.basename(relative)));
  }
}


function collect(directory, prefix = '') {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (ignored.has(entry.name)) return [];
    const relative = path.join(prefix, entry.name);
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) return collect(absolute, relative);
    return [relative];
  });
}

const assets = collect(root).filter((file) => !file.startsWith('dist' + path.sep));
if (!assets.includes('index.html') || !assets.includes('styles.css') || !assets.includes('app.js')) {
  throw new Error('required website entry assets are missing');
}

const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
for (const reference of ['styles.css', 'app.js', 'theme-init.js', 'vendor/drawably/style.css', 'drawably-ink.mjs']) {
  if (!html.includes(reference)) throw new Error(`index.html does not reference ${reference}`);
}

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });
for (const relative of assets) {
  const source = path.join(root, relative);
  const target = path.join(dist, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
}
copyDrawably(dist);

console.log(`Forge build: ${packageJson.name}@${packageJson.version}`);
console.log(`Forge build: copied ${assets.length} site files plus Drawably runtime to dist/`);
console.log('Forge build: entrypoint index.html verified');
