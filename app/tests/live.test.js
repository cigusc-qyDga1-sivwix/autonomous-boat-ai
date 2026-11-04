const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const raw=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
assert.equal(raw.mode,'auto-live');
assert.ok(raw.forecast_races.length>0);
assert.ok(raw.forecast_races.length<=288);
for(const r of raw.forecast_races){
  assert.ok(r.sha256 && r.frozen_at_utc);
  // Old saved v1.5/v1.8/v1.9 forecasts are immutable and may contain
  // 120 tickets. That is historical READ compatibility, not a new policy.
  // From v2.0 onward, the main is forbidden to issue >24 tickets.
  const historicWide=new Set([
    'four-factor-v1.5-point-free-untrained',
    'four-factor-v1.8-adaptive-points-primary-untrained',
    'four-factor-v1.9-aligned-primary-untrained'
  ]).has(r.model_version);
  const conservative=r.model_version==='four-factor-v2.0-justified-points-primary-untrained';
  const expanded=Date.parse(r.frozen_at_utc)>=Date.parse('2026-10-29T00:00:00+09:00');
  const maximum=conservative?24:historicWide?120:expanded?20:12;
  assert.ok(r.bets.length>=(historicWide?1:4)&&r.bets.length<=maximum);
  if(conservative){
    const policy=r.interaction_primary?.point_policy;
    assert.ok(policy&&policy.max_issued_ticket_points===24);
    assert.ok(policy.selected_point_count<=24);
    assert.ok(r.bets.every(b=>b.virtual_yen%1000===0&&b.virtual_yen>=1000));
  }
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

