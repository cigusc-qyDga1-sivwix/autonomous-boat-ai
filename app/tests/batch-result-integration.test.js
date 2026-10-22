/* iPhone-style end-to-end batch import: multi-R photo + official daily URL. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const payload=require('./fixtures/frozen-official-data.js');
const data=JSON.parse(JSON.stringify(payload));
const handlers={},nodes=new Map(),store=new Map(),writes=[];
function node(id){
 if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',value:'',files:[],dataset:{},
  classList:{add(){},remove(){},toggle(){}},addEventListener(){},setAttribute(){},removeAttribute(){},
  querySelectorAll(){return bulkDomRows}});
 return nodes.get(id);
}
const document={
 hidden:false,getElementById:node,querySelectorAll:()=>[],
 addEventListener:(t,h)=>{(handlers[t]||=[]).push(h)}
};
class TestURL extends URL{}
TestURL.createObjectURL=()=> 'blob:https://boatlab.test/batchpreview';
TestURL.revokeObjectURL=()=>{};
const photoOCR='鳴門\n2R 1-2-3 ¥1,230\n3R 2-1-3 ¥1,450';
const window={scrollTo(){},Tesseract:{
 createWorker:async()=>({recognize:async()=>({data:{text:photoOCR,blocks:[]}}),terminate:async()=>{}})
}};
const localStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>{store.set(k,v);writes.push(k)},removeItem:k=>store.delete(k)};
let bulkDomRows=[],pdfSnapshot=null;
const fetch=async(url)=>{
 if(String(url).includes('official-pay/'))return {ok:true,json:async()=>pdfSnapshot};
 return {ok:true,json:async()=>data};
};
const ctx=vm.createContext({window,document,URL:TestURL,localStorage,fetch,console,
 location:{protocol:'file:'},navigator:{},setTimeout,clearTimeout,Date,Intl,Blob,
 confirm:()=>true});
for(const file of ['result-reader.js','batch-result-reader.js','app.js'])
 vm.runInContext(fs.readFileSync('app/'+file,'utf8'),ctx);
function click(selector,attrs){
 const target={closest:s=>s===selector?{dataset:attrs}:null};
 for(const cb of handlers.click||[])cb({target});
}
function change(selector,attrs){
 const target={...attrs,matches:s=>s===selector};
 for(const cb of handlers.change||[])cb({target});
}
const delay=ms=>new Promise(r=>setTimeout(r,ms));
function fakeRow(i,r){
 return {dataset:{batchRow:String(i)},querySelector(s){
   if(s==='[data-batch-check]')return {checked:r.checked};
   if(s==='[data-batch-finish]')return {value:r.finish};
   if(s==='[data-batch-pay]')return {value:r.payout_per_100};
   return null;
 }};
}
async function run(){
 await delay(70);
 click('[data-view]',{view:'results'});
 const ui=node('main');
 assert.match(ui.innerHTML,/全レース結果をまとめて照合/);
 assert.match(ui.innerHTML,/id="batch-image"/);
 assert.match(ui.innerHTML,/id="batch-url"/);
 assert.match(ui.innerHTML,/画像を一括読み取り/);
 assert.match(ui.innerHTML,/公式結果をまとめて確認/);
 const image={name:'whole-day.png',type:'image/png',size:45000};
 change('#batch-image',{files:[image]});
 assert.match(ui.innerHTML,/whole-day.png/);
 assert.match(ui.innerHTML,/blob:https:\/\/boatlab.test\/batchpreview/);
 assert.equal(window.BoatBatchReader.snapshot().rows.length,0);
 click('[data-action]',{action:'batch-image-read'});
 await delay(30);
 const snap=window.BoatBatchReader.snapshot();
 assert.equal(snap.rows.length,2);
 assert.equal(snap.rows[0].race,2);
 assert.equal(snap.rows[1].race,3);
 assert.equal(snap.rows[0].kind,'image');
 assert.match(ui.innerHTML,/2R 抽出/);
 assert.equal(store.has('boatlab-results-v1'),false,'image recognition cannot auto-settle');
 bulkDomRows=snap.rows.map((x,i)=>fakeRow(i,x));
 click('[data-action]',{action:'batch-apply'});
 const manual=JSON.parse(store.get('boatlab-results-v1'));
 assert.equal(manual['2026-10-22|鳴門|2'].finish,'1-2-3');
 assert.equal(manual['2026-10-22|鳴門|2'].source,'image_ocr_unverified');
 assert.equal(manual['2026-10-22|鳴門|3'].payout_per_100,1450);
 assert.equal(window.BoatLab.officialStats(window.BoatLab.getData().forecast_races).count,1,
   'photo OCR is not verified official evidence');
 const payoutPage={
   date:'2026-10-22',status:'verified_by_server_fetch',
   evidence_type:'official_boatrace_pay_snapshot',
   source_url:'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022',
   retrieved_at_utc:'2026-10-22T06:00:00+00:00',
   results:{
     '14-1':{finish:data.official_results['2026-10-22|鳴門|1'].finish,payout_per_100:2350},
     '14-4':{finish:'3-1-2',payout_per_100:4720}
   },reviews:{},cancellations:{},conflicts:{}
 };
 pdfSnapshot=payoutPage;
 node('batch-url').value=payoutPage.source_url;
 click('[data-action]',{action:'batch-url-read'});
 await delay(30);
 const officialStage=window.BoatBatchReader.snapshot();
 assert.equal(officialStage.rows.length,2);
 assert.equal(officialStage.rows.filter(x=>x.officialDone).length,1);
 assert.equal(officialStage.rows.filter(x=>x.checked).length,1);
 assert.match(ui.innerHTML,/公式照合済み/);
 bulkDomRows=officialStage.rows.map((x,i)=>fakeRow(i,x));
 click('[data-action]',{action:'batch-apply'});
 const storedOfficial=JSON.parse(store.get('boatlab-batch-official-v1'));
 assert.equal(storedOfficial['2026-10-22|鳴門|4'].finish,'3-1-2');
 assert.equal(storedOfficial['2026-10-22|鳴門|4'].source,'boatrace_official_pay');
 assert.equal(storedOfficial['2026-10-22|鳴門|4'].verified,true);
 assert.equal(window.BoatLab.officialStats(window.BoatLab.getData().forecast_races).count,2);
 assert.equal(data.official_results['2026-10-22|鳴門|4'],undefined,
   'published immutable forecast payload must remain unchanged');
 assert.equal(data.forecast_races[3].bets[0].combination,payload.forecast_races[3].bets[0].combination);
 console.log('BOAT LAB image and official URL full-day batch integration: PASS');
}
run().catch(e=>{console.error(e);process.exitCode=1});
