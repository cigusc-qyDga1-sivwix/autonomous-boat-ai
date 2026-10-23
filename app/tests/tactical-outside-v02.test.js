'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const sandbox={};
vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),{window:sandbox,Number,Intl});
const T=sandbox.BoatTacticalModel;
const racers=Array.from({length:6},(_,i)=>({
 lane:i+1,course:i+1,national_win_rate:[6,5.8,6.1,8.7,8.3,6.9][i],
 motor_top_2_percent:[30,32,31,65,62,49][i],
 average_start_timing:[.19,.17,.18,.09,.11,.13][i],
 exhibition_st:[.18,.15,.20,.03,.05,.09][i],
 exhibition_time:[6.80,6.78,6.82,6.64,6.68,6.70][i]
}));
const input={venue:'鳴門',racers,weather_used:{wind_speed:3}};
const original=JSON.stringify(input);
const legacy=T.forecast(input),trial=T.forecastOutside(input);
assert.equal(JSON.stringify(input),original,'original inputs must never mutate');
assert.equal(legacy.model,'tactical-1m-conditional-v0.1-untrained');
assert.equal(trial.model,'tactical-outside-makuri-v0.2-untrained');
assert.equal(T.forecast({...input,experimental_variant:'outside-makuri-v0.2'}).top,trial.top);
const share=(p,c)=>p.head_course_shares.find(x=>x.course===c).relative_share;
assert.ok(share(trial,4)>share(legacy,4),'strong course4 gains relative tactical share');
assert.ok(share(trial,5)>share(legacy,5),'strong following course5 gains relative tactical share');
assert.ok(trial.bets.some(x=>x.head_course===4),'credible outside attack must be considered');
assert.ok(trial.bets.some(x=>x.combination.startsWith('4-5-')),'4-to-5 follow-up conditional branch');
assert.ok(trial.metadata.outside_attack_signals.find(x=>x.course===4).multiplier>1);
const weak={...input,racers:racers.map((r,i)=>i===3?{
 ...r,national_win_rate:3.2,motor_top_2_percent:8,average_start_timing:.29,
 exhibition_st:.29,exhibition_time:7.15}:r)};
assert.ok(T.forecastOutside(weak).metadata.outside_attack_signals.find(x=>x.course===4).multiplier<=1,
 'weak outside attack must not get a blanket enhancement');
const shuffled={...input,racers:racers.map((r,i)=>({
 ...r,course:i===0?2:i===1?1:i+1}))};
assert.equal(T.forecastOutside(shuffled).head_course_shares[0].lane,2,'actual course not lane');
assert.deepEqual(JSON.parse(JSON.stringify(T.forecastOutside({...input,result:{finish:'6-5-4',decision:'まくり'},payout:{yen_per_100:99999}}))),
 JSON.parse(JSON.stringify(trial)),'race outcomes or future payouts must not affect predicted result');
for(const pred of [legacy,trial]){
 assert.ok(pred.bets.length>=4&&pred.bets.length<=12);
 assert.equal(pred.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
 assert.equal(new Set(pred.bets.map(b=>b.combination)).size,pred.bets.length);
 assert.ok(pred.bets.every(b=>b.virtual_yen>=1000));
}
const {run}=require('../../scripts/freeze_outside_trials.js');
const sourceBets=['1-2-3','1-3-2','2-1-3','3-1-2','1-2-4','3-2-1']
 .map((x,i)=>({combination:x,virtual_yen:i===0?10000:8000}));
const now=Date.parse('2026-10-23T16:42:00+09:00');
const race=(n,clock,phase='baseline')=>({
 venue:'鳴門',race:n,phase,cutoff_jst:clock,racers,
 bets:sourceBets,model_version:'original-v0.7',sha256:'b'.repeat(64),
 frozen_at_utc:'2026-10-23T07:20:00Z',weather_used:{wind_speed:3}
});
const live={event_date:'2026-10-23',updated_at_utc:'2026-10-23T07:41:00Z',
 forecast_races:[race(1,'16:44'),race(2,'17:15'),race(3,'17:30')]};
const first=run(live,null,now);
assert.equal(first.status.new_forward_freezes,2,'less-than-three-minute lead is excluded');
assert.equal(first.status.excluded_late,1);
assert.equal(first.doc.records.length,2);
const r=first.doc.records[0];
assert.equal(r.is_forward_fixed,true);
assert.equal(r.virtual_budget_per_model_yen,50000);
assert.equal(r.previous_model.model,'tactical-1m-conditional-v0.1-untrained');
assert.equal(r.outside_model.model,'tactical-outside-makuri-v0.2-untrained');
assert.match(r.record_sha256,/^[a-f0-9]{64}$/);
assert.deepEqual(run(live,first.doc,now+1000).doc.records.map(x=>x.record_sha256),
 first.doc.records.map(x=>x.record_sha256),'immutable forward ledger');
assert.equal(run(live,first.doc,now+1000).status.new_forward_freezes,0);
const stale={...live,updated_at_utc:'2026-10-23T05:41:00Z'};
assert.equal(run(stale,null,now).doc.records.length,0,'stale snapshot is ineligible');
const replay={...live,forecast_races:[race(2,'17:15','exhibition')]};
const two=run(replay,first.doc,now+1000);
assert.equal(two.status.new_forward_freezes,1);
assert.equal(two.doc.records.filter(x=>x.race===2).length,2);
console.log('Outside makuri v0.2 and independent cutoff-before-finish seal: PASS');
