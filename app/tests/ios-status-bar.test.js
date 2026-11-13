'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');

const html = fs.readFileSync('app/index.html', 'utf8');
const css = fs.readFileSync('app/ios-status-bar.css', 'utf8');
const sw = fs.readFileSync('app/service-worker.js', 'utf8');
const manifest = JSON.parse(fs.readFileSync('app/manifest.webmanifest', 'utf8'));

assert.match(html, /name="viewport" content="[^"]*viewport-fit=cover"/);
assert.match(html, /name="apple-mobile-web-app-capable" content="yes"/);
assert.match(html, /name="apple-mobile-web-app-status-bar-style" content="black-translucent"/);
assert.doesNotMatch(html, /apple-mobile-web-app-status-bar-style" content="default"/);

const theme = /name="theme-color" content="(#[0-9a-f]{6})"/.exec(html)?.[1];
assert.equal(theme, '#081b33');
assert.equal(manifest.theme_color, theme, 'Installed PWA theme matches HTML theme');
assert.match(css, /--ios-top-surface:\s*#081b33/);
assert.match(css, /html\s*\{[\s\S]*?background-color:\s*var\(--ios-top-surface\)/);
assert.match(css, /@media\s*\(max-width:\s*810px\)/);
assert.match(css, /\.topbar\s*\{[\s\S]*?background:\s*#081b33/);
assert.match(css, /height:\s*calc\(64px \+ env\(safe-area-inset-top/);
assert.match(css, /\.topbar \.mobile-brand\s*\{[\s\S]*?color:\s*#f5fbff/);
assert.match(css, /\.topbar \.quick-links-menu summary\s*\{[\s\S]*?color:\s*#e0f8f4/);

const cssLink = html.indexOf('href="./ios-status-bar.css?v=20261113-dark-top-v2"');
const premiumLink = html.indexOf('href="./premium-ui.css?');
assert.ok(cssLink > premiumLink && premiumLink >= 0,
  'iPhone dark header rules must override the premium sticky topbar');
assert.match(sw, /boat-lab-static-v80/);
assert.match(sw, /'\.\/ios-status-bar\.css'/);
console.log('iPhone PWA dark status-bar contrast contract: PASS');
