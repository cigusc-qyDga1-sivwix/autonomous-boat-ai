/* Result page workflow: one-tap race select and filter while keeping frozen data. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const frozen=require('./fixtures/frozen-official-data.js');
const initial=JSON.parse(JSON.stringify(frozen));
const handlers={},nodes=new Map();
function el(id){
 if(!nodes.has(id))nodes.set(id,{
   innerHTML:'',textContent:'',dataset:{},value:'',
   classList:{add(){},remove(){},toggle(){}},
   addEventListener(){},setAttribute(){},removeAttribute(){}
 });
 return nodes.get(id);
}
const doc={hidden:false,getElementById:el,querySelectorAll:()=>[],
 addEventListener:(type,fn)=>(handlers[type]||=[]).push(fn)};
const win={scrollTo(){}};
const store={getItem(){return null},setItem(){},removeItem(){}};
const context=vm.createContext({document:doc,window:win,localStorage:store,
 fetch:async()=>({ok:true,json:async()=>JSON.parse(JSON.stringify(initial))}),
 navigator:{},location:{protocol:'file:'},setTimeout,clearTimeout,
 Date,Intl,Number,Math,console,Blob,URL});
vm.runInContext(fs.readFileSync('app/result-quickboard.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),context);
const click=(selector,dataset)=>{
 for(const handler of handlers.click||[]){
  handler({target:{closest:kind=>kind===selector?{dataset}:null}});
 }
};
async function main(){
 await new Promise(r=>setTimeout(r,85));
 click('[data-view]',{view:'results'});
 const node=el('main');
 assert.match(node.innerHTML,/ワンタップ結果照合/);
 assert.match(node.innerHTML,/data-result-filter="hit"/);
 assert.match(node.innerHTML,/公式未取得は不的中として数えません/);
 const userView=win.BoatLab.getData().forecast_races;
 const before=JSON.stringify(userView);
 const r=userView[userView.length-1];
 click('[data-result-quick]',{resultQuick:r.venue+'|'+r.race});
 assert.match(node.innerHTML,new RegExp('選択中：'+r.venue+' '+r.race+'R'));
 assert.match(node.innerHTML,/結果を更新/);
 click('[data-result-filter]',{resultFilter:'awaiting'});
 assert.match(node.innerHTML,/公式未取得/);
 assert.match(node.innerHTML,/ワンタップ結果照合/);
 click('[data-result-filter]',{resultFilter:'verified'});
 assert.match(node.innerHTML,/公式照合済み/);
 assert.equal(JSON.stringify(win.BoatLab.getData().forecast_races),before);
 assert.ok(win.BoatLab.officialStats(userView).count>=1,
   'verified official fixtures remain independently countable');
 console.log('BOAT LAB integrated one-tap results board / filters: PASS');
}
main().catch(e=>{console.error(e);process.exitCode=1});
