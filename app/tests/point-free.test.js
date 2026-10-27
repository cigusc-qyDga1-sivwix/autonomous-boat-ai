'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const bridge=require('../../scripts/main_point_free_bridge.js');
const api=globalThis.BoatTacticalModel;
const combos=[];for(let a=1;a<=6;a++)for(let b=1;b<=6;b++)for(let c=1;c<=6;c++)if(new Set([a,b,c]).size===3)combos.push(`${a}-${b}-${c}`);
// The number of supported evaluations determines the number of picks, including
// values below 4 and above 12/18. No rounding to preset ticket or head quotas.
for(const n of [1,2,3,5,17,19,41,73,120]){
 const candidates=combos.map((combination,i)=>({combination,pseudo:i<n?1:0,headCourse:+combination[0]}));
 const r=api.pointFreePicks(candidates);assert.equal(r.picks.length,n);
 assert.equal(r.policy.point_target,null);assert.equal(r.policy.head_quota,null);
 assert.equal(r.policy.candidates.filter(c=>c.selected).length,n);
 const reversed=api.pointFreePicks([...candidates].reverse());
 assert.deepEqual(r.picks.map(c=>c.combination).sort(),reversed.picks.map(c=>c.combination).sort());
}
assert.throws(()=>api.pointFreePicks([]));
const live=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const counts=new Set();
for(const r of live.forecast_races){
 const f={venue:r.venue,phase:r.phase,racers:r.racers,weather_used:r.weather_used,venue_profile:r.venue_profile,frozen_at_utc:r.frozen_at_utc};
 const input=JSON.stringify(f),a=bridge.run(f),b=api[f.venue==='江戸川'?'forecastFourFactorConditional':'forecastFourFactorVenueAware'](f);
 assert.equal(JSON.stringify(f),input);assert.ok(bridge.validBets(a.bets));
 assert.deepEqual(a.head_course_shares,b.head_course_shares);
 assert.deepEqual(a.four_factor.rows,b.metadata.four_factor.rows);
 assert.deepEqual(a.four_factor.chaser_policy,b.metadata.four_factor.chaser_policy);
 assert.deepEqual(a.point_free_control.bets,b.bets);
 const p=a.four_factor.ticket_policy;
 assert.equal(p.selected_count,a.bets.length);assert.equal(p.candidates.length,120);
 assert.deepEqual(p.candidates.filter(c=>c.selected).map(c=>c.combination),a.bets.map(c=>c.combination));
 assert.equal(a.point_free_provenance.trajectory_learning_completed,false);
 if(f.venue==='江戸川')assert.equal(a.venue_tactics_v2,null);
 assert.deepEqual(bridge.run({...f,result:{finish:'6-5-4'},payout:999999,odds:999}),a);
 assert.match(globalThis.BoatFourFactor.panel({four_factor:a.four_factor}),/点数枠なしv1.5/);
 assert.doesNotMatch(globalThis.BoatFourFactor.panel({four_factor:a.four_factor}),/累計80%/);
 counts.add(a.bets.length);
}
assert.ok(counts.size>5);assert.ok([...counts].some(n=>n>18));
// Largest ticket domains accept 100-yen increments without fake/duplicate bets.
for(const n of [1,3,19,120]){
 const bs=combos.slice(0,n).map((combination,i)=>({combination,virtual_yen:100+(i===0?50000-n*100:0)}));
 assert.ok(bridge.validBets(bs));assert.ok(!bridge.validBets([...bs,bs[0]]));
}
console.log(`Point-free invariants: ${live.forecast_races.length} saved inputs, counts ${[...counts].sort((a,b)=>a-b).join(',')}: PASS`);
