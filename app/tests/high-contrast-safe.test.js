'use strict';
/* Contrast recovery release contract. Never use color-only to certify formal status. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const index=fs.readFileSync('app/index.html','utf8');
const css=fs.readFileSync('app/high-contrast-safe.css','utf8');
const sw=fs.readFileSync('app/service-worker.js','utf8');
const app=fs.readFileSync('app/app.js','utf8');
const manifest=JSON.parse(fs.readFileSync('app/manifest.webmanifest','utf8'));

assert.match(index,/href="\.\/high-contrast-safe\.css\?v=20261116-accessibility-v1"/);
assert.ok(index.indexOf('high-contrast-safe.css')>index.indexOf('ios-status-bar.css'));
assert.ok(index.indexOf('high-contrast-safe.css')>index.indexOf('rough-race-signal.css'));
assert.doesNotMatch(index,/midnight-racing\.css/);
assert.match(sw,/boat-lab-static-v85/);
assert.match(sw,/'\.\/high-contrast-safe\.css'/);
assert.match(app,/serviceWorker\.register\('\.\/service-worker\.js',\{updateViaCache:'none'\}\)/);
assert.match(app,/\.then\(reg=>reg\.update\(\)\)/);
assert.equal(manifest.theme_color,'#081b33');
assert.match(css,/:root\s*\{[\s\S]*?color-scheme:\s*light/);
assert.match(css,/\.main \.bl-focus-board\s*\{[\s\S]*?background:\s*#ffffff\s*!important/);
assert.match(css,/\.main \.bl-race-desk,[\s\S]*?\.main \.race-timeline\s*\{[\s\S]*?background:\s*#ffffff\s*!important/);
assert.match(css,/\.main \.venue-card[\s\S]*?\.main \.venue-card\.venue-theme-night\s*\{[\s\S]*?background:\s*#ffffff\s*!important/);
assert.match(css,/\.main \.bl-focus-urgent\s*\{[\s\S]*?background:#fff5de\s*!important/);
assert.match(css,/\.topbar\s*\{[\s\S]*?background:\s*#081b33\s*!important/);
assert.match(css,/\.main \.venue-filter\.active\s*\{/);
assert.match(css,/\.main \.bl-focus-status\.is-pending\s*\{/);
assert.match(css,/\.main \.bl-focus-lane\.lane-2/);
assert.match(css,/\.main \.timeline-race\[data-exhibition-status="formal"\]/);

function rgb(hex){const s=hex.replace('#','');return [0,2,4].map(i=>parseInt(s.slice(i,i+2),16)/255)}
function luminance(hex){const v=rgb(hex).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*v[0]+.7152*v[1]+.0722*v[2]}
function ratio(a,b){const l=[luminance(a),luminance(b)].sort((x,y)=>y-x);return (l[0]+.05)/(l[1]+.05)}
const pairs=[
 ['base workspace','#142e42','#f0f5f9'],
 ['white prediction cards','#142e42','#ffffff'],
 ['venue cards','#17394d','#ffffff'],
 ['selected filter','#ffffff','#087966'],
 ['status bar','#f2fbff','#081b33'],
 ['urgent text','#60400c','#fff5de'],
 ['formal green','#07634f','#eafbf3'],
 ['provisional text','#80500f','#fff1d4'],
];
for(const [label,fg,bg] of pairs)assert.ok(ratio(fg,bg)>=4.5,`${label} contrast <4.5: ${ratio(fg,bg).toFixed(2)}`);
console.log('High contrast PWA recovery: safe light surfaces, status semantics and WCAG AA palette PASS');
