/* BOAT LAB result evidence widget: simulated phone interactions (offline). */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const data=require('./fixtures/frozen-official-data.js');
const fixture=JSON.parse(JSON.stringify(data));
const target=fixture.forecast_races.find(r=>!fixture.official_results[fixture.event_date+'|'+r.venue+'|'+r.race]);
const targetKey=fixture.event_date+'|'+target.venue+'|'+target.race;
delete fixture.official_results[targetKey];
delete fixture.settlement_alerts[targetKey];

const nodes=new Map();
function getElement(id){
 if(!nodes.has(id))nodes.set(id,{
   innerHTML:'',textContent:'',value:'',files:[],dataset:{},
   classList:{add(){},remove(){},toggle(){}},
   addEventListener(){},setAttribute(){},removeAttribute(){}
 });
 return nodes.get(id);
}
const handlers={};
const document={hidden:false,getElementById:getElement,querySelectorAll:()=>[],
 addEventListener:(name,fn)=>{(handlers[name]||=[]).push(fn)}};
const stored=new Map(),writes=[];
const localStorage={
 getItem:k=>stored.get(k)||null,
 setItem:(k,v)=>{stored.set(k,v);writes.push({k,v})},
 removeItem:k=>stored.delete(k)
};
class LocalURL extends URL {}
LocalURL.createObjectURL=()=> 'blob:https://boatlab.test/preview';
LocalURL.revokeObjectURL=()=>{};
const window={scrollTo(){},Tesseract:{
 createWorker:async()=>({
   recognize:async()=>({data:{text:'3連単 2-1-3 ￥2,460'}}),
   terminate:async()=>{}
 })
}};
const fetch=async()=>({ok:true,json:async()=>fixture});
const ctx=vm.createContext({window,document,localStorage,fetch,URL:LocalURL,navigator:{},
 location:{protocol:'file:'},setTimeout,clearTimeout,console,Blob,Date,Intl});
vm.runInContext(fs.readFileSync('app/result-reader.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),ctx);
const delay=ms=>new Promise(r=>setTimeout(r,ms));
function click(selector,value){
 for(const fn of handlers.click||[])fn({target:{closest:s=>s===selector?{dataset:value}:null}});
}
function change(selector,fields){
 const e={target:{...fields,matches:s=>s===selector}};
 for(const fn of handlers.change||[])fn(e);
}
function submit(){
 let prevented=false;
 for(const fn of handlers.submit||[])fn({target:{id:'result-form'},preventDefault(){prevented=true}});
 assert.equal(prevented,true);
}
async function main(){
 await delay(60);
 click('[data-view]',{view:'results'});
 // Select a known race with no official result; form confirmation must be allowed.
 change('#result-venue',{value:target.venue});
 change('#result-race',{value:String(target.race)});
 const main=getElement('main');
 assert.match(main.innerHTML,/画像・URLから結果を読み取る/);
 assert.match(main.innerHTML,/id="result-image-file"/);
 assert.match(main.innerHTML,/id="result-official-url"/);
 assert.match(main.innerHTML,/画像を読み取る/);
 assert.match(main.innerHTML,/URLで照合/);

 const image={name:'official-result.png',type:'image/png',size:12000};
 change('#result-image-file',{files:[image]});
 assert.match(main.innerHTML,/official-result.png/);
 assert.match(main.innerHTML,/blob:https:\/\/boatlab.test\/preview/);
 assert.equal(window.BoatResultReader.snapshot().fileName,'official-result.png');
 click('[data-action]',{action:'read-result-image'});
 await delay(50);
 assert.match(main.innerHTML,/OCRで読み取った候補/);
 assert.match(main.innerHTML,/2-1-3/);
 assert.match(main.innerHTML,/2,460円/);
 assert.equal(writes.filter(x=>x.k.includes('results')).length,0,'OCR must not auto-save any race');
 click('[data-action]',{action:'apply-result-read'});
 assert.equal(getElement('finish-0').value,'2');
 assert.equal(getElement('finish-1').value,'1');
 assert.equal(getElement('finish-2').value,'3');
 assert.equal(getElement('payout').value,'2460');
 assert.equal(writes.filter(x=>x.k.includes('results')).length,0,'Form prefilling must not auto-save');
 submit();
 const manual=JSON.parse(stored.get('boatlab-results-v1'));
 assert.equal(manual[targetKey].finish,'2-1-3');
 assert.equal(manual[targetKey].payout_per_100,2460);
 assert.equal(manual[targetKey].source,'manual');
 assert.equal(window.BoatLab.getData().official_results[targetKey],undefined);
 // Same-day official URL without a published result never invents the outcome.
 getElement('result-official-url').value='https://www.boatrace.jp/owpc/pc/race/pay?hd='+fixture.event_date.replaceAll('-','');
 click('[data-action]',{action:'read-result-url'});
 assert.match(main.innerHTML,/まだありません/);
 // Select a verified official race. URL lookup confirms it, but never writes over it.
 const verified=fixture.forecast_races.find(r=>fixture.official_results[fixture.event_date+'|'+r.venue+'|'+r.race]?.verified&&!fixture.settlement_alerts?.[fixture.event_date+'|'+r.venue+'|'+r.race]);
 assert.ok(verified);
 change('#result-venue',{value:verified.venue});
 change('#result-race',{value:String(verified.race)});
 const officialURL='https://www.boatrace.jp/owpc/pc/race/pay?hd='+fixture.event_date.replaceAll('-','');
 getElement('result-official-url').value=officialURL;
 const before=writes.length;
 click('[data-action]',{action:'read-result-url'});
 assert.match(main.innerHTML,/公開済み公式結果を確認/);
 assert.equal(writes.length,before,'Official URL lookup is read-only');
 assert.equal(window.BoatResultReader.snapshot().candidate.status,'official_verified');
 const verifiedKey=fixture.event_date+'|'+verified.venue+'|'+verified.race;
 assert.equal(window.BoatResultReader.snapshot().candidate.finish,fixture.official_results[verifiedKey].finish);
 assert.ok(!main.innerHTML.includes('候補を入力フォームに反映'));
 console.log('BOAT LAB mobile result image+URL reconciliation integration: PASS');
}
main().catch(e=>{console.error(e);process.exitCode=1});
