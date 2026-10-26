'use strict';
const assert=require('node:assert/strict');
require('../four-factor.js');
require('../tactical-1m.js');
const T=globalThis.BoatTacticalModel;
const fixture=(venue,phase='exhibition')=>({
 venue,phase,frozen_at_utc:'2026-10-27T00:00:00Z',
 weather_used:{wind_speed:2,wave_height:1},
 racers:Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,
   national_win_rate:5,motor_top_2_percent:30,
   average_start_timing:[.18,.18,.09,.12,.15,.17][i],
   exhibition_time:6.8,exhibition_st:.15,
   racer_context:{values:{national_top3:50,local_win:5,frame_win:5,frame_st:.17,motor_top3:50}}
 }))
});
const pick=input=>T.forecastVenueLayoutTrial(input);
for(const venue of ['戸田','福岡','唐津']){
 const input=fixture(venue),before=JSON.stringify(input);
 const trial=pick(input),main=T.forecastFourFactorOpen(input);
 assert.equal(JSON.stringify(input),before,'prediction cannot mutate the immutable input');
 assert.equal(trial.model,'four-factor-venue-layout-v1.2-untrained');
 assert.equal(main.model,'four-factor-v1.1-untrained','existing main remains v1.1');
 assert.equal(trial.metadata.venue_layout_v12.target_venue,true);
 assert.equal(trial.metadata.venue_layout_v12.applied,true,
  'the fixture has an estimated 3-course ST/go/turn attack advantage');
 assert.ok(trial.metadata.venue_layout_v12.adjustments.some(x=>x.course===3));
 assert.notDeepEqual(trial.head_course_shares,main.head_course_shares,
  'evidence-gated target trial must actually change head rankings');
 assert.equal(trial.metadata.venue_layout_v12.excluded_edogawa,false);
 assert.equal(trial.metadata.venue_layout_v12.wind_bearing_inferred,false);
 assert.equal(trial.metadata.venue_layout_v12.tide_observation_used,false);
 assert.equal(trial.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
 assert.ok(trial.bets.length>=4&&trial.bets.length<=12);
 assert.equal(new Set(trial.bets.map(b=>b.combination)).size,trial.bets.length);
 const gains=trial.metadata.venue_layout_v12.adjustments;
 assert.ok(gains.every(x=>x.relative_multiplier>=1&&x.relative_multiplier<=1.05));
}
// No inferred attack from site identity alone.
for(const venue of ['戸田','福岡','唐津']){
 const neutral=fixture(venue);
 for(const boat of neutral.racers)boat.average_start_timing=.17;
 assert.equal(pick(neutral).metadata.venue_layout_v12.applied,false,
  'layout alone must not manufacture a favorable center attack');
}
const karatsuBaseline=pick(fixture('唐津','baseline'));
assert.equal(karatsuBaseline.metadata.venue_layout_v12.applied,false,
 'no Karatsu layout adjustment without complete exhibition');
assert.equal(karatsuBaseline.metadata.venue_layout_v12.karatsu_real_entry_certified,false);
for(const venue of ['江戸川','徳山','大村']){
 const input=fixture(venue),trial=pick(input),main=T.forecastFourFactorOpen(input);
 assert.equal(trial.metadata.venue_layout_v12.applied,false);
 assert.equal(trial.metadata.venue_layout_v12.target_venue,false);
 assert.deepEqual(trial.head_course_shares,main.head_course_shares,
  'non-target sites must retain main head rankings');
 assert.deepEqual(trial.bets,main.bets,
  'non-target sites must retain main ticket combinations and allocations');
}
const withoutTide=fixture('福岡');withoutTide.weather_used=null;
assert.equal(pick(withoutTide).metadata.venue_layout_v12.tide_observation_used,false);
assert.equal(pick(withoutTide).metadata.venue_layout_v12.wind_bearing_inferred,false);
console.log('Venue layout trial: PASS (Toda/Fukuoka/Karatsu; Edogawa excluded)');
