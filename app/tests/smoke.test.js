const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const data=JSON.parse(fs.readFileSync('app/data/2026-10-22.json','utf8'));
assert.equal(data.forecast_races.length,24);
assert.equal(data.forecast_races.filter(x=>x.classification==='WATCH').length,14);
assert.equal(data.forecast_races.filter(x=>x.classification==='SKIP').length,10);
for(const r of data.forecast_races){
  assert.equal(r.bets.length,8);
  assert.equal(r.bets.reduce((n,b)=>n+b.virtual_yen,0),50000);
  assert.equal(new Set(r.bets.map(x=>x.combination)).size,8);
}
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast'])elements.set(id,{innerHTML:'',textContent:'',classList:{add:()=>{},remove:()=>{},toggle:()=>{}},addEventListener:()=>{},setAttribute:()=>{},removeAttribute:()=>{}});
const listeners={};
const document={getElementById:id=>elements.get(id),querySelectorAll:()=>[],addEventListener:(name,fn)=>{(listeners[name]||=[]).push(fn);}};
const storage=new Map();
const localStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
const window={scrollTo:()=>{}};
vm.runInNewContext(fs.readFileSync('app/app.js','utf8'),{window,document,localStorage,fetch:async()=>({ok:true,json:async()=>data}),navigator:{},location:{protocol:'file:'},clearTimeout,setTimeout,console,Blob,URL});
setTimeout(()=>{
  assert.equal(window.BoatLab.getData().forecast_races.length,24);
  assert.match(elements.get('main').innerHTML,/AI予想ダッシュボード/);
  assert.equal(window.BoatLab.stats(data.forecast_races).examined,0);
  assert.throws(()=>window.BoatLab.validate({...data,forecast_races:[data.forecast_races[0],data.forecast_races[0]]}));
  console.log('BOAT LAB smoke tests: PASS');
},100);
