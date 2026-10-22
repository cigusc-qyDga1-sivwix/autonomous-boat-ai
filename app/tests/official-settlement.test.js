const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const data=require('./fixtures/frozen-official-data.js');
const verifiedRace=data.forecast_races.find(r=>{
  const p=data.official_results?.[data.event_date+'|'+r.venue+'|'+r.race];
  return p?.verified===true && p?.source==='boatrace_official_pay' &&
    (!p.snapshot_sha256 || p.snapshot_sha256===r.sha256);
});
assert.ok(verifiedRace,'At least one official result should exist in the checked-in fixture');
const key=data.event_date+'|'+verifiedRace.venue+'|'+verifiedRace.race;
const official=data.official_results[key];
const fakeManual={[key]:{finish:'6-5-4',payout_per_100:120,source:'manual'}};
const localStorage={
  getItem:k=>k==='boatlab-results-v1'?JSON.stringify(fakeManual):null,
  setItem(){},removeItem(){}
};
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast'])elements.set(id,{
  innerHTML:'',textContent:'',classList:{add(){},remove(){},toggle(){}},
  addEventListener(){},setAttribute(){},removeAttribute(){}
});
const listeners={};
const document={getElementById:id=>elements.get(id),querySelectorAll:()=>[],
  addEventListener:(name,fn)=>(listeners[name]||=[]).push(fn)};
const window={scrollTo(){}};
vm.runInNewContext(fs.readFileSync('app/app.js','utf8'),{
  window,document,localStorage,fetch:async()=>({ok:true,json:async()=>data}),
  navigator:{},location:{protocol:'file:'},setTimeout,clearTimeout,console,Blob,URL,Intl,Date
});
setTimeout(()=>{
  const api=window.BoatLab;
  assert.equal(api.officialFor(verifiedRace).finish,official.finish);
  assert.equal(api.compute(verifiedRace).record.finish,official.finish,'official must supersede wrong manual input');
  assert.equal(api.compute(verifiedRace).payout,official.virtual_payout);
  const summary=api.officialStats(data.forecast_races);
  assert.ok(summary.count>=1);
  assert.equal(summary.count,Object.values(data.official_results).filter(r=>r.source==='boatrace_official_pay'&&r.verified===true).length);
  for(const click of listeners.click||[]){
    click({target:{closest:s=>s==='[data-view]'?{dataset:{view:'results'}}:null}});
  }
  assert.match(elements.get('main').innerHTML,/公式照合/);
  assert.match(elements.get('main').innerHTML,/BOATRACE/);
  assert.match(elements.get('main').innerHTML,/払戻金一覧/);
  assert.match(elements.get('main').innerHTML,/返還/);
  for(const click of listeners.click||[]){
    click({target:{closest:s=>s==='[data-view]'?{dataset:{view:'analysis'}}:null}});
  }
  const diagnosis=elements.get('main').innerHTML;
  assert.match(diagnosis,/予想AIの弱点診断/);
  assert.match(diagnosis,/2着の組合せ抜け/);
  assert.match(diagnosis,/1・2着一致→3着抜け/);
  assert.match(diagnosis,/買い目筆頭が①頭/);
  assert.match(diagnosis,/公式照合済み/);

  console.log('BOAT LAB official settlement UI tests: PASS');
},150);
