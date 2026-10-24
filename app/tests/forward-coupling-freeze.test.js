'use strict';
const assert=require('node:assert/strict');
const {run}=require('../../scripts/freeze_coupling_trials.js');
const day='2026-10-24',now=Date.parse('2026-10-24T16:30:00+09:00');
const racers=Array.from({length:6},(_,i)=>({
 lane:i+1,course:i+1,national_win_rate:[4.8,4.8,5,8,7,5][i],
 motor_top_2_percent:[31,33,32,66,55,39][i],average_start_timing:[.19,.18,.17,.08,.11,.15][i]
}));
const bets=['1-2-3','1-2-4','1-3-2','4-5-1'].map(combination=>({combination,virtual_yen:12500}));
const mk=(n,clock,phase='baseline')=>({
 venue:'鳴門',race:n,cutoff_jst:clock,phase,racers,
 bets,model_version:'frozen-v1',sha256:'a'.repeat(64),
 frozen_at_utc:'2026-10-24T06:59:00Z',weather_used:{wind_speed:2}});
const live={event_date:day,updated_at_utc:'2026-10-24T07:29:00Z',
 forecast_races:[mk(1,'16:32'),mk(2,'16:48'),mk(3,'17:18','exhibition')]};
const original=JSON.stringify(live);
const first=run(live,null,now);
assert.equal(first.status.new_forward_freezes,2);
assert.equal(first.status.excluded_late,1);
assert.equal(first.doc.records.length,2);
assert.equal(first.doc.records[0].v05_control.model,'tactical-outside-role-v0.5-untrained');
assert.equal(first.doc.records[0].v06_coupled.model,'tactical-six-boat-coupling-v0.6-untrained');
assert.equal(first.doc.records[0].v06_coupled.interaction_graph.length,6);
assert.match(first.doc.records[0].record_sha256,/^[a-f0-9]{64}$/);
assert.equal(first.doc.records[0].original_fixed_sha256,'a'.repeat(64));
assert.equal(first.doc.records[0].input_quality.entry_confirmed_exhibition,false);
assert.equal(first.status.entry_provisional_new,1);
for(const r of first.doc.records){
 for(const key of ['v05_control','v06_coupled']){
  const bets=r[key].bets;
  assert.ok(bets.length>=4&&bets.length<=12);
  assert.equal(bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
 }
}
assert.equal(JSON.stringify(live),original,'do not mutate source records');
const replay=run(live,first.doc,now+1000);
assert.equal(replay.status.new_forward_freezes,0);
assert.deepEqual(replay.doc.records.map(x=>x.record_sha256),first.doc.records.map(x=>x.record_sha256));
const contaminated={...live,official_results:{'鳴門|2':{finish:'4-5-6',payout:10000}},
 forecast_races:live.forecast_races.map(x=>({...x,result:{finish:'4-5-6'},payout:{value:9800}}))};
assert.deepEqual(run(contaminated,null,now).doc.records.map(x=>x.v06_coupled.bets),
 first.doc.records.map(x=>x.v06_coupled.bets),'no outcome leakage into predictions');
const stale={...live,updated_at_utc:'2026-10-24T05:00:00Z'};
assert.equal(run(stale,null,now).doc.records.length,0);
assert.throws(()=>run({...live,event_date:'invalid'},null,now),/Missing source event date/);
console.log('BOAT LAB v0.6 pre-cutoff SHA and matched v0.5 A/B checks: PASS');
