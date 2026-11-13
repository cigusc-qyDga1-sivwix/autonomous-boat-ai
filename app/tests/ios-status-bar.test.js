'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');

const html = fs.readFileSync('app/index.html', 'utf8');
const css = fs.readFileSync('app/ios-status-bar.css', 'utf8');
const sw = fs.readFileSync('app/service-worker.js', 'utf8');
const manifest = JSON.parse(fs.readFileSync('app/manifest.webmanifest', 'utf8'));

assert.match(html, /name="viewport" content="[^"]*viewport-fit=cover"/);
assert.match(html, /name="apple-mobile-web-app-capable" content="yes"/);
assert.match(html, /name="apple-mobile-web-app-status-bar-style" content="default"/);
assert.doesNotMatch(html, /apple-mobile-web-app-status-bar-style" content="black-translucent"/);

const theme = /name="theme-color" content="(#[0-9a-f]{6})"/.exec(html)?.[1];
assert.equal(theme, '#eaf7fb');
assert.equal(manifest.theme_color, theme, 'Installed PWA theme matches HTML theme');
assert.match(css, /--ios-top-surface:\s*#eaf7fb/);
assert.match(css, /html\s*\{[\s\S]*?background-color:\s*var\(--ios-top-surface\)/);
assert.match(css, /@media\s*\(max-width:\s*810px\)/);
assert.match(css, /\.topbar\s*\{[\s\S]*?background:\s*linear-gradient\(180deg,\s*#eaf7fb/);

const cssLink = html.indexOf('href="./ios-status-bar.css?v=20261113-light-top-v1"');
const premiumLink = html.indexOf('href="./premium-ui.css?');
assert.ok(cssLink > premiumLink && premiumLink >= 0,
  'iPhone contrast rules must override the premium sticky topbar');
assert.match(sw, /boat-lab-static-v79-ios-status-contrast/);
assert.match(sw, /'\.\/ios-status-bar\.css'/);
console.log('iPhone PWA status-bar contrast contract: PASS');
