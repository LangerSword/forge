'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const source = path.join(root, 'web');
const output = path.join(root, 'public');
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

const assets = collect(source).filter((file) => !file.startsWith('dist' + path.sep));
if (!assets.includes('index.html') || !assets.includes('styles.css') || !assets.includes('app.js')) {
  throw new Error('required web assets are missing');
}

const html = fs.readFileSync(path.join(source, 'index.html'), 'utf8');
for (const reference of ['styles.css', 'app.js', 'theme-init.js', 'vendor/drawably/style.css', 'drawably-ink.mjs']) {
  if (!html.includes(reference)) throw new Error(`web/index.html does not reference ${reference}`);
}

fs.rmSync(output, { recursive: true, force: true });
fs.mkdirSync(output, { recursive: true });
for (const relative of assets) {
  const sourcePath = path.join(source, relative);
  const outputPath = path.join(output, relative);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.copyFileSync(sourcePath, outputPath);
}
copyDrawably(output);

console.log(`Forge root build: copied ${assets.length} static site files plus Drawably runtime to public/`);
