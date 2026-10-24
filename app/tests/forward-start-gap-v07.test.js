'use strict';
const assert=require('node:assert/strict');
const {run}=require('../../scripts/freeze_start_trials.js');
const day='2026-10-24',now=Date.parse('2026-10-24T16:30:00+09:00');
const racers=Array.from({length:6},(_,i)=>({
 lane:i+1,course:i+1,national_win_rate:[5,5,5,8.5,7,6.5][i],
 motor_top_2_percent:[30,30,30,70,50,45][i],
 average_start_timing:[.18,.18,.2,.08,.12,.14][i],
 exhibition_st:[.18,.18,.19,.07,.12,.13][i]
}));
const bets=['1-2-3','1-3-2','4-5-1','5-4-1'].map(combination=>({combination,virtual_yen:12500}));
const mk=(n,cutoff,gate)=>({
 venue:'丸亀',race:n,cutoff_jst:cutoff,phase:'exhibition',
 racers,bets,sha256:'d'.repeat(64),model_version:'v1',
 frozen_at_utc:'2026-10-24T06:50:00Z',
 entry_exhibition_gate:gate
});
const source={event_date:day,updated_at_utc:'2026-10-24T07:29:00Z',
 forecast_races:[mk(1,'16:32'),mk(2,'17:04'),mk(3,'17:10',{entry_watch:true,final_eligible:false})]};
const untouched=JSON.stringify(source);
const {doc,status}=run(source,null,now);
assert.equal(status.new_forward_freezes,1);
assert.equal(status.excluded_late,1);
assert.equal(status.excluded_entry_watch,1);
assert.equal(doc.records.length,1);
assert.equal(doc.records[0].v06_control.model,'tactical-six-boat-coupling-v0.6-untrained');
assert.equal(doc.records[0].v07_start_gap.model,'tactical-outside-start-gap-v0.7-untrained');
assert.equal(doc.records[0].v07_start_gap.st_signals.length,6);
assert.equal(doc.records[0].input_quality.start_exhibition_is_not_race_st,true);
assert.equal(doc.records[0].is_forward_fixed,true);
assert.match(doc.records[0].record_sha256,/^[0-9a-f]{64}$/);
assert.equal(doc.records[0].original_fixed_sha256,'d'.repeat(64));
assert.equal(JSON.stringify(source),untouched);
const repeat=run(source,doc,now+1000);
assert.equal(repeat.status.new_forward_freezes,0);
assert.deepEqual(repeat.doc.records.map(r=>r.record_sha256),doc.records.map(r=>r.record_sha256));
const outside=doc.records[0].v07_start_gap.bets;
assert.ok(outside.length>=4&&outside.length<=12);
assert.equal(outside.reduce((n,b)=>n+b.virtual_yen,0),50000);
const leaked={...source,official_results:{'丸亀|2':{finish:'6-5-4'}},
 forecast_races:source.forecast_races.map(x=>({...x,result:{finish:'4-5-6'},payout:{amount:3000}}))};
assert.deepEqual(run(leaked,null,now).doc.records.map(r=>r.v07_start_gap.bets),
 doc.records.map(r=>r.v07_start_gap.bets));
assert.equal(run({...source,updated_at_utc:'2026-10-24T04:00:00Z'},null,now).doc.records.length,0);
console.log('BOAT LAB v0.7 pre-cutoff start v0.6 A/B + entry-watch + idempotence: PASS');
