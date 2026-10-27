'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const p=x=>fs.readFileSync(x,'utf8');
const app=p('app/app.js'), research=p('app/exhibition-research.js'), html=p('app/exhibition.html'), index=p('app/index.html'), sw=p('app/service-worker.js'), venue=p('app/venue-board.js');
assert.match(app,/async function pollExhibitionHeartbeat\(\)/);
assert.match(app,/data\/exhibition\/status-latest\.json\?fresh=/);
assert.match(app,/setInterval\(pollExhibitionHeartbeat,60000\)/);
assert.match(app,/if\(exhibitionHeartbeatBusy\|\|document\.hidden\|\|readJSON\(STORE_DATA,null\)\)return;/,
 'manual imports must not be silently overridden');
assert.match(research,/setInterval\(\(\)=>\{if\(!document\.hidden/);
assert.match(research,/最新観測/);
assert.match(research,/以前の記録を表示中。最新情報ではありません/);
assert.match(html,/exhibition-research\.js\?v=20261027-auto-fresh/);
assert.match(index,/app\.js\?v=20261027-venue-v14/);
assert.match(index,/tactical-1m\.js\?v=20261027-venue-v14/);
assert.match(index,/venue-tactics-v2\.js\?v=20261027-venue23/);
assert.match(venue,/four-factor-v1\.3-conditional-scenarios-untrained/);
assert.match(sw,/boat-lab-static-v51/);
const listeners={};
const fetchCalls=[],cacheCalls=[];
const self={
 location:{origin:'https://example.test'},
 addEventListener:(name,cb)=>listeners[name]=cb
};
vm.runInNewContext(sw,{self,caches:{match:()=>{cacheCalls.push('cache');return Promise.resolve('stale')}},
 URL,fetch:(request,opts)=>{fetchCalls.push({request,opts});return Promise.resolve({ok:true,status:200});},
 Response:{error:()=>null}});
async function verify(url){
 let pending=null;
 const event={request:{method:'GET',url},respondWith:q=>pending=q};
 listeners.fetch(event);
 assert.ok(pending,'network-only route intercepts exhibition JSON');
 await pending;
 assert.equal(fetchCalls.at(-1).opts.cache,'no-store');
 assert.equal(cacheCalls.length,0,'should NOT fall back to a stale copy of JSON');
}
(async()=>{
 await verify('https://example.test/data/exhibition/status-latest.json');
 await verify('https://example.test/data/exhibition/2026-10-27.json');
 await verify('https://example.test/data/live/latest.json');
 console.log('Exhibition heartbeat / automatic research reload / network-only JSON / v1.3 label checks PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
