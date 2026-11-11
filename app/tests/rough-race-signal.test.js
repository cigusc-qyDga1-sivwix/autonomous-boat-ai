'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ctx={};ctx.globalThis=ctx;
vm.runInNewContext(fs.readFileSync('app/rough-race-signal.js','utf8'),ctx);
const signal=ctx.BoatRoughRaceSignal;
const base={
  venue:'三国',race:4,cutoff_jst:'11:30',phase:'exhibition',
  classification:'WATCH',model_role:'main',
  sha256:'a'.repeat(64),frozen_at_utc:'2026-11-12T02:20:00Z',
  entry_exhibition_gate:{final_eligible:true},
  exhibition_input_check:{verified_before_freeze:true},
  bets:[{combination:'4-1-3',virtual_yen:50000}],
  strong_field_diagnostic:{status:'MODEL_CLOSE_HEADS_NOT_STRONG_FIELD'}
};
const context={mode:'auto-live',formal:true,event_date:'2026-11-12'};
function assess(changes={},opts=context){return signal.assess({...base,...changes},opts);}
assert.equal(assess().label,'⚡ 荒れ注意');
assert.match(signal.render(base,context),/1着混戦/);
assert.match(signal.render(base,context),/荒れ注意/);
assert.equal(assess({strong_field_diagnostic:{status:'NO_STRONG_FIELD_PARITY_SIGNAL'}}),null,
  'No warning without frozen diagnostic evidence');
assert.equal(assess({strong_field_diagnostic:undefined,formal_head_risk_v25:{
  inside_head_rebalance:{applied:true}}}).reasons.join(''), '攻防変化');
assert.equal(assess({strong_field_diagnostic:{
  status:'NO_STRONG_FIELD_PARITY_SIGNAL',coverage_diagnostics_read_only:true,
  second_pair_coverage_status:'ASSESSED',second_pair_coverage_warning:true,
  missing_top_second_pairs:[{head_lane:4,second_lane:5}]
}}).reasons.join(''), '2着候補注意');
for(const changes of [
  {phase:'baseline'},
  {classification:'SKIP'},
  {model_role:'research_shadow'},
  {entry_exhibition_gate:{final_eligible:false}},
  {exhibition_input_check:{verified_before_freeze:false}},
  {sha256:''},
  {frozen_at_utc:'2026-11-12T02:31:00Z'},
  {frozen_at_utc:'invalid'},
  {frozen_at_utc:'2026-11-10T02:20:00Z'}
]){
 assert.equal(assess(changes),null,'Provisional, untrusted or late snapshot must not get an amber warning');
}
assert.equal(assess({}, {...context,formal:false}),null);
assert.equal(assess({}, {...context,mode:'manual'}),null);
assert.equal(assess({}, {...context,event_date:'2026-11-11'}),null);
const original=JSON.stringify(base);
const a=signal.assess({...base,result:{finish:'4-1-3'},payout:278690,odds:999},context);
const b=signal.assess({...base,result:{finish:'1-2-3'},payout:500,odds:1},context);
assert.equal(a.label,b.label,'Result and payout must never change pre-cutoff warning');
assert.equal(JSON.stringify(base),original,'Display layer must never edit frozen tickets');
const index=fs.readFileSync('app/index.html','utf8');
assert.ok(index.includes('rough-race-signal.js'));
assert.ok(index.includes('rough-race-signal.css'));
assert.ok(index.indexOf('rough-race-signal.js')<index.indexOf('venue-board.js'));
for(const p of ['app/venue-board.js','app/race-timeline.js','app/app.js','app/prediction-focus.js']){
 assert.match(fs.readFileSync(p,'utf8'),/BoatRoughRaceSignal\?\.render/,
  p+' should render verified-exhibition warning');
}
console.log('Rough-race warning: pre-cutoff-only, risk evidence-only, no betting/results mutation PASS');
