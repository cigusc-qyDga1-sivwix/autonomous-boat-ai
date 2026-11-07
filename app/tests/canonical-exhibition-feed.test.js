'use strict';
// Canonical mirror is read-only and never allows a lagging Pages artifact to
// promote an older or research-only snapshot as formal.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('app/canonical-exhibition-feed.js','utf8');
const context=vm.createContext({window:{},Date});
vm.runInContext(source,context);
const feed=context.window.BoatCanonicalExhibitionFeed;
const deep=x=>JSON.parse(JSON.stringify(x));
const manifest={
 schema:'boatlabs.forecast_capture.v1',
 status:'completed',event_date:'2026-11-07',
 captured_at_utc:'2026-11-07T02:09:56.733595+00:00',
 completed_at_utc:'2026-11-07T02:10:03.570740+00:00',
 final_exhibition_verified_races:2,forecast_races:2
};
const current={
 event_date:'2026-11-07',updated_at_utc:'2026-11-07T02:02:01+00:00',
 mode:'auto-live',forecast_races:[{venue:'多摩川',race:1,phase:'baseline'}]
};
const latest={
 mode:'auto-live',event_date:'2026-11-07',
 updated_at_utc:'2026-11-07T02:09:56.733595+00:00',
 forecast_races:[{venue:'多摩川',race:1,phase:'exhibition'},
                 {venue:'住之江',race:2,phase:'exhibition'}]
};
function transport({m=manifest,l=latest,failManifest=false,failLatest=false}={}){
 const urls=[],opts=[];
 const fetcher=async(url,opt)=>{
  urls.push(String(url));opts.push(opt);
  if(url.includes('forecast-sync')){
   if(failManifest)throw Error('CORS');
   return {ok:true,json:async()=>deep(m)};
  }
  if(url.includes('/latest.json')){
   if(failLatest)throw Error('Offline');
   return {ok:true,json:async()=>deep(l)};
  }
  throw Error('unexpected source');
 };
 return {fetcher,urls,opts};
}
async function run(){
 const original=JSON.stringify(current);
 const tr=transport();
 const result=await feed.check({current,fetcher:tr.fetcher,clock:()=>Date.parse('2026-11-07T02:11:00Z')});
 assert.equal(result.state,'newer');
 assert.equal(result.manifest.final_exhibition_verified_races,2);
 assert.equal(result.payload.forecast_races.length,2);
 assert.equal(tr.urls.length,2);
 assert.ok(tr.urls.every(x=>x.includes('raw.githubusercontent.com/')));
 assert.ok(tr.opts.every(x=>x.cache==='no-store'));
 assert.equal(JSON.stringify(current),original,'transport must not mutate stored predictions');
 assert.equal(feed.status().lastStatus,'newer');
 const same=transport();
 const equal=await feed.check({current:latest,fetcher:same.fetcher});
 assert.equal(equal.state,'same');
 assert.equal(same.urls.length,1,'do not download large raw JSON on same revision');
 const outdated=transport();
 assert.equal((await feed.check({current:{...current,
  event_date:'2026-11-08'},fetcher:outdated.fetcher})).state,'same');
 assert.equal(outdated.urls.length,1,'never replace later day by older main cache');
 const lag=transport({l:{...latest,forecast_races:[latest.forecast_races[0],{
  ...latest.forecast_races[1],phase:'baseline'}]}});
 assert.equal((await feed.check({current,fetcher:lag.fetcher})).state,'not_ready',
   'CDN mismatch must not adopt data as fresh');
 const badTime=transport({l:{...latest,updated_at_utc:'2026-11-07T02:05:00Z'}});
 assert.equal((await feed.check({current,fetcher:badTime.fetcher})).state,'not_ready');
 const unavailable=transport({failManifest:true});
 assert.equal((await feed.check({current,fetcher:unavailable.fetcher})).state,'unavailable');
 assert.equal(unavailable.urls.length,1,'failed upstream must not erase Pages state');
 const noCdn=transport({failLatest:true});
 assert.equal((await feed.check({current,fetcher:noCdn.fetcher})).state,'not_ready');
 const malformed=transport({m:{...manifest,final_exhibition_verified_races:3}});
 assert.equal((await feed.check({current,fetcher:malformed.fetcher})).state,'unavailable');
 const older=transport({m:{...manifest,completed_at_utc:'2026-11-07T01:00:00Z'}});
 assert.equal((await feed.check({current,fetcher:older.fetcher})).state,'unavailable');
 const sourceApp=fs.readFileSync('app/app.js','utf8');
 const audit=fs.readFileSync('app/exhibition-audit.js','utf8');
 const index=fs.readFileSync('app/index.html','utf8');
 const sw=fs.readFileSync('app/service-worker.js','utf8');
 assert.match(sourceApp,/async function pollCanonicalForecast\(\)/);
 assert.match(sourceApp,/async function manualRefreshExhibition\(\)/);
 assert.match(sourceApp,/setInterval\(pollCanonicalForecast,60000\)/);
 assert.match(sourceApp,/case 'refresh-exhibition':void manualRefreshExhibition\(\);break;/);
 assert.match(sourceApp,/if\(incoming.event_date<data.event_date\)return/);
 assert.match(audit,/data-action="refresh-exhibition"/);
 assert.match(index,/canonical-exhibition-feed\.js\?v=20261107-main-source-v1/);
 assert.ok(index.indexOf('canonical-exhibition-feed.js')<index.indexOf('app.js'));
 assert.match(sw,/boat-lab-static-v67/);
 assert.match(sw,/\.\/canonical-exhibition-feed\.js/);
 console.log('Canonical exhibition: newer upstream, stale Pages, mismatch, offline, checksum-freeze guard PASS');
}
run().catch(e=>{console.error(e);process.exitCode=1});
