'use strict';
const assert=require('node:assert/strict');
const bridge=require('../../scripts/main_four_factor_bridge.js');
require('../four-factor.js');
require('../tactical-1m.js');
const model=globalThis.BoatTacticalModel;
const fixture=()=>({
 venue:'三国',phase:'exhibition',frozen_at_utc:'2026-10-27T08:45:00Z',
 weather_used:{wind_speed:2,wave_height:1},
 racers:Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,national_win_rate:[5.4,5.1,5.2,5.5,6.6,6.2][i],
  motor_top_2_percent:[30,32,31,34,55,51][i],
  average_start_timing:[.17,.17,.18,.17,.14,.14][i],
  exhibition_st:[.16,.17,.18,.16,.04,.05][i],
  exhibition_time:[6.89,6.91,6.88,6.90,6.78,6.82][i],
  racer_context:null
 }))
});
const input=fixture(),untouched=JSON.stringify(input);
const result=bridge.run({...input,postrace_conditional_trial:true});
assert.equal(JSON.stringify(input),untouched);
assert.equal(result.model_version,'four-factor-v1.3-conditional-scenarios-untrained');
assert.ok(bridge.validBets(result.bets));
assert.equal(result.postrace_conditional_v13.pre_cutoff_only,true);
assert.equal(result.postrace_conditional_v13.result_data_used,false);
assert.equal(result.postrace_conditional_v13.observations.length,4);
const fifth=result.postrace_conditional_v13.observations.find(x=>x.course===5);
assert.equal(fifth.outside_head_supported,true);
assert.equal(fifth.adjacent_follow_supported,true);
assert.ok(fifth.head_multiplier>1);
assert.equal(result.postrace_conditional_control.model_version,'four-factor-v1.2-head-coverage-untrained');
assert.ok(bridge.validBets(result.postrace_conditional_control.bets));
assert.deepEqual(result.postrace_conditional_control.bets,bridge.run({...input,head_coverage_trial:true}).bets);
assert.deepEqual(bridge.run({...input,postrace_conditional_trial:true,result:{finish:'5-6-1'},payout:99999,odds:{x:2}}),result,
 'outcome, payouts and odds cannot change v1.3');
assert.deepEqual(result.bets,model.forecastFourFactorConditional(input).bets,'bridge/browser parity');
const beta=fixture();beta.phase='baseline';
assert.ok(bridge.run({...beta,postrace_conditional_trial:true}).postrace_conditional_v13.observations.every(x=>!x.outside_head_supported),
 'no preview means no exhibition boost');
const weak=fixture();weak.racers[4].exhibition_time=7.2;
assert.equal(bridge.run({...weak,postrace_conditional_trial:true}).postrace_conditional_v13.observations.find(x=>x.course===5).outside_head_supported,false);
const flying=fixture();flying.racers[4].exhibition_st=-.05;
const invalid=fixture();invalid.racers[4].exhibition_st=null;
const f=bridge.run({...flying,postrace_conditional_trial:true}),n=bridge.run({...invalid,postrace_conditional_trial:true});
assert.deepEqual(f.bets,n.bets,'exhibition F has no false fast-ST bonus');
assert.ok(f.postrace_conditional_v13.observations[2].exhibition_f_ignored);
assert.ok(bridge.validBets(bridge.run({...input,postrace_conditional_trial:true,head_coverage_trial:true}).bets));
console.log('Conditional v1.3: measured outside speed, conditional second, no F leakage, matched v1.2, frozen-input parity and money constraints PASS');
