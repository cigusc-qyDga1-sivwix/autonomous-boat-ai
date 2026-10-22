const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const m={window:{}};
vm.runInNewContext(fs.readFileSync('app/boaters-reference.js','utf8'),m);
const refs=m.window.BoatExternalReference;
assert.equal(refs.linkFor('徳山','2026-10-22',10),
  'https://boaters-boatrace.com/race/tokuyama/2026-10-22/10R/race-detail');
assert.equal(refs.predictionLinkFor('徳山','2026-10-22',10),
  'https://boaters-boatrace.com/race/tokuyama/2026-10-22/10R/race-prediction');
assert.equal(refs.linkFor('鳴門','2026-10-22',12),
  'https://boaters-boatrace.com/race/naruto/2026-10-22/12R/race-detail');
assert.equal(refs.linkFor('架空場','2026-10-22',1),'https://boaters-boatrace.com/race');
assert.equal(refs.linkFor('徳山','invalid',1),'https://boaters-boatrace.com/race');
assert.equal(refs.linkFor('徳山','2026-10-22',13),'https://boaters-boatrace.com/race');
const data=JSON.parse(fs.readFileSync('app/data/2026-10-22.json','utf8'));
const original=JSON.stringify(data.forecast_races[0]);
const localHTML=refs.analysisHTML(data.forecast_races[0]);
assert.match(localHTML,/BOAT LAB保存記録のみ/);
assert.match(localHTML,/全国勝率/);
assert.match(localHTML,/展示タイム/);
assert.match(localHTML,/モーター2連対率/);
assert.match(localHTML,/BOATERSのデータを取得した結果ではありません/);
assert.equal(JSON.stringify(data.forecast_races[0]),original,'read-only local analysis must not edit forecast');

// Integration: the selected race gets a usable link; user-click reveals local analysis
// and never sends a network request to BOATERS.
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast']){
  elements.set(id,{innerHTML:'',textContent:'',classList:{add(){},remove(){},toggle(){}},
    addEventListener(){},setAttribute(){},removeAttribute(){}});
}
const listeners={};
const document={hidden:false,getElementById:id=>elements.get(id),querySelectorAll:()=>[],
  addEventListener:(kind,listener)=>{(listeners[kind]||=[]).push(listener)}};
let fetchCount=0;
const window={scrollTo(){}};
const ctx=vm.createContext({
  window,document,
  localStorage:{getItem(){return null},setItem(){},removeItem(){}},
  fetch:async url=>{
    assert.ok(!String(url).includes('boaters-boatrace.com'),'must not scrape BOATERS');
    fetchCount++;
    if(String(url).includes('live/latest.json'))throw new Error('fixture offline');
    return {ok:true,json:async()=>data};
  },
  navigator:{},location:{protocol:'file:'},setTimeout,clearTimeout,console,Blob,URL,Intl,Date,
});
vm.runInContext(fs.readFileSync('app/boaters-reference.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/venue-board.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),ctx);
function click(selector,value){
  const node={dataset:value};
  for(const fn of listeners.click||[])fn({target:{closest:s=>s===selector?node:null}});
}
setTimeout(()=>{
  const r=data.forecast_races[0];
  click('[data-race]',{race:r.venue+'|'+r.race});
  const detail=elements.get('main').innerHTML;
  assert.match(detail,/BOATERS レース情報/);
  assert.match(detail,/BOATERS AI予想/);
  assert.match(detail,/利用規約/);
  assert.match(detail,/取得済みデータを分析/);
  const expected=refs.linkFor(r.venue,data.event_date,r.race);
  assert.ok(detail.includes(expected));
  assert.ok(!detail.includes('BOAT LAB保存記録のみ'));
  click('[data-action]',{action:'analyze-saved-race'});
  const expanded=elements.get('main').innerHTML;
  assert.match(expanded,/BOAT LAB保存記録のみ/);
  assert.match(expanded,/全国勝率 上位/);
  assert.equal(fetchCount,2,'no network requests for analysis (only app data)');
  console.log('BOAT LAB BOATERS-reference tests: PASS');
},120);
