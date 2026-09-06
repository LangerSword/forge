#!/usr/bin/env node
'use strict';

const { spawn } = require('node:child_process');
const path = require('node:path');

const packageRoot = path.resolve(__dirname, '..');
const server = path.join(packageRoot, 'web', 'server.js');
const dist = path.join(packageRoot, 'public');
const args = [server, '--dir', dist, ...process.argv.slice(2)];
const child = spawn(process.execPath, args, {
  cwd: packageRoot,
  env: process.env,
  stdio: 'inherit'
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 1);
  }
});

child.on('error', (error) => {
  console.error(`Forge evidence site failed to start: ${error.message}`);
  process.exit(1);
});
