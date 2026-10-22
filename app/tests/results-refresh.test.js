/* Result refresh screen: forced fetch, status, up-to-date metrics and resilience. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const saved=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const deep=x=>JSON.parse(JSON.stringify(x));
const officialEntry=Object.entries(saved.official_results||{}).find(([,v])=>
  v.verified===true && v.source==='boatrace_official_pay');
assert.ok(officialEntry,'Need a real previously verified official result in fixture');
const initial=deep(saved);
delete initial.official_results[officialEntry[0]];
initial.updated_at_utc='2026-10-22T00:00:00+00:00';
const newVersion=deep(saved);
newVersion.updated_at_utc='2026-10-22T07:20:00+00:00';
let response=initial, hold=null, throws=false;
const calls=[],listen={};
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast']){
 elements.set(id,{innerHTML:'',textContent:'',
 classList:{add(){},remove(){},toggle(){}},
 addEventListener(){},setAttribute(){},removeAttribute(){}});
}
const document={hidden:false,
 getElementById:id=>elements.get(id),
 querySelectorAll:()=>[],
 addEventListener:(name,cb)=>{(listen[name]||=[]).push(cb)}
};
const window={scrollTo(){}};
const localStorage={getItem(){return null},setItem(){},removeItem(){}};
const fetch=async(url,opts)=>{
 calls.push({url,opts});
 if(throws)throw Error('Offline');
 if(hold)await new Promise(r=>{hold(r)});
 return {ok:true,json:async()=>deep(response)};
};
const ctx=vm.createContext({window,document,localStorage,fetch,navigator:{},
 location:{protocol:'file:'},console,setTimeout,clearTimeout,Blob,URL,Intl,Date});
vm.runInContext(fs.readFileSync('app/app.js','utf8'),ctx);
function navResults(){
 for(const cb of listen.click||[])cb({
  target:{closest:selector=>selector==='[data-view]'?{dataset:{view:'results'}}:null}
 });
}
function pressResultsRefresh(){
 for(const cb of listen.click||[])cb({
  target:{closest:selector=>selector==='[data-action]'?
    {dataset:{action:'refresh-official-results'}}:null}
 });
}
async function main(){
 await new Promise(r=>setTimeout(r,70));
 navResults();
 const ui=elements.get('main');
 assert.match(ui.innerHTML,/結果を更新/);
 assert.match(ui.innerHTML,/公式ページ確認/);
 assert.match(ui.innerHTML,/公開済み結果を再読み込み/);
 assert.match(ui.innerHTML,/BOATRACE 本日の払戻金一覧/);
 assert.match(ui.innerHTML,/公式照合/);
 assert.ok(window.BoatLab.officialStats(window.BoatLab.getData().forecast_races).count<
   Object.keys(saved.official_results||{}).length);

 response=newVersion;
 // Race in-flight: mark busy; don't allow an overlapping manual refresh.
 let resolvePending;
 hold=(resolve)=>{resolvePending=resolve};
 const update=window.BoatLab.refreshOfficialResults();
 assert.match(ui.innerHTML,/更新を確認中/);
 assert.match(ui.innerHTML,/disabled aria-busy="true"/);
 await Promise.resolve();await Promise.resolve();
 assert.equal(typeof resolvePending,'function');
 const countBefore=calls.length;
 await window.BoatLab.refreshOfficialResults();
 assert.equal(calls.length,countBefore,'duplicate clicks must not start another request');
 hold=null;
 resolvePending();
 await update;
 assert.match(ui.innerHTML,/新たに1Rの公式結果を確認しました/);
 assert.equal(window.BoatLab.officialStats(window.BoatLab.getData().forecast_races).count,
   Object.keys(saved.official_results).length);
 const value=window.BoatLab.getData().official_results[officialEntry[0]];
 assert.equal(value.finish,officialEntry[1].finish);
 assert.ok(calls.every(x=>x.opts?.cache==='no-store'));
 assert.ok(calls.every(x=>String(x.url).includes('refresh=')));

 const reqCount=calls.length;
 pressResultsRefresh();
 await new Promise(r=>setTimeout(r,30));
 assert.equal(calls.length,reqCount+1,'button must really refetch data');
 assert.match(ui.innerHTML,/新しい公式照合結果はまだありません/);

 throws=true;
 await window.BoatLab.refreshOfficialResults();
 assert.match(ui.innerHTML,/データを取得できませんでした/);
 assert.match(ui.innerHTML,/is-error/);
 assert.equal(window.BoatLab.getData().official_results[officialEntry[0]].finish,
   officialEntry[1].finish,'failed reload must preserve current verified results');
 throws=false;

 const stale=deep(saved);stale.event_date='2026-10-21';
 response=stale;
 await window.BoatLab.refreshOfficialResults();
 assert.match(ui.innerHTML,/より古いため/);
 assert.equal(window.BoatLab.getData().event_date,saved.event_date);
 console.log('BOAT LAB manual official result refresh tests: PASS');
}
main().catch(e=>{console.error(e);process.exitCode=1});
