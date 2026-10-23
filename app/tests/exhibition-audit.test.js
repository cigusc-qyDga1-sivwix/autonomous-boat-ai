const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const archive=JSON.parse(fs.readFileSync('app/data/exhibition/2026-10-23.json','utf8'));
assert.ok(archive.records.length>=1);
let hits=[];
const day=archive.event_date;
const status={event_date:day,collected_at_utc:new Date().toISOString(),
 complete_sources:true,research_races:archive.records.length};
const window={};
const context={window,Date,Number,fetch:async(url)=>{
 hits.push(String(url));
 return {ok:true,json:async()=>String(url).includes('status-latest')?status:archive};
}};
vm.runInNewContext(fs.readFileSync('app/exhibition-audit.js','utf8'),context);
const ui=window.BoatExhibitionAudit;
(async()=>{
 await ui.load(day);
 const first=archive.records[0];
 const r={venue:first.venue,race:first.race,phase:'baseline'};
 const evidence=JSON.stringify(r);
 const panel=ui.panel(r);
 assert.match(panel,/取得済み展示/);
 assert.match(panel,/固定予想には未反映/);
 assert.match(panel,/展示ST/);
 assert.match(panel,/研究記録/);
 assert.ok(!panel.includes(first.result?.finish||'XXX-NONE-YYY'),'must not render outcomes in exhibition research panel');
 const banner=ui.banner({mode:'auto-live',updated_at_utc:new Date().toISOString(),forecast_races:[
  {phase:'baseline'},{phase:'exhibition'}]});
 assert.match(banner,/1\/2R/);
 assert.match(banner,/展示研究記録/);
 assert.match(banner,/展示収集チェック/);
 assert.ok(hits.some(x=>x.includes('/data/exhibition/2026-10-23.json')));
 assert.equal(JSON.stringify(r),evidence,'no mutation of pre-cutoff original race');
 assert.ok(ui.status().count>0);
 console.log('Exhibition research visibility, source health and frozen separation: PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
