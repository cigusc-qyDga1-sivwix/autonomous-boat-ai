'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const legs=require('../three-leg-primary.js');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const profiles=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;

function race(venue='児島'){
 return {
   venue,phase:'exhibition',linked_primary_trial:true,
   three_leg_primary_trial:true,venue_tactics_trial:true,
   venue_profile:profiles.find(p=>p.name===venue),
   weather_used:{wind_speed:2},frozen_at_utc:'2026-11-10T03:00:00Z',
   racers:Array.from({length:6},(_,i)=>({
     lane:i+1,course:i+1,
     national_win_rate:6.2-i*.19,average_start_timing:.13+i*.012,
     motor_top_2_percent:51-i*4,
     exhibition_st:.11+i*.012,
     exhibition_time:6.72+i*.032,
     original_exhibition:{
       lap_time:36.5-i*.09,
       half_lap_time:18.3-i*.07,
       turn_time:5.9-i*.12,
       straight_time:7.11+i*.023
     },racer_context:null
   }))
 };
}
for(const venue of ['児島','浜名湖','福岡','桐生','住之江','芦屋']){
 const input=race(venue),copy=JSON.stringify(input);
 const enabled=bridge.run(input);
 const prior=bridge.run({...input,three_leg_primary_trial:false});
 assert.equal(JSON.stringify(input),copy,'Source racers must remain untouched');
 assert.equal(enabled.model_version,prior.model_version);
 const leg=enabled.three_leg_primary_v1;
 assert.equal(leg.status,'applied',venue);
 assert.equal(leg.applied,true);
 assert.equal(leg.result_data_used,false);
 assert.equal(leg.source_exhibition_weight_unchanged,true);
 assert.equal(leg.rows.length,6);
 assert.equal(enabled.three_leg_control_ranked.length,120);
 assert.deepEqual(enabled.three_leg_control_ranked,prior.ranked_outcomes);
 assert.equal(enabled.ranked_outcomes.length,120);
 assert.ok(Math.abs(enabled.ranked_outcomes.reduce((sum,x)=>sum+x.relative_score,0)-1)<1e-7);
 assert.ok(bridge.validBets(enabled.bets,20));
 assert.ok(bridge.validBets(prior.bets,20));
 assert.ok(enabled.ranked_outcomes.some((x,i)=>
   Math.abs(x.relative_score-prior.ranked_outcomes[i].relative_score)>1e-10));
 for(const row of leg.rows){
  const w=row.multipliers;
  assert.ok(Math.abs(w.go*w.turn*w.straight-1)<1e-10);
  assert.ok(Object.values(w).every(v=>v>=Math.exp(-.012)-1e-10&&v<=Math.exp(.012)+1e-10));
  if(['児島','桐生','住之江','芦屋'].includes(venue)){
   assert.equal(w.go,1,'No fabricated independent launch for '+venue);
   assert.equal(row.go_evidence,'not_separately_measured');
  }else{
   assert.equal(row.go_evidence,'original_straight_segment');
  }
 }
 if(venue==='桐生')assert.ok(leg.source_metric_keys.includes('half_lap_time'));
 if(venue==='住之江')assert.ok(!leg.source_metric_keys.includes('straight_time'));
}
// Missing 6-boat readings -> exactly unchanged 120 rankings; no filled values.
const partial=race();
partial.racers[3].original_exhibition.turn_time=null;
const disabled=bridge.run({...partial,three_leg_primary_trial:false});
const incomplete=bridge.run(partial);
assert.equal(incomplete.three_leg_primary_v1.status,'incomplete_required_exhibition');
assert.equal(incomplete.three_leg_primary_v1.applied,false);
assert.deepEqual(incomplete.ranked_outcomes,disabled.ranked_outcomes);
assert.equal(incomplete.three_leg_control_ranked,undefined);
// Other phases and excluded venue get strict neutrality.
for(const input of [{...race(),phase:'baseline'},{...race('江戸川')}]) {
 const x=bridge.run(input);
 const y=bridge.run({...input,three_leg_primary_trial:false});
 assert.equal(x.three_leg_primary_v1.status,'not_eligible');
 assert.deepEqual(x.ranked_outcomes,y.ranked_outcomes);
}
// Results are never inputs to the formal leg decision.
const source=race();
const fresh=bridge.run(source);
const poisoned=bridge.run({...source,official_results:{finish:'6-5-4'},
 result:{finish:'1-2-3'},pay:{payout_per_100:99999}});
assert.deepEqual(poisoned,fresh);
const raw=require('../four-factor.js').evaluate(source);
const derived=legs.evaluate(source,raw);
assert.equal(derived.source_exhibition_weight_unchanged,true);
console.log('Three-leg formal: same exhibition total, bounded roles, 23 venues, no lookahead PASS');
