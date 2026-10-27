'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
require('../four-factor.js');
require('../venue-tactics-v2.js');
require('../tactical-1m.js');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const profiles=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;
const h=globalThis.BoatVenueTacticsV2.HISTORY;
assert.equal(profiles.length,24);
assert.equal(Object.keys(h).length,24,'historical descriptive shares for every known venue');
assert.equal(new Set(profiles.map(p=>p.name)).size,24);
for(const p of profiles){
 const x=h[p.name];
 assert.equal(x.length,4);
 assert.ok(x.every(v=>Number.isFinite(v)&&v>=0&&v<=100));
 assert.ok(x.reduce((a,b)=>a+b,0)<=100,'other winning methods must remain possible');
}
function fixture(name,phase='exhibition'){
 return {
  venue:name,phase,frozen_at_utc:'2026-10-27T09:47:00Z',
  venue_profile:profiles.find(p=>p.name===name),weather_used:{wind_speed:2},
  racers:Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,
   national_win_rate:[5.7,5.4,6.4,5.9,6.4,6.0][i],
   motor_top_2_percent:[32,31,51,33,40,34][i],
   average_start_timing:[.17,.17,.09,.17,.12,.18][i],
   exhibition_st:phase==='exhibition'?[.16,.17,.08,.18,.12,.19][i]:null,
   exhibition_time:phase==='exhibition'?[6.90,6.92,6.83,6.94,6.88,6.91][i]:null,
   racer_context:null
  }))
 };
}
for(const p of profiles){
 const f=fixture(p.name),v14=bridge.run({...f,venue_tactics_trial:true});
 const meta=v14.venue_tactics_v2;
 assert.equal(v14.model_version,'four-factor-v1.4-venue-aware-23-untrained');
 assert.equal(meta.version,'venue-tactics-v2-23venues-ex-edogawa');
 assert.equal(meta.eligible,p.name!=='江戸川',p.name);
 assert.equal(meta.excluded,p.name==='江戸川',p.name);
 assert.equal(meta.result_data_used,false);
 assert.equal(meta.pre_cutoff_only,true);
 assert.deepEqual(meta.historical_winning_method_share_pct,{
  escape:h[p.name][0],makuri:h[p.name][1],sashi:h[p.name][2],makurizashi:h[p.name][3]
 });
 assert.equal(meta.head_course_multipliers.length,6);
 assert.equal(meta.attack_evidence.length,5);
 assert.ok(bridge.validBets(v14.bets),p.name);
 assert.ok(bridge.validBets(v14.venue_tactics_ab.control_bets),p.name);
 assert.ok(bridge.validBets(v14.venue_tactics_ab.prior_bets),p.name);
 assert.equal(v14.venue_tactics_ab.same_inputs_except_venue_tactics,true);
 assert.equal(v14.venue_tactics_ab.generated_pre_cutoff,true);
 assert.deepEqual(v14.venue_tactics_ab.control_bets,
  bridge.run({...f,venue_tactics_trial:true,venue_tactics_disabled:true}).bets);
 assert.deepEqual(v14.venue_tactics_ab.prior_bets,
  bridge.run({...f,postrace_conditional_trial:true}).bets);
 if(p.name==='江戸川'){
   assert.equal(meta.applied,false);
   assert.deepEqual(v14.bets,v14.venue_tactics_ab.prior_bets,
     '江戸川 must not change the v1.3 bet structure');
 }
}
const toda=bridge.run({...fixture('戸田'),venue_tactics_trial:true});
const tokuyama=bridge.run({...fixture('徳山'),venue_tactics_trial:true});
assert.ok(toda.venue_tactics_v2.head_course_multipliers[2]>1,
 'TODA stronger past makuri share should require a fast attacker');
assert.ok(tokuyama.venue_tactics_v2.head_course_multipliers[2]<1,
 'TOKUYAMA historical makuri share lower than cross-venue baseline');
const noSignal=fixture('戸田','baseline');
noSignal.racers.forEach(r=>r.average_start_timing=.17);
const absence=bridge.run({...noSignal,venue_tactics_trial:true});
assert.ok(absence.venue_tactics_v2.attack_evidence.every(e=>!e.evidence));
assert.ok(absence.venue_tactics_v2.head_course_multipliers.every(n=>n===1));
const missing=fixture('戸田');missing.venue_profile=null;
const ignored=bridge.run({...missing,venue_tactics_trial:true});
assert.equal(ignored.venue_tactics_v2.eligible,false);
assert.ok(ignored.venue_tactics_v2.head_course_multipliers.every(n=>n===1));
const fakeResult=bridge.run({...fixture('戸田'),venue_tactics_trial:true,
 result:{finish:'3-4-1'},payout:22000,odds:{foo:123},
 actual_race_st:{1:.01,3:.03}});
assert.deepEqual(fakeResult,toda,'no actual racing data leaks into venue prediction');
const swapped=fixture('戸田');swapped.racers[2].course=4;swapped.racers[3].course=3;
const positionChanged=bridge.run({...swapped,venue_tactics_trial:true});
assert.ok(positionChanged.venue_tactics_v2.attack_evidence.some(x=>x.course===3),
 'actual entry, not frame, is the feature input');
const f=fixture('戸田');f.racers[2].exhibition_st=-.03;
const nullST=fixture('戸田');nullST.racers[2].exhibition_st=null;
assert.deepEqual(bridge.run({...f,venue_tactics_trial:true}).bets,
 bridge.run({...nullST,venue_tactics_trial:true}).bets,
 'exhibition F cannot become a fictitious fast legal start');
console.log('Venue v1.4: 24 documented/23 eligible, unique per-venue method priors, no 江戸川, pre-cutoff/result-blind, full A/B, 4-12 tickets/50k PASS');
