'use strict';
// Venue-surface trial: 23 venues enrolled; Edogawa explicitly excluded.
// Model differences must arise from pre-cutoff ST and movement evidence only.
const assert=require('node:assert/strict');
const fs=require('node:fs');
require('../four-factor.js');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const profiles=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;
const profile=name=>profiles.find(p=>p.name===name);
const fixture=name=>({
 venue:name,phase:'baseline',frozen_at_utc:'2026-10-27T00:00:00Z',
 venue_profile:profile(name),weather_used:{wind_speed:2},
 racers:Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,national_win_rate:5.5,motor_top_2_percent:35,
  average_start_timing:[.17,.18,.11,.17,.17,.17][i],
  exhibition_st:null,exhibition_time:null,racer_context:{values:{national_top3:50}}
 }))
});
assert.equal(profiles.length,24);
for(const p of profiles){
 const r=bridge.run(fixture(p.name));
 assert.equal(r.venue_surface_v1.excluded,p.name==='江戸川');
 assert.equal(r.venue_surface_v1.eligible,p.name!=='江戸川',
   'new 23-venue surface trial must NOT include Edogawa');
 assert.equal(r.bets.reduce((s,x)=>s+x.virtual_yen,0),50000);
 assert.equal(new Set(r.bets.map(x=>x.combination)).size,r.bets.length);
 if(p.name==='江戸川'){
  assert.equal(r.venue_surface_v1.applied,false);
  assert.equal(r.venue_surface_ab,null);
 }
}
const toda=fixture('戸田');
const active=bridge.run(toda);
assert.equal(active.venue_surface_v1.applied,true,'strong center ST edge should trigger documented Toda hypothesis');
assert.ok(active.venue_surface_v1.head_course_multipliers[2]>1);
assert.ok(active.venue_surface_ab,'same-time surface-disabled counterfactual required');
assert.ok(bridge.validBets(active.venue_surface_ab.control_bets));
assert.ok(bridge.validBets(active.venue_surface_ab.trial_bets));
const disabled=bridge.run({...toda,surface_trial_disabled:true});
assert.equal(disabled.venue_surface_v1.applied,false);
assert.deepEqual(disabled.bets,active.venue_surface_ab.control_bets);
const noGap=fixture('戸田');
noGap.racers.forEach(r=>r.average_start_timing=.17);
const noEvidence=bridge.run(noGap);
assert.equal(noEvidence.venue_surface_v1.applied,false,
 'mere location must not trigger bonus without positive ST evidence');
const fukuoka=bridge.run(fixture('福岡'));
assert.equal(fukuoka.venue_surface_v1.applied,true,'official Fukuoka 1M layout tested only with ST evidence');
const unknown=bridge.run({...toda,venue_profile:null});
assert.equal(unknown.venue_surface_v1.eligible,false,'missing/invalid profile cannot silently infer a venue adjustment');
const outcome=bridge.run({...toda,result:{finish:'6-5-4'},payout:12345,odds:{x:20}});
assert.deepEqual(outcome,active,'result and odds cannot change the pre-cutoff venue trial');
console.log('Edogawa-excluded 23-venue surface trial, evidence gating, browser inputs, A/B and allocation: PASS');
