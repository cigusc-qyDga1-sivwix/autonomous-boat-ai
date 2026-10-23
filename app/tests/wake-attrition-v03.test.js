'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const box={};vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),{window:box,Number,Intl});
const T=box.BoatTacticalModel;
const racers=Array.from({length:6},(_,i)=>({
 lane:i+1,course:i+1,national_win_rate:[4.6,4.7,4.2,8.4,6.8,6.2][i],
 motor_top_2_percent:[25,22,23,70,52,45][i],
 average_start_timing:[.20,.18,.19,.10,.13,.14][i],
 exhibition_st:[.21,.18,.20,.08,.12,.13][i],
 exhibition_time:[6.85,6.90,6.82,6.55,6.70,6.72][i]
}));
const inRace={venue:'鳴門',racers,weather_used:{wind_speed:2}};
const immutable=JSON.stringify(inRace);
const v01=T.forecast(inRace),v02=T.forecastOutside(inRace),v03=T.forecastWake(inRace);
assert.equal(JSON.stringify(inRace),immutable);
assert.equal(v01.model,'tactical-1m-conditional-v0.1-untrained');
assert.equal(v02.model,'tactical-outside-makuri-v0.2-untrained');
assert.equal(v03.model,'tactical-wake-attrition-v0.3-untrained');
const find=(model,c)=>model.bets.find(x=>x.combination===c)?.relative_score||0;
assert.ok(find(v03,'4-5-6')>find(v02,'4-5-6'),'follow boats 5 and 6 benefit relatively when inner washes out');
assert.ok(v03.metadata.wake_risk_by_attacker.find(x=>x.head_course===4).inner_courses
 .every(x=>x.estimated_exposure>.15),'strong 4 makuri has high conditional wake exposure for inner 1–3');
assert.deepEqual(JSON.parse(JSON.stringify(v03.head_course_shares)),
 JSON.parse(JSON.stringify(v02.head_course_shares)),'wake affects conditionally who follows, not the head bias');
const weak={...inRace,racers:racers.map((r,i)=>i===3?{...r,
 national_win_rate:3.0,motor_top_2_percent:10,
 average_start_timing:.30,exhibition_st:.30,exhibition_time:7.15}:r)};
const weakTrial=T.forecastWake(weak);
assert.ok(weakTrial.metadata.wake_risk_by_attacker.find(x=>x.head_course===4)
 .inner_courses.every(x=>x.estimated_exposure===0),'weak attacker must not impose invented washout');
const entry={...inRace,racers:racers.map((r,i)=>({
 ...r,course:[1,4,5,3,6,2][i]
}))};
const changed=T.forecastWake(entry);
assert.equal(changed.head_course_shares[1].lane,6,'actual 2C is 6 boat, not lane 2');
assert.throws(()=>T.forecastWake({...inRace,racers:racers.map((r,i)=>({
 ...r,course:i===0?2:i===1?2:i+1
}))}),/実進入が未確認/,'v0.3 cannot silently fall back to ordinary course when invalid');
const withOutcome=T.forecastWake({...inRace,result:{finish:'4-5-6'},payout:{yen_per_100:100000}});
assert.deepEqual(JSON.parse(JSON.stringify(withOutcome)),JSON.parse(JSON.stringify(v03)),
 'no post-race decision or payout in model');
for(const pred of [v01,v02,v03]){
 assert.ok(pred.bets.length>=4&&pred.bets.length<=12);
 assert.equal(pred.bets.reduce((sum,b)=>sum+b.virtual_yen,0),50000);
 assert.equal(new Set(pred.bets.map(x=>x.combination)).size,pred.bets.length);
}
const {run}=require('../../scripts/freeze_wake_trials.js');
const oldBets=['1-2-3','1-3-2','2-1-3','3-1-2','1-2-4','3-2-1']
 .map((combination,i)=>({combination,virtual_yen:i===0?10000:8000}));
const now=Date.parse('2026-10-23T16:42:00+09:00');
const race=(n,clock,phase='baseline')=>({venue:'鳴門',race:n,phase,
 cutoff_jst:clock,racers,bets:oldBets,
 model_version:'old',sha256:'b'.repeat(64),
 frozen_at_utc:'2026-10-23T07:20:00Z',weather_used:{wind_speed:2}});
const live={event_date:'2026-10-23',updated_at_utc:'2026-10-23T07:41:00Z',
 forecast_races:[race(1,'16:44'),race(2,'17:15'),race(3,'17:30')]};
const first=run(live,null,now);
assert.equal(first.doc.records.length,2);
assert.equal(first.status.new_forward_freezes,2);
assert.equal(first.status.excluded_late,1);
const r=first.doc.records[0];
assert.equal(r.previous_model.model,v02.model);
assert.equal(r.wake_model.model,v03.model);
assert.match(r.record_sha256,/^[a-f0-9]{64}$/);
assert.equal(r.virtual_budget_per_model_yen,50000);
const replay=run(live,first.doc,now+1000);
assert.equal(replay.status.new_forward_freezes,0);
assert.deepEqual(replay.doc.records.map(x=>x.record_sha256),first.doc.records.map(x=>x.record_sha256));
assert.equal(run({...live,updated_at_utc:'2026-10-23T05:41:00Z'},null,now).doc.records.length,0);
const later={...live,forecast_races:[race(2,'17:15','exhibition')]};
assert.equal(run(later,first.doc,now+1000).doc.records.length,3,'distinct exhibition version only');
console.log('Makuri wake-attrition v0.3 and independent pre-cutoff SHA: PASS');
