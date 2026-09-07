'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
const packageJson = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const ignored = new Set(['node_modules', 'dist', '.git', '.vercel', '.gitignore', 'package.json', 'package-lock.json', 'README.md', 'DESIGN.md', 'server.js', 'vercel.json', 'scripts']);

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
for (const reference of ['styles.css', 'app.js']) {
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

console.log(`Forge build: ${packageJson.name}@${packageJson.version}`);
console.log(`Forge build: copied ${assets.length} site files to dist/`);
console.log('Forge build: entrypoint index.html verified');
