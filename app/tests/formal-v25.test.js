'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const profiles=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;
function input(){
 return {venue:'児島',phase:'exhibition',venue_tactics_trial:true,
  linked_primary_trial:true,three_leg_primary_trial:true,
  formal_insight_v24:true,formal_head_risk_v25:true,
  frozen_at_utc:'2026-11-11T02:25:00Z',
  venue_profile:profiles.find(p=>p.name==='児島'),
  weather_used:{wind_speed:2},
  racers:Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,national_win_rate:6.3-i*.10,
   average_start_timing:i===0?.188:i===2?.133:.163,
   motor_top_2_percent:50-i*2,exhibition_st:.12+i*.006,
   exhibition_time:6.78-i*.014,
   original_exhibition:{
    lap_time:36.68-i*.02,half_lap_time:18.2-i*.02,
    turn_time:i===2?5.29:5.65-i*.015,
    straight_time:7.31+i*.012
   }
  }))
 };
}
const source=input(),unchanged=JSON.stringify(source);
const old=bridge.run({...source,formal_head_risk_v25:false});
const revised=bridge.run(source);
assert.equal(JSON.stringify(source),unchanged,'must not modify source inputs');
assert.equal(revised.formal_head_risk_v25.prior_model,
 'four-factor-v2.4-entry-exhibition-balance-untrained');
assert.equal(revised.formal_head_risk_v25.result_data_used,false);
assert.equal(revised.formal_head_risk_v25.generated_pre_cutoff,true);
assert.equal(revised.formal_head_risk_v25.frozen_at_utc,source.frozen_at_utc);
assert.deepEqual(revised.formal_head_risk_v25.ranked_outcomes,old.ranked_outcomes);
assert.deepEqual(revised.formal_head_risk_v25.control_bets,old.bets);
assert.equal(revised.formal_head_risk_v25.inside_head_rebalance.applied,true);
assert.ok(revised.formal_head_risk_v25.inside_head_rebalance.final_head_multiplier >= .84,
 'course-one total head reduction must not exceed 16 percent');
assert.ok(revised.formal_head_risk_v25.inside_head_rebalance.final_head_multiplier <= 1);
assert.ok(revised.head_course_shares[0].relative_share < old.head_course_shares[0].relative_share,
 'independently supported threat must lower course-one head share');
assert.ok(revised.head_course_shares[2].relative_share > old.head_course_shares[2].relative_share,
 'supported third-course attacker should gain head share');
assert.ok(bridge.validBets(revised.bets,20));
assert.ok(bridge.validBets(old.bets,20));
assert.equal(revised.ranked_outcomes.length,120);
assert.ok(Math.abs(revised.ranked_outcomes.reduce((a,b)=>a+b.relative_score,0)-1)<1e-10);
assert.deepEqual(bridge.run({...source,result:{finish:'3-1-2'},pay:{payout_per_100:5000},
 odds:999999}),revised,'results, payouts and odds must be ignored');
const noThreat=input();
noThreat.racers[0].average_start_timing=.12;
const neutral=bridge.run(noThreat);
const baseline=bridge.run({...noThreat,formal_head_risk_v25:false});
assert.equal(neutral.formal_head_risk_v25.inside_head_rebalance.applied,false);
assert.deepEqual(neutral.ranked_outcomes,baseline.ranked_outcomes,
 'without independent attack evidence, do not punish the inside');
const missing=input();
missing.racers[4].original_exhibition.turn_time=null;
assert.equal(bridge.run(missing).formal_head_risk_v25.inside_head_rebalance.applied,false,
 'missing six-boat turn evidence must fail neutral');
console.log('Formal v2.5: challenger head switch, same-time v2.4 control, immutable stakes and result-blind PASS');
