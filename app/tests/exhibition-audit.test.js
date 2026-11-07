const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const archive=JSON.parse(fs.readFileSync('app/data/exhibition/2026-10-23.json','utf8'));
assert.ok(archive.records.length>=1);
let hits=[];
let sourceArchive=archive;
let sourceAudit=null;
const day=archive.event_date;
const status={event_date:day,collected_at_utc:new Date().toISOString(),
 complete_sources:true,research_races:archive.records.length};
const window={};
const context={window,Date,Number,fetch:async(url)=>{
 hits.push(String(url));
 return {ok:true,json:async()=>String(url).includes('status-latest')?status:
  String(url).includes('rejection-audit-latest')?sourceAudit:sourceArchive};
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
 // 11/7-type failure: research is captured too late, never promoted retroactively.
 const code=day.replaceAll('-','')+'1106';
 const captured=day+'T03:48:51+00:00'; // 12:48:51 JST; safe deadline 12:45.
 const makeRow=at=>({race_code:code,venue:'びわこ',race:6,cutoff_jst:'12:48',
  source_observed_jst:day+'T12:40:00+09:00',preview_captured_at_utc:at,
  boats:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,
   exhibition_st:0.12,exhibition_time:6.8}))});
 sourceArchive={schema:'boatlabs.exhibition_research.v1',event_date:day,
  created_at_utc:day+'T03:49:00Z',records:[makeRow(captured)]};
 sourceAudit={event_date:day,status:'analyzed',
  classification:'retrospective_diagnostic_not_live_eligibility',
  race_reasons:[{race_code:code,reason:'research_import_after_safe_freeze_deadline'}]};
 await ui.load(day);
 const base={venue:'びわこ',race:6,cutoff_jst:'12:48',phase:'baseline'};
 const evidenceBefore=JSON.stringify(base);
 assert.equal(ui.diagnose(base,Date.parse(day+'T12:51:00+09:00')).code,'late');
 assert.match(ui.panel(base),/安全期限を超過/);
 assert.match(ui.banner({mode:'auto-live',updated_at_utc:new Date().toISOString(),
  forecast_races:[base]}),/期限超過 1R/);
 const formal={...base,phase:'exhibition',
  exhibition_input_check:{verified_before_freeze:true},
  entry_exhibition_gate:{final_eligible:true}};
 assert.equal(ui.diagnose(formal).code,'formal');
 assert.equal(ui.diagnose({...base,phase:'exhibition'}).code,'frozen_unverified');
 // Earlier six-boat capture + no frozen exhibition: gap after the safety deadline.
 sourceArchive.records=[makeRow(day+'T03:40:00Z')];
 sourceAudit.race_reasons=[{race_code:code,
   reason:'not_frozen_despite_plausible_source_timestamp_investigate_runtime'}];
 await ui.load(day);
 assert.equal(ui.diagnose(base,Date.parse(day+'T12:42:00+09:00')).code,'waiting');
 assert.equal(ui.diagnose(base,Date.parse(day+'T12:46:00+09:00')).code,'gap');
 assert.equal(ui.diagnose({...base,race:7}).code,'not_collected');
 sourceAudit.race_reasons=[{race_code:code,
  reason:'exhibition_snapshot_present_check_formal_gate'}];
 await ui.load(day);
 assert.match(ui.diagnose(base,Date.parse(day+'T12:46:00+09:00')).detail,/表示や正式判定/);
 assert.equal(JSON.stringify(base),evidenceBefore,'read-only diagnostics cannot rewrite frozen picks');
 console.log('Exhibition research visibility, source health and frozen separation: PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
