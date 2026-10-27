'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
require('../four-factor.js');require('../tactical-1m.js');
const api=globalThis.BoatTacticalModel;
// Frozen pre-cutoff inputs only; no results/payouts enter either engine.
const live=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
let changed=0;
for(const r of live.forecast_races){
 const f={venue:r.venue,phase:r.phase,racers:r.racers,weather_used:r.weather_used,venue_profile:r.venue_profile,frozen_at_utc:r.frozen_at_utc};
 const before=JSON.stringify(f),old=api.forecastFourFactorOpen(f),trial=api.forecastFourFactorCoverage(f);
 assert.equal(JSON.stringify(f),before);
 assert.deepEqual(old.head_course_shares,trial.head_course_shares);
 assert.deepEqual(old.metadata.four_factor.rows,trial.metadata.four_factor.rows);
 assert.deepEqual(old.metadata.four_factor.chaser_policy,trial.metadata.four_factor.chaser_policy);
 assert.equal(old.bets.length,trial.bets.length);
 assert.equal(new Set(trial.bets.map(x=>x.combination)).size,trial.bets.length);
 assert.equal(trial.bets.reduce((n,x)=>n+x.virtual_yen,0),50000);
 const p=trial.metadata.four_factor.ticket_policy;
 for(const course of p.selected_head_courses)assert.ok(trial.bets.filter(b=>b.head_course===course).length>=2);
 assert.deepEqual(api.forecastFourFactorCoverage({...f,result:{finish:'6-5-4'},payout:99999}),trial);
 if(JSON.stringify(old.bets)!==JSON.stringify(trial.bets))changed++;
 const bridge=require('../../scripts/main_four_factor_bridge.js').run({...f,head_coverage_trial:true});
 assert.equal(bridge.model_version,'four-factor-v1.2-head-coverage-untrained');
 assert.deepEqual(bridge.bets,trial.bets);
 assert.deepEqual(bridge.head_coverage_control.bets,old.bets);
}
assert.ok(changed>0);
// Target selection responds to each distribution, no compulsory 2/3 heads.
const candidates=[];for(let h=1;h<=6;h++)for(let j=0;j<3;j++)candidates.push({headCourse:h,combination:`${h}-${j}`,pseudo:(7-h)*.01-j*.001});
assert.deepEqual(api.headCoveragePicks(candidates,8,[.85,.05,.04,.03,.02,.01]).policy.selected_head_courses,[1]);
assert.deepEqual(api.headCoveragePicks(candidates,8,[.45,.30,.13,.06,.04,.02]).policy.selected_head_courses,[1,2,3]);
assert.deepEqual(api.headCoveragePicks(candidates,8,[.25,.24,.23,.22,.04,.02]).policy.selected_head_courses,[1,2,3,4]);
assert.equal(api.headCoveragePicks(candidates,4,[.25,.24,.23,.22,.04,.02]).picks.length,4);
console.log(`Head coverage: ${live.forecast_races.length} races, ${changed} changed ticket sets; scores/count/stake preserved, old control and adaptive selection: PASS`);
