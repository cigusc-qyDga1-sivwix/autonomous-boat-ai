'use strict';
const assert=require('node:assert/strict');
const api=require('../statistical-shadow.js');
const r={venue:'徳山',race:1,sha256:'abc'};
const row={source_sha256:'abc',trained_through:'2026-10-26',training_n:735,frozen_at_utc:'2026-10-27T00:00:00Z',
 bets:['1-2-3','1-3-2','2-1-3','2-3-1'].map((combination,i)=>({combination,virtual_yen:i?12000:14000}))};
const doc={event_date:'2026-10-27',races:{'徳山-1':row}};
assert.match(api.panel(doc,r,'2026-10-27'),/検証用・正式買い目とは別/);
assert.match(api.panel(doc,r,'2026-10-27'),/735R/);
assert.match(api.panel(doc,{...r,sha256:'new'},'2026-10-27'),/未取得/);
assert.match(api.panel(doc,r,'2026-10-26'),/未取得/);
assert.match(api.panel({...doc,races:{'徳山-1':{...row,bets:[{combination:'<img>',virtual_yen:50000}]}}},r,'2026-10-27'),/検証できません/);
assert.match(api.panel({...doc,races:{'徳山-1':{...row,trained_through:'<script>'}}},r,'2026-10-27'),/&lt;script&gt;/);
console.log('Statistical shadow: source/date isolation, budget guards, no formal promotion, escaped metadata: PASS');
