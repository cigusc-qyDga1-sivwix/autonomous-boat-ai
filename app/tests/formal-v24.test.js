'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const factors=require('../four-factor.js');
const profiles=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;
function input(venue='福岡'){
 return {venue,phase:'exhibition',venue_tactics_trial:true,linked_primary_trial:true,
  three_leg_primary_trial:true,formal_insight_v24:true,
  frozen_at_utc:'2026-11-11T00:46:00Z',
  venue_profile:profiles.find(x=>x.name===venue),weather_used:{wind_speed:2},
  racers:Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,national_win_rate:6.2-i*.10,
   average_start_timing:i===0?.187:i===2?.132:.16,
   motor_top_2_percent:48-i*2,exhibition_st:.12+i*.006,
   exhibition_time:6.79-i*.014,
   original_exhibition:{
    lap_time:36.67-i*.02,half_lap_time:18.2-i*.02,
    turn_time:i===2?5.29:5.65-i*.015,
    straight_time:7.31+i*.012
   }
  }))
 };
}
for(const venue of ['福岡','児島','桐生','徳山']){
 const source=input(venue);
 const saved=JSON.stringify(source);
 const prior=bridge.run({...source,formal_insight_v24:false});
 const revised=bridge.run(source);
 assert.equal(JSON.stringify(source),saved);
 assert.equal(revised.formal_insight_v24.generated_pre_cutoff,true);
 assert.equal(revised.formal_insight_v24.result_data_used,false);
 assert.deepEqual(revised.formal_insight_v24.ranked_outcomes,prior.ranked_outcomes);
 assert.equal(revised.formal_insight_v24.formal_exhibition_balance.applied,true);
 assert.equal(revised.formal_insight_v24.formal_inside_pressure?.pre_cutoff_only,true);
 assert.equal(revised.ranked_outcomes.length,120);
 assert.ok(Math.abs(revised.ranked_outcomes.reduce((s,x)=>s+x.relative_score,0)-1)<1e-10);
 assert.ok(bridge.validBets(revised.bets,20));
 assert.ok(bridge.validBets(prior.bets,20));
 assert.ok(revised.ranked_outcomes.some((x,i)=>
   Math.abs(x.relative_score-prior.ranked_outcomes[i].relative_score)>1e-10));
 if(venue==='福岡') assert.equal(revised.formal_insight_v24.formal_exhibition_balance.metric_mix.time,.18);
 if(venue==='桐生') assert.equal(revised.formal_insight_v24.formal_exhibition_balance.metric_mix.half,.10);
 if(venue==='徳山') assert.equal(revised.formal_insight_v24.formal_exhibition_balance.metric_mix.straight,undefined);
 assert.equal(revised.four_factor.weights.exhibition,.10,'must not increase total exhibition factor');
 assert.deepEqual(bridge.run({...source,result:{finish:'6-5-4'},pay:{payout_per_100:9999},odds:9999}),revised);
}
const support=input('児島');
assert.equal(bridge.run(support).formal_insight_v24.formal_inside_pressure.applied,true);
const noPressure=input('児島');
noPressure.racers[0].average_start_timing=.12;
assert.equal(bridge.run(noPressure).formal_insight_v24.formal_inside_pressure.applied,false,
 'Do not indiscriminately penalize course one');
const missing=input('児島');
missing.racers[4].original_exhibition.turn_time=null;
const disabled=bridge.run({...missing,formal_insight_v24:false});
const partial=bridge.run(missing);
assert.equal(partial.formal_insight_v24.formal_exhibition_balance.applied,false);
assert.equal(partial.formal_insight_v24.formal_inside_pressure.applied,false);
assert.deepEqual(partial.ranked_outcomes,disabled.ranked_outcomes,
 'No invented missing six-boat original metrics');
assert.equal(factors.evaluate({...missing,formal_insight_v24:false}).formal_exhibition_balance_v24,undefined);
console.log('Formal v2.4: real-course matchup, four metrics, prior-control, fail-neutral, no result leak PASS');
