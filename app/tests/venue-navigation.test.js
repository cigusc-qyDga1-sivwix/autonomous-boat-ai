const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const data=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast']) {
  elements.set(id,{innerHTML:'',textContent:'',classList:{add(){},remove(){},toggle(){}},
    addEventListener(){},setAttribute(){},removeAttribute(){}});
}
const listeners={};
const document={hidden:false,getElementById:id=>elements.get(id),querySelectorAll:()=>[],
  addEventListener:(name,cb)=>{(listeners[name]||=[]).push(cb)}};
const storage=new Map();
const localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
const window={scrollTo(){}};
const context=vm.createContext({window,document,localStorage,fetch:async()=>({ok:true,json:async()=>data}),
  navigator:{},location:{protocol:'file:'},setTimeout,clearTimeout,console,Blob,URL,Date,Intl});
vm.runInContext(fs.readFileSync('app/race-visual.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/venue-board.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),context);
function click(selector,node){
  const target={closest:(s)=>s===selector?node:null};
  for(const cb of listeners.click||[])cb({target});
}
setTimeout(()=>{
  const main=elements.get('main');
  assert.match(main.innerHTML,/今日の開催一覧/);
  assert.equal((main.innerHTML.match(/class="venue-card venue-theme-/g)||[]).length,24);
  const venue=data.forecast_races[0].venue;
  click('[data-open-venue]',{dataset:{openVenue:venue},disabled:false});
  assert.match(main.innerHTML,/全12R/);
  assert.equal((main.innerHTML.match(/class="venue-race(?: venue-race-[a-z]+)?"/g)||[]).length,12);
  const selected=data.forecast_races[0];
  click('[data-race]',{dataset:{race:venue+'|'+selected.race}});
  assert.match(main.innerHTML,/3連単フォーメーション/);
  assert.match(main.innerHTML,/🚤 出走表/);
  assert.match(main.innerHTML,/全国勝率/);
  assert.match(main.innerHTML,/モーター/);
  assert.match(main.innerHTML,/展開予想アニメ/);
  assert.match(main.innerHTML,/第1ターンマーク/);
  assert.equal((main.innerHTML.match(/data-sim-boat="/g)||[]).length,6);
  click('[data-action]',{dataset:{action:'back-overview'}});
  assert.match(main.innerHTML,/今日の開催一覧/);
  click('[data-favorite-venue]',{dataset:{favoriteVenue:'桐生'}});
  assert.ok(JSON.parse(storage.get('boatlab-favorite-venues-v1')).includes('桐生'));
  click('[data-venue-filter]',{dataset:{venueFilter:'favorite'}});
  assert.match(main.innerHTML,/お気に入り/);
  console.log('BOAT LAB venue navigation integration tests: PASS');
},130);
