'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const venueEngine=require('../venue-motor-exhibition.js');
const profiles=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;

function input(venue){
 const racers=Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,
   national_win_rate:6.5-i*.13,motor_top_2_percent:55-i*6,
   average_start_timing:.15+i*.005,exhibition_st:.12+i*.01,
   exhibition_time:6.72+i*.025,
   original_exhibition:{
     lap_time:36.1+i*.12,half_lap_time:18.15+i*.08,
     turn_time:5.2+i*.06,straight_time:7.1+i*.035
   },racer_context:null
 }));
 return {venue,phase:'exhibition',racers,
   venue_profile:profiles.find(x=>x.name===venue),
   weather_used:{wind_speed:2},
   frozen_at_utc:'2026-11-10T00:09:00Z',
   venue_tactics_trial:true,linked_primary_trial:true,
   venue_motor_exhibition_shadow_trial:true};
}
for(const venue of ['児島','桐生','住之江','江戸川']){
 const prepared=input(venue);
 const formal=bridge.run({...prepared,venue_motor_exhibition_shadow_trial:false});
 const done=bridge.run(prepared);
 assert.deepEqual(done.bets,formal.bets,'Never revise canonical main for '+venue);
 const shadow=done.venue_motor_exhibition_shadow;
 assert.equal(shadow.not_formal,true);
 assert.equal(shadow.no_additional_stake,true);
 assert.equal(shadow.frozen_at_utc,prepared.frozen_at_utc);
 assert.equal(shadow.metric_ablation_protocol,'venue-shadow-v0.2-one-metric-removed');
 const keys=venue==='江戸川'?[]:venue==='住之江'?
  ['exhibition_time','lap_time','turn_time']:
  venue==='桐生'?['exhibition_time','half_lap_time','turn_time','straight_time']:
  ['exhibition_time','lap_time','turn_time','straight_time'];
 assert.deepEqual(shadow.metric_ablations.map(x=>x.metric),keys);
 assert.equal(shadow.metric_ablations.length,keys.length);
 for(const alt of shadow.metric_ablations){
   assert.equal(alt.status,'ready','isolated ablation available: '+venue+' '+alt.metric);
   assert.equal(alt.not_formal,true);
   assert.equal(alt.actual_results_used,false);
   assert.equal(alt.frozen_at_utc,prepared.frozen_at_utc);
   assert.equal(alt.same_virtual_budget,true);
   assert.ok(bridge.validBets(alt.bets,20));
   assert.equal(alt.same_point_count,alt.bets.length===shadow.trial_bets.length);
 }
}
const race=input('児島');
const baseline=bridge.run(race);
const tampered={...race,result:{finish:'6-5-4'},payout:100000,actual_race_st:.01};
assert.deepEqual(bridge.run(tampered),baseline,'No postrace information may change A/B');
const copy=structuredClone(race);
const before=JSON.stringify(copy);
const abr=venueEngine.evaluate({...copy,venue_metric_ablation_key:'straight_time'});
assert.equal(abr.ablated_metric,'straight_time');
assert.ok(!abr.metric_coverage.includes('straight_time'));
assert.equal(JSON.stringify(copy),before,'Do not mutate canonical input');
assert.throws(()=>venueEngine.evaluate({...race,venue_metric_ablation_key:'half_lap_time'}),/expected venue metric/);
console.log('Same-snapshot original metric ablations, per-venue coverage, no data leak, unchanged main PASS');
