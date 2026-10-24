'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const old=require('../../scripts/main_v07_bridge.js');
const next=require('../../scripts/main_v09_bridge.js');
const win={};vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),{window:win,Number,Intl});
const T=win.BoatTacticalModel;
const mk=()=>({
 venue:'唐津',phase:'exhibition',
 frozen_at_utc:'2026-10-25T01:40:00Z',
 weather_used:{wind_speed:2},
 racers:[5.8,5.9,5.7,8.7,8.5,5.8].map((win,i)=>({
  lane:i+1,course:i+1,national_win_rate:win,
  motor_top_2_percent:[31,33,36,77,70,29][i],
  average_start_timing:[.19,.18,.17,.08,.1,.17][i],
  exhibition_st:[.19,.18,.17,.08,.11,.17][i],
  exhibition_time:[6.85,6.82,6.8,6.51,6.55,6.82][i],
  original_exhibition:{turn_time:[5.9,5.85,5.8,5.49,5.51,5.9][i]}
 }))
});
const src=mk(),copy=JSON.stringify(src);
const a=old.run(src),b=next.run(src);
assert.equal(JSON.stringify(src),copy,'original pre-race snapshot never mutated');
assert.equal(a.model_version,'tactical-outside-start-gap-v0.7-untrained');
assert.equal(b.model_version,'tactical-outside-start-wake-v0.9-untrained');
assert.ok(old.validBets(a.bets)&&next.validBets(b.bets));
assert.equal(b.wake_v09.pre_cutoff_only,true);
assert.equal(b.wake_v09.applies_to_all_head_courses,true);
assert.equal(b.wake_v09.head_course_exposure.length,6);
assert.ok(b.wake_v09.head_course_exposure.find(x=>x.course===1).second_chasers.length===5,
 'even 1-course escape must consider wake at 2M+');
assert.equal(b.bets.reduce((n,x)=>n+x.virtual_yen,0),50000);
const expected=T.forecastWakeIntegrated(src);
assert.deepEqual(JSON.parse(JSON.stringify(expected.bets)),
 JSON.parse(JSON.stringify(b.bets)),'Node bridge exactly same canonical browser model');
assert.equal(T.forecastOutsideStart(src).model,a.model_version,
 'historical v0.7 identity must be unchanged');
const noResult=next.run({...src,result:{finish:'4-5-1'},
 official_results:{x:'4-5-1'},payout:9999,odds:{'4-5-1':120}});
assert.deepEqual(noResult,b,'no result/payout/odds leakage');
const weak=mk();weak.racers[4]={...weak.racers[4],national_win_rate:3.1,
 average_start_timing:.32,exhibition_time:7.4,motor_top_2_percent:5};
const nextWeak=next.run(weak);
assert.equal(next.validBets(nextWeak.bets),true);
assert.ok(nextWeak.bets.every(x=>x.combination.split('-').length===3));
const shifted=mk();shifted.racers[1].course=4;shifted.racers[3].course=2;
assert.equal(next.run(shifted).wake_v09.head_course_exposure.length,6);
const invalid=mk();invalid.racers[0].course=2;
assert.throws(()=>next.run(invalid),/実進入が未確認/);
console.log('v0.9 wake primary bridge: 1M/2M all-head evaluation, old v0.7 unchanged, budget and no leakage: PASS');
