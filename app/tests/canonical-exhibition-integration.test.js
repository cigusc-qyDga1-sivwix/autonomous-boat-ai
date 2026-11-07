'use strict';
// Full in-app integration: GitHub Pages may serve an older JSON snapshot;
// canonical main's newer immutable exhibition forecast must be displayed.
// Do not mutate the saved source or silently replace a later fixed forecast.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const deep=x=>JSON.parse(JSON.stringify(x));

const latest=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const raw=deep(latest);
const old=deep(latest);
old.updated_at_utc=new Date(Date.parse(raw.updated_at_utc)-6*60000).toISOString();
const exhibit=old.forecast_races.find(r=>r.phase==='exhibition');
assert.ok(exhibit,'test requires at least one exhibition snapshot');
exhibit.phase='baseline';
const verified=raw.forecast_races.filter(r=>r.phase==='exhibition').length;
const manifest={
 schema:'boatlabs.forecast_capture.v1',status:'completed',
 event_date:raw.event_date,forecast_races:raw.forecast_races.length,
 final_exhibition_verified_races:verified,
 captured_at_utc:raw.updated_at_utc,
 completed_at_utc:new Date(Date.parse(raw.updated_at_utc)+3000).toISOString()
};
const calls=[],listeners={},intervals=[];
let pagesOffline=false,upstreamOffline=false,researchReads=0;
const fetch=async(url,options)=>{
 url=String(url);
 calls.push({url,options});
 if(url.includes('raw.githubusercontent.com')){
  if(upstreamOffline)throw Error('CORS blocked');
  return {ok:true,json:async()=>deep(url.includes('forecast-sync')?manifest:raw)};
 }
 if(url.includes('/data/live/latest.json')){
  if(pagesOffline)throw Error('Pages offline');
  return {ok:true,json:async()=>deep(old)};
 }
 if(url.includes('/data/exhibition/')){
  researchReads++;
  return {ok:true,json:async()=>({})};
 }
 throw Error('Unexpected network URL '+url);
};
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast']){
 elements.set(id,{innerHTML:'',textContent:'',
  classList:{add(){},remove(){},toggle(){}},
  addEventListener(){},setAttribute(){},removeAttribute(){}});
}
const document={hidden:false,
 getElementById:id=>elements.get(id),querySelectorAll:()=>[],
 addEventListener:(name,cb)=>{(listeners[name]||=[]).push(cb)}
};
const window={scrollTo(){},fetch,
 BoatExhibitionAudit:{load:async()=>{researchReads++},banner:()=>''}};
const storage=new Map();
const localStorage={getItem:k=>storage.get(k)||null,
  setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
const ctx=vm.createContext({window,document,fetch,localStorage,
 navigator:{},location:{protocol:'file:'},console,
 Intl,Date,setTimeout,clearTimeout,setInterval:(cb,ms)=>{intervals.push({cb,ms});},Blob,URL});
vm.runInContext(fs.readFileSync('app/canonical-exhibition-feed.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),ctx);
async function main(){
 await new Promise(resolve=>setTimeout(resolve,160));
 const installed=window.BoatLab.getData();
 assert.equal(installed.updated_at_utc,raw.updated_at_utc,
  'auto sync should adopt newer GitHub main while Pages still serves old');
 assert.equal(installed.forecast_races.filter(r=>r.phase==='exhibition').length,verified);
 assert.equal(window.BoatCanonicalExhibitionFeed.status().lastStatus,'newer');
 assert.ok(calls.some(x=>x.url.includes('raw.githubusercontent.com')));
 assert.ok(calls.some(x=>x.url.includes('/data/live/latest.json?refresh=')));
 assert.ok(intervals.some(x=>x.cb.name==='pollCanonicalForecast'&&x.ms===60000));
 const immutable=JSON.stringify(installed.forecast_races);
 for(const cb of listeners.click||[])cb({target:{
  closest:selector=>selector==='[data-action]'?
   {dataset:{action:'refresh-exhibition'}}:null
 }});
 await new Promise(resolve=>setTimeout(resolve,120));
 assert.equal(window.BoatLab.getData().updated_at_utc,raw.updated_at_utc,
  'manual Pages refresh must not roll back more recent canonical forecasts');
 assert.equal(JSON.stringify(window.BoatLab.getData().forecast_races),immutable,
  'once published, historical official tickets stay bit-for-bit identical');
 assert.match(elements.get('toast').textContent,/最新予想を確認|公開サイトのデータを確認/);
 assert.ok(researchReads>0);
 pagesOffline=true;upstreamOffline=true;
 for(const cb of listeners.click||[])cb({target:{
  closest:selector=>selector==='[data-action]'?
   {dataset:{action:'refresh-exhibition'}}:null
 }});
 await new Promise(resolve=>setTimeout(resolve,120));
 assert.match(elements.get('toast').textContent,/接続できなかった/);
 assert.equal(JSON.stringify(window.BoatLab.getData().forecast_races),immutable,
  'failure from both sources must preserve frozen predictions');
 console.log('Canonical upstream live exhibition update, manual retry, anti-rollback and offline preservation PASS');
}
main().catch(e=>{console.error(e);process.exitCode=1});
