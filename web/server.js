'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { URL } = require('node:url');

const MIME_TYPES = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8'
};

function argumentValue(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const root = path.resolve(process.cwd(), argumentValue('--dir', 'dist'));
const host = process.env.HOST || '0.0.0.0';
const port = Number.parseInt(process.env.PORT || argumentValue('--port', '4173'), 10);

if (!Number.isInteger(port) || port < 0 || port > 65535) {
  console.error('Forge server: PORT/--port must be an integer from 0 to 65535.');
  process.exit(1);
}

function filePathFor(requestUrl) {
  let pathname;
  try { pathname = decodeURIComponent(new URL(requestUrl, 'http://forge.local').pathname); } catch { return null; }
  if (pathname.includes('\0')) return null;
  const relativePath = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
  const filePath = path.resolve(root, relativePath);
  const rootPrefix = `${root}${path.sep}`;
  if (filePath !== root && !filePath.startsWith(rootPrefix)) return null;
  return filePath;
}

function candidatesFor(requestUrl) {
  const primary = filePathFor(requestUrl);
  if (!primary) return [];
  const pathname = new URL(requestUrl, 'http://forge.local').pathname;
  if (pathname === '/') return [primary];
  if (pathname.endsWith('/')) return [path.join(primary, 'index.html')];
  return [primary, path.join(primary, 'index.html')];
}

function send(response, status, body, headers = {}) {
  response.writeHead(status, headers);
  if (response.req.method !== 'HEAD') response.end(body); else response.end();
}

const server = http.createServer((request, response) => {
  if (!['GET', 'HEAD'].includes(request.method)) {
    send(response, 405, 'Method Not Allowed\n', { 'Content-Type': 'text/plain; charset=utf-8', Allow: 'GET, HEAD' });
    return;
  }

  const candidates = candidatesFor(request.url || '/');
  if (!candidates.length) { send(response, 400, 'Bad Request\n', { 'Content-Type': 'text/plain; charset=utf-8' }); return; }
  const requestedPath = candidates.find((candidate) => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
  if (!requestedPath) { send(response, 404, 'Not Found\n', { 'Content-Type': 'text/plain; charset=utf-8' }); return; }

  const stats = fs.statSync(requestedPath);
  const extension = path.extname(requestedPath).toLowerCase();
  const headers = { 'Cache-Control': 'no-cache', 'Content-Type': MIME_TYPES[extension] || 'application/octet-stream', 'Content-Length': stats.size };
  if (request.method === 'HEAD') { send(response, 200, '', headers); return; }
  fs.createReadStream(requestedPath).on('error', () => send(response, 500, 'Internal Server Error\n', { 'Content-Type': 'text/plain; charset=utf-8' })).once('open', () => response.writeHead(200, headers)).pipe(response);
});

server.on('error', (error) => { console.error(`Forge server: ${error.message}`); process.exitCode = 1; });
server.listen(port, host, () => {
  const address = server.address();
  const displayPort = typeof address === 'object' && address ? address.port : port;
  console.log(`Forge preview serving ${root} at http://${host}:${displayPort}`);
});
