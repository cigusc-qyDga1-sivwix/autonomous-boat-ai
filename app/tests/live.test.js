const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const raw=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
assert.equal(raw.mode,'auto-live');
assert.ok(raw.forecast_races.length>0);
assert.ok(raw.forecast_races.length<=288);
for(const r of raw.forecast_races){
  assert.ok(r.sha256 && r.frozen_at_utc);
  assert.ok(r.bets.length>=4&&r.bets.length<=12);
  if(r.point_count!==undefined)assert.equal(r.point_count,r.bets.length);
  assert.equal(r.bets.reduce((a,b)=>a+b.virtual_yen,0),50000);
  assert.ok(['baseline','exhibition'].includes(r.phase));
}
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast'])elements.set(id,{
  innerHTML:'',textContent:'',classList:{add:()=>{},remove:()=>{},toggle:()=>{}},
  addEventListener:()=>{},setAttribute:()=>{},removeAttribute:()=>{}
});
const document={getElementById:id=>elements.get(id),querySelectorAll:()=>[],
  addEventListener:()=>{},hidden:false};
const storage=new Map();
const localStorage={getItem:key=>storage.get(key)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
const window={scrollTo:()=>{}};
const fetch=async url=>{
  if(String(url).includes('live/latest.json'))return {ok:true,json:async()=>raw};
  throw new Error('unexpected '+url);
};
vm.runInNewContext(fs.readFileSync('app/app.js','utf8'),{
  window,document,localStorage,fetch,navigator:{},location:{protocol:'file:'},
  clearTimeout,setTimeout,console,Blob,URL,Intl,Date
});
setTimeout(()=>{
  const data=window.BoatLab.getData();
  assert.equal(data.mode,'auto-live');
  assert.equal(data.forecast_races.length,raw.forecast_races.length);
  assert.match(elements.get('main').innerHTML,/AI予想ダッシュボード/);
  assert.match(elements.get('main').innerHTML,/全国開催|自動取得/);
  const officialEntries=Object.entries(data.official_results||{});
  const verifiedCount=data.forecast_races.filter(r=>{
    const k=data.event_date+'|'+r.venue+'|'+r.race;
    const p=data.official_results?.[k];
    return p?.source==='boatrace_official_pay'&&p.verified===true&&
      (!p.snapshot_sha256||p.snapshot_sha256===r.sha256)&&!data.settlement_alerts?.[k];
  }).length;
  assert.equal(window.BoatLab.officialStats(data.forecast_races).count,verifiedCount);
  assert.equal(window.BoatLab.stats(data.forecast_races).examined,verifiedCount);
  assert.ok(officialEntries.length>=verifiedCount);
  console.log('BOAT LAB nationwide live app smoke: PASS');
},100);
