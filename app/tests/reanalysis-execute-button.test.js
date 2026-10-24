/* iPhone-like delegated click flow: direct CSV -> inputs -> execute -> result.
 * Regression: before this fix a successful direct fetch did NOT feed the model.
 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const fixture=require('./fixtures/frozen-official-data.js');
const frozen=JSON.parse(JSON.stringify(fixture));
const handlers={},nodes=new Map();
function el(id){
 if(!nodes.has(id))nodes.set(id,{
  innerHTML:'',textContent:'',value:'',dataset:{},classList:{add(){},remove(){},toggle(){}},
  addEventListener(){},setAttribute(){},removeAttribute(){}
 });
 return nodes.get(id);
}
const doc={hidden:false,getElementById:el,addEventListener:(type,fn)=>(handlers[type]||=[]).push(fn),
 querySelectorAll(sel){
  if(sel!=='[data-recalc-lane][data-recalc-metric]')return [];
  const found=[];
  for(const m of el('main').innerHTML.matchAll(/data-recalc-lane="(\d+)" data-recalc-metric="([^"]+)" value="([^"]*)"/g))
   found.push({dataset:{recalcLane:m[1],recalcMetric:m[2]},value:m[3]});
  return found;
 }};
const win={scrollTo(){}};
const store={getItem(){return null},setItem(){},removeItem(){}};
let state={state:'idle',message:'未取得'};
let requests=0,forceRequests=0;
const preview={date:frozen.event_date,source_observed_jst:'2026-10-22T03:00:00+09:00',values:{}};
for(let lane=1;lane<=6;lane++)preview.values[lane]={
 lap_time:36.4+.2*lane,turn_time:5.3+.09*lane,straight_time:7.0+.08*lane
};
win.BoatOriginalExhibitionDirect={
 status:()=>state,get:()=>state.state==='ready'?state.data:null,
 refresh:async(_r,_d,opts)=>{
  requests++;if(opts.force)forceRequests++;
  state={state:'ready',data:preview,count:18,message:'直前CSVから 18/18項目を取得'};
  return state;
 }
};
win.BoatExhibitionAudit={metricsFor:()=>null,load:async()=>{},panel:()=>''};
const env=vm.createContext({window:win,document:doc,localStorage:store,
 fetch:async()=>({ok:true,json:async()=>JSON.parse(JSON.stringify(frozen))}),
 navigator:{},location:{protocol:'file:'},console,Intl,Date,Number,Math,
 Blob,URL,setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync('app/forecast-reanalysis.js','utf8'),env);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),env);
function click(selector,dataset){
 for(const listener of handlers.click||[])
  listener({target:{closest:q=>q===selector?{dataset}:null}});
}
async function tick(){await new Promise(resolve=>setTimeout(resolve,20));}
async function main(){
 await tick();
 const race=frozen.forecast_races[0];
 const original=JSON.stringify(race);
 click('[data-race]',{race:race.venue+'|'+race.race});
 click('[data-action]',{action:'analyze-saved-race'});
 await tick();
 assert.ok(requests>=1,'opening reanalysis must check direct CSV');
 assert.match(el('main').innerHTML,/直接CSV 18件/);
 assert.match(el('main').innerHTML,/再予想を実行/);
 click('[data-action]',{action:'refresh-original-exhibition'});
 await tick();
 assert.equal(forceRequests,1,'manual acquisition button invokes direct fetch');
 click('[data-action]',{action:'run-reanalysis'});
 assert.match(el('main').innerHTML,/再予想を実行しました/);
 assert.match(el('main').innerHTML,/展開を再評価した3連単/);
 assert.match(el('main').innerHTML,/1周タイム/);
 assert.match(el('main').innerHTML,/回り足タイム/);
 assert.match(el('main').innerHTML,/直線タイム/);
 assert.match(el('main').innerHTML,/仮想合計 <strong>50,000円/);
 assert.equal(JSON.stringify(race),original,'running must not mutate frozen bets');
 // Test direct data actually wins over the older research archive.
 const auto=win.BoatReanalysis.autoExtra(race,{values:{1:{lap_time:39.9}}},preview);
 assert.equal(auto.values[1].lap_time,preview.values[1].lap_time);
 assert.equal(auto.sources.direct,18);
 assert.equal(auto.sources.research,0);
 const sw=fs.readFileSync('app/service-worker.js','utf8');
 assert.match(sw,/url\.pathname\.includes\('\/data\/live\/'\)/);
 assert.match(sw,/cache:'no-store'/);
 assert.ok(!sw.includes("cached||caches.match('./index.html')"),
  'JSON requests must not receive fallback HTML');
 console.log('BOAT LAB execution button and direct exhibition integration: PASS');
}
main().catch(err=>{console.error(err);process.exitCode=1});
