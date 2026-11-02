'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const engine=require('../venue-motor-exhibition.js');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const profiles=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;
const names=profiles.map(p=>p.name);
assert.equal(names.length,24);
assert.deepEqual(new Set(names),new Set(Object.keys(engine.FOCUS)));
function fixture(venue='児島',phase='exhibition'){
 const racers=Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,
  national_win_rate:[6.2,6.1,6.0,5.9,5.8,5.7][i],
  motor_top_2_percent:[48,45,39,32,26,22][i],
  average_start_timing:[.16,.15,.14,.16,.15,.17][i],
  exhibition_st:phase==='exhibition'?[.13,.12,.15,.18,.16,.19][i]:null,
  exhibition_time:phase==='exhibition'?[6.72,6.75,6.80,6.85,6.89,6.93][i]:null,
  original_exhibition:phase==='exhibition'?{
   lap_time:[36.2,36.4,36.5,36.8,37.0,37.2][i],
   turn_time:[5.20,5.22,5.31,5.40,5.49,5.55][i],
   straight_time:[6.00,6.04,6.09,6.12,6.19,6.23][i]
  }:null,
  racer_context:null
 }));
 return {venue,phase,racers,venue_profile:profiles.find(p=>p.name===venue),
   weather_used:{wind_speed:2},frozen_at_utc:'2026-11-02T01:00:00Z',
   venue_tactics_trial:true,venue_motor_exhibition_shadow_trial:true};
}
for(const name of names){
 const input=fixture(name);
 const detail=engine.evaluate(input);
 assert.equal(detail.excluded,name==='江戸川');
 assert.equal(detail.eligible,name!=='江戸川');
 assert.equal(detail.result_data_used,false);
 assert.equal(detail.pre_cutoff_only,true);
 assert.equal(detail.rows.length,6);
 assert.equal(detail.metric_coverage_count,4);
 assert.equal(detail.applied,name!=='江戸川');
 for(const row of detail.rows){
  assert.ok(Object.values(row.multipliers).every(n=>n>=.965&&n<=1.036));
  assert.ok(Number.isInteger(row.course)&&row.course>=1&&row.course<=6);
 }
 const trial=bridge.run(input);
 const control=bridge.run({...input,venue_motor_exhibition_shadow_trial:false});
 assert.deepEqual(trial.bets,control.bets,'canonical main must NEVER change: '+name);
 assert.equal(trial.venue_motor_exhibition_shadow.not_formal,true);
 assert.deepEqual(trial.venue_motor_exhibition_shadow.control_bets,control.bets);
 assert.equal(trial.venue_motor_exhibition_shadow.same_inputs_except_shadow,true);
 assert.equal(trial.venue_motor_exhibition_shadow.no_additional_stake,true);
 assert.ok(bridge.validBets(trial.venue_motor_exhibition_shadow.trial_bets,20));
 if(name==='江戸川')assert.deepEqual(trial.venue_motor_exhibition_shadow.trial_bets,control.bets);
}
const base=fixture();
const check=engine.evaluate(base);
assert.ok(check.rows[0].multipliers.straight>1);
assert.ok(check.rows[0].multipliers.turn>1);
assert.ok(check.rows[5].multipliers.straight<1);
const baseline=engine.evaluate(fixture('児島','baseline'));
assert.equal(baseline.status,'not_eligible');
assert.equal(baseline.applied,false);
const partial=fixture();
partial.racers[3].original_exhibition.turn_time=null;
assert.equal(engine.evaluate(partial).metric_coverage_count,3,'one missing disables the whole specific metric');
const noMetrics=fixture();
noMetrics.racers.forEach(r=>{r.exhibition_time=null;r.original_exhibition=null;});
assert.equal(engine.evaluate(noMetrics).status,'exhibition_metrics_incomplete');
assert.ok(engine.evaluate(noMetrics).rows.every(r=>r.multipliers.go===1));
const incompleteMotor=fixture();incompleteMotor.racers[5].motor_top_2_percent=0;
assert.equal(engine.evaluate(incompleteMotor).status,'motor_missing');
assert.ok(engine.evaluate(incompleteMotor).rows.every(r=>r.multipliers.turn===1));
const swap=fixture();swap.racers[0].course=4;swap.racers[3].course=1;
assert.equal(engine.evaluate(swap).rows[0].course,4,'actual entry maintained');
const f=fixture();f.racers[2].exhibition_st=-.02;
assert.deepEqual(engine.evaluate(f),check,'F is not an extra motor score');
const leak=fixture();leak.result={finish:'6-5-4'};leak.payout=200000;leak.actual_race_st={1:.01};
assert.deepEqual(bridge.run(leak),bridge.run(base),'results cannot contaminate prospective shadow');
const windy=fixture();windy.weather_used.wind_speed=6;
assert.ok(Math.abs(Math.log(engine.evaluate(windy).rows[0].multipliers.go))<
          Math.abs(Math.log(check.rows[0].multipliers.go)));
const missingProfile=fixture();missingProfile.venue_profile=null;
assert.equal(engine.evaluate(missingProfile).applied,false);
const page=require('../four-factor.js').panel({...bridge.run(base),
 four_factor:bridge.run(base).four_factor,
 venue_motor_exhibition_shadow:bridge.run(base).venue_motor_exhibition_shadow});
assert.ok(page.includes('場別モーター×展示'));
assert.ok(page.includes('正式予想・正式収支は変更しません'));
console.log('Motor × exhibition venue shadow: 24 registry, 23 eligible, 6-boat coverage, F/missing/entry guards, same-time A/B and immutable main PASS');
