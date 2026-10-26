 'use strict';
const assert=require('node:assert/strict');
require('../four-factor.js');require('../tactical-1m.js');
const api=globalThis.BoatTacticalModel;
const fixture=()=>({venue:'大村',phase:'baseline',frozen_at_utc:'2026-10-27T00:00:00Z',
 racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,national_win_rate:5,average_start_timing:.17,motor_top_2_percent:30}))});
const policy=r=>api.forecastFourFactorOpen(r).metadata.four_factor.chaser_policy;
const second=(p,h,c)=>p.second_by_head.find(x=>x.head_course===h).candidates.find(x=>x.course===c).relative_share;
const third=(p,h,s,c)=>p.third_by_pair.find(x=>x.head_course===h&&x.second_course===s).candidates.find(x=>x.course===c).relative_share;
const equal=policy(fixture());
assert.equal(equal.fixed_neighbor_bonus,false);assert.equal(equal.legacy_ticket_rescue,false);
assert.equal(equal.second_by_head.length,6);assert.equal(equal.third_by_pair.length,30);
for(const row of [...equal.second_by_head,...equal.third_by_pair]){
 assert.ok(Math.abs(row.candidates.reduce((n,x)=>n+x.relative_share,0)-1)<1e-12);
 assert.ok(row.candidates.every(x=>x.relative_share>0));
}
// With identical ability, the only course effect is the small unconditional
// prior; changing the winning course cannot invent a special follower bonus.
assert.ok(Math.abs(second(equal,2,3)/second(equal,2,6)-1.06/.94)<1e-12);
assert.ok(Math.abs(second(equal,4,3)/second(equal,4,6)-1.06/.94)<1e-12);
const outer=fixture();outer.racers[5].national_win_rate=9;outer.racers[5].motor_top_2_percent=65;
const po=policy(outer);
assert.ok(second(po,2,6)>second(po,2,1));assert.ok(second(po,2,6)>second(po,2,3));
assert.ok(third(po,2,1,6)>third(po,2,1,3));
const inner=fixture();inner.racers[0].national_win_rate=9;inner.racers[0].motor_top_2_percent=65;
const pi=policy(inner);
assert.ok(second(pi,4,1)>second(pi,4,5));assert.ok(second(pi,4,1)>second(pi,4,6));
assert.ok(third(pi,4,5,1)>third(pi,4,5,6));
const result=api.forecastFourFactorOpen(outer);
assert.match(globalThis.BoatFourFactor.panel({four_factor:result.metadata.four_factor}),/頭ごとの2着候補/);
assert.match(globalThis.BoatFourFactor.panel({four_factor:result.metadata.four_factor}),/残り5艇を毎回評価/);
assert.equal(result.model,'four-factor-v1.1-untrained');assert.deepEqual(result.role_changes,[]);
assert.ok(result.bets.every(x=>x.conditional_reason.includes('攻め方未確定')));
assert.equal(result.bets.reduce((n,x)=>n+x.virtual_yen,0),50000);
const entry=fixture();[entry.racers[0].course,entry.racers[5].course]=[6,1];
assert.equal(policy(entry).second_by_head.find(x=>x.head_course===2).candidates.find(x=>x.course===6).lane,1);
assert.deepEqual(policy({...outer,result:{finish:'2-6-1'},payout:99999}),po);
// Earlier frozen model algorithms must remain byte-identical to the base.
const historical=[];
for(let i=0;i<20;i++){
 const f=fixture();f.racers.forEach((r,j)=>{r.national_win_rate=3+(i+j)%6;r.average_start_timing=.1+((i+j)%12)/100;r.motor_top_2_percent=20+((i*7+j*11)%50);});
 for(const method of ['forecastOutsideStart','forecastWakeIntegrated','forecastFourFactor'])
  historical.push(api[method](f));
}
console.log('Open chasers: full coverage, ability reversals, bounded geometry, no rescue, entry mapping, 60 historical outputs unchanged: PASS');

// Baseline captured from a4e4abf before v1.1; no git refs required in shallow CI.
assert.equal(require('node:crypto').createHash('sha256').update(JSON.stringify(historical)).digest('hex'),'5e45269e2ca919fe969ad3245bca1241e012e7efbd41ec79bc79f53bff118e26');
