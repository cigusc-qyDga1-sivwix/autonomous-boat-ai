'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const win={};vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),{window:win,Number,Intl});
const model=win.BoatTacticalModel;
const mk=(venue='唐津')=>({
 venue,phase:'exhibition',weather_used:{wind_speed:2},
 frozen_at_utc:'2026-10-24T04:50:00Z',
 racers:[5.6,5.8,5.8,8.9,9.2,6.6].map((n,i)=>({
  lane:i+1,course:i+1,national_win_rate:n,
  motor_top_2_percent:[24,32,31,77,83,39][i],
  average_start_timing:[.18,.17,.17,.095,.095,.16][i],
  exhibition_time:[6.82,6.80,6.81,6.53,6.54,6.77][i],
  original_exhibition:{lap_time:[37.5,37.6,37.4,36.5,36.54,37.2][i],
   turn_time:[5.9,6,5.95,5.5,5.54,5.85][i],
   straight_time:[7.3,7.4,7.35,6.85,6.87,7.25][i]}
 })),
 bets:['1-2-3','1-3-2','2-1-3','3-1-2'].map(x=>({combination:x,virtual_yen:12500}))
});
function audit(input){
 const saved=JSON.stringify(input);
 const old=model.forecastRoleAware(input),trial=model.forecastOutsideRole(input);
 assert.equal(trial.model,'tactical-outside-role-v0.5-untrained');
 assert.equal(old.model,'tactical-role-consistency-v0.4-untrained');
 assert.equal(JSON.stringify(input),saved,'never alter fixed SHA or bets');
 assert.equal(trial.is_frozen,false);
 assert.equal(trial.bets.reduce((sum,b)=>sum+b.virtual_yen,0),50000);
 assert.ok(trial.bets.length>=4&&trial.bets.length<=12);
 assert.equal(new Set(trial.bets.map(b=>b.combination)).size,trial.bets.length);
 assert.equal(trial.metadata.outside_v05.conditional_outside_evidence.length,3);
 for(const signal of trial.metadata.outside_v05.conditional_outside_evidence){
  assert.ok([4,5,6].includes(signal.course));
  assert.ok(signal.confidence>=0&&signal.confidence<=.7);
  if(signal.following_supported)assert.ok(signal.confidence>=.10);
 }
 for(let lane=1;lane<=6;lane++){
  const x=trial.role_coverage[lane];
  assert.ok(x.first>=0&&x.first<=1&&x.second>=0&&x.second<=1&&x.third>=0&&x.third<=1);
  [x.headTickets,x.secondTickets,x.thirdTickets].forEach(z=>assert.ok(Number.isInteger(z)&&z>=0));
 }
 assert.ok(trial.bets.every(x=>x.combination.split('-').length===3));
 const noResult={...input,result:{finish:'5-6-4',decision:'まくり差し'},
  payout:{finish:'5-6-4',yen_per_100:121000},official_results:{'test':'5-6-4'}};
 assert.deepEqual(JSON.parse(JSON.stringify(model.forecastOutsideRole(noResult))),
  JSON.parse(JSON.stringify(trial)),'post race information must not enter model');
 return {trial,old};
}
const best=audit(mk());
assert.equal(best.trial.metadata.outside_v05.venue_specific_prior,true);
assert.match(best.trial.metadata.outside_v05.reference_source,/karatsu/);
assert.equal(best.trial.metadata.outside_v05.prior_blend,.35);
const c4=best.trial.head_course_shares.find(r=>r.course===4).relative_share;
const old4=best.old.head_course_shares.find(r=>r.course===4).relative_share;
assert.ok(c4>old4,'fast 4th course must be penalized less when attack supported');
const signals=best.trial.metadata.outside_v05.conditional_outside_evidence;
assert.ok(signals.find(x=>x.course===4).attack);
assert.ok(signals.find(x=>x.course===4).following_supported,'5th should be able to follow a proven 4th course attack');
assert.ok(best.trial.role_coverage[5].second>=best.old.role_coverage[5].second,
 '5th-course relative 2nd-place strength should respond to fast 4th attack');
const weak=mk('住之江');
weak.racers=weak.racers.map((x,i)=>i>=3?{...x,
 national_win_rate:3,motor_top_2_percent:10,
 average_start_timing:.29,exhibition_time:7.55,
 original_exhibition:{lap_time:39.4,turn_time:7.4,straight_time:8.7}}:x);
const poor=audit(weak);
assert.equal(poor.trial.metadata.outside_v05.venue_specific_prior,false);
assert.equal(poor.trial.metadata.outside_v05.reference_source,null);
assert.equal(poor.trial.metadata.outside_v05.conditional_outside_evidence.every(x=>!x.attack),true,
 'weak outside boats cannot have an attack flag');
assert.equal(poor.trial.role_changes.filter(x=>x.role==='second'&&x.lane>=4).length,0,
 'weak outside must never receive forced second-place quota');
for(const venue of ['唐津','びわこ','福岡','鳴門','大村']){
 for(let seed=0;seed<8;seed++){
  const r=mk(venue);
  r.racers=r.racers.map((x,i)=>({...x,national_win_rate:3+((i*17+seed*9)%67)/10,
   motor_top_2_percent:12+((i*13+seed*11)%72),
   average_start_timing:.09+((i*5+seed*7)%19)/100,
   exhibition_time:6.4+((i*13+seed*5)%65)/100}));
  audit(r);
 }
}
assert.equal(Object.keys(model.OUTSIDE_VENUE_COURSES).length,3);
assert.match(fs.readFileSync('app/app.js','utf8'),/forecastOutsideRole\(r\)/);
assert.match(fs.readFileSync('app/app.js','utf8'),/攻め条件あり/);
console.log('Boat outside course v0.5: conditional course-4 attack, 5 follow, no blanket outside boost, immutable old models: PASS');
