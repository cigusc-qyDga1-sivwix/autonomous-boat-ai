'use strict';
// Static visual contract: the presentation-only midnight layer must keep
// formal/provisional meanings, PWA cache freshness and iOS legibility.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const html = fs.readFileSync('app/index.html', 'utf8');
const css = fs.readFileSync('app/midnight-racing.css', 'utf8');
const sw = fs.readFileSync('app/service-worker.js', 'utf8');
const manifest = JSON.parse(fs.readFileSync('app/manifest.webmanifest', 'utf8'));

assert.match(html, /midnight-racing\.css\?v=20261116-v1/);
assert.ok(html.indexOf('href="./midnight-racing.css') > html.indexOf('href="./ios-status-bar.css'),
  'The midnight theme must load AFTER the native status-bar contrast rules.');
assert.ok(html.indexOf('href="./midnight-racing.css') > html.indexOf('href="./premium-ui.css'),
  'The midnight theme must override old dashboard light chrome.');
assert.match(sw, /boat-lab-static-v83/);
assert.match(sw, /'\.\/midnight-racing\.css'/);
assert.equal(manifest.background_color, '#081b33');
assert.equal(manifest.theme_color, '#081b33');
assert.match(css, /\.topbar\s*\{[\s\S]*?background:linear-gradient/);
assert.match(css, /@media\s*\(max-width:810px\)/);
assert.match(css, /\.bottom-nav button\.active/);
assert.match(css, /\.venue-card/);
assert.match(css, /\.bl-focus-board/);
assert.match(css, /\.bl-focus-card\.is-pending/);
assert.match(css, /\.timeline-urgent/);
assert.match(css, /@media\s*\(prefers-reduced-motion:reduce\)/);

// Predictive gates and formal status signals remain in their older,
 // higher-specificity selectors; this layer NEVER invents or promotes forecasts.
assert.doesNotMatch(css, /content\s*:\s*["'](?:正式予想|的中|展示反映済み)/);
assert.doesNotMatch(css, /display\s*:\s*none\s*;\s*\/\*\s*formal/);
assert.match(css, /presentation-only|Presentation-only/i);
console.log('Midnight Racing premium PWA visual contract: PASS');
