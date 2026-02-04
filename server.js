// server.js - cPanel / Passenger friendly entrypoint
// This file expects the project to be built with `next build` using
// `next.config.js` output: 'standalone'. After build, Next places a
// runnable server under `.next/standalone/server.js` which we require.

/* eslint-disable no-console */

if (process.env.NODE_ENV !== 'production') {
  console.warn('server.js is intended for running the standalone production build.');
}

try {
  // Require the standalone server produced by `next build` (output: 'standalone')
  // This file is present at `.next/standalone/server.js` after a successful build.
  // cPanel Startup File should point to this `server.js` at repository root.
  require('./.next/standalone/server.js');
} catch (err) {
  console.error('Could not start standalone server. Make sure you ran `npm run build` first.');
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
}
// cPanel friendly entrypoint - runs the Next standalone server if built
const path = require('path');
const fs = require('fs');

const standaloneServer = path.join(__dirname, '.next', 'standalone', 'server.js');
if (fs.existsSync(standaloneServer)) {
  require(standaloneServer);
} else {
  console.error('Standalone server not found. Run `npm run build` with output:standalone');
  process.exit(1);
}
