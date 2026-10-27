const assert=require('node:assert/strict');
const fs=require('node:fs');
const api=require('../exhibition-watch.js');
const html=fs.readFileSync('app/exhibition-watch.html','utf8');
const index=fs.readFileSync('app/index.html','utf8');
const research=fs.readFileSync('app/exhibition.html','utf8');

const r=api.route('2026-10-27','大村',8);
assert.equal(r.venueCode,'24');
assert.equal(r.boatcast,'https://boatcast.jp/');
assert.equal(r.beforeinfo,'https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=8&jcd=24&hd=20261027');
assert.equal(r.records,'./exhibition.html?date=2026-10-27');
assert.equal(api.route('2026-10-27','24',8).venue,'大村');
for(const item of [['2026-02-30','大村',8],['2026-10-27','大村',0],['2026-10-27','大村',13],['2026-10-27','無効',8]]){
 assert.equal(api.route(...item),null);
}
const parsed=api.initial('?venue=%E5%A4%A7%E6%9D%91&race=8&date=2026-10-27');
assert.deepEqual(parsed,{day:'2026-10-27',venue:'大村',race:8});
assert.equal(api.initial('?venue=24&race=8&date=2026-10-27').venue,'大村');
assert.equal(api.initial('?venue=25&race=-1&date=2026-99-99','2026-10-27').race,1);
assert.equal(api.jstDate(new Date('2026-10-27T15:02:00Z')),'2026-10-28');
assert.match(html,/id="watch-player"/);
assert.match(html,/id="watch-permission"/);
assert.match(html,/展示リプレイ/);
assert.match(index,/exhibition-watch\.html/);
assert.match(research,/exhibition-watch\.html/);
assert.doesNotMatch(html,/<iframe|<video[^>]*src="https:/i);
assert.doesNotMatch(fs.readFileSync('app/exhibition-watch.js','utf8'),/\bfetch\s*\(/);
assert.equal(api.BOATCAST,'https://boatcast.jp/');
console.log('BOAT LAB viewing-only official exhibition portal: PASS');
