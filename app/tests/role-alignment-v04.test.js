'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const ctx={window:{},Number,Intl};
vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),ctx);
const T=ctx.window.BoatTacticalModel;
function base(){
 return {
  venue:'鳴門',cutoff_jst:'11:30',frozen_at_utc:'2026-10-24T01:00:00Z',
  weather_used:{wind_speed:2},venue_profile:{course1_reference_rate:.475},
  racers:Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,name:'選手'+(i+1),
   national_win_rate:[6.0,6.3,6.0,6.7,7.0,5.7][i],
   motor_top_2_percent:[35,38,36,42,47,31][i],
   average_start_timing:[.16,.14,.16,.13,.11,.18][i],
   exhibition_time:[6.77,6.72,6.76,6.66,6.57,6.85][i]
  })),
  bets:['1-2-3','1-3-2','2-1-3','3-1-2'].map(c=>({
   combination:c,virtual_yen:12500
  }))
 };
}
function validate(r,seed){
 const untouched=JSON.stringify(r);
 const legacy=T.forecast(r),v4=T.forecastRoleAware(r);
 assert.equal(legacy.model,'tactical-1m-conditional-v0.1-untrained','legacy model stays identified as v0.1');
 assert.equal(v4.model,'tactical-role-consistency-v0.4-untrained');
 assert.equal(JSON.stringify(r),untouched,'never mutate fixed tickets or race record');
 assert.equal(v4.is_frozen,false);
 assert.ok(v4.bets.length>=4&&v4.bets.length<=12);
 assert.equal(new Set(v4.bets.map(x=>x.combination)).size,v4.bets.length);
 assert.equal(v4.bets.reduce((s,x)=>s+x.virtual_yen,0),50000);
 assert.equal(legacy.bets.reduce((s,x)=>s+x.virtual_yen,0),50000);
 assert.deepEqual(JSON.parse(JSON.stringify(legacy.head_course_shares)),
   JSON.parse(JSON.stringify(v4.head_course_shares)),'same first-place model and course mapping');
 const sums=[0,0,0];
 for(let lane=1;lane<=6;lane++){
  const z=v4.role_coverage[lane];
  assert.ok(z,'every boat must have role diagnostics '+lane);
  for(const [j,key] of ['first','second','third'].entries()){
   assert.ok(z[key]>=0&&z[key]<=1);
   sums[j]+=z[key];
  }
  const hits=[0,1,2].map(i=>v4.bets.filter(b=>Number(b.combination.split('-')[i])===lane).length);
  assert.deepEqual([z.headTickets,z.secondTickets,z.thirdTickets],hits);
  const share=v4.head_course_shares.find(x=>x.lane===lane).relative_share;
  assert.ok(Math.abs(share-z.first)<=.00015,'first role marginal matches ranking');
 }
 sums.forEach(x=>assert.ok(Math.abs(x-1)<.002,'role marginal sums to one across six boats'));
 for(const change of v4.role_changes){
  assert.ok(v4.bets.some(x=>x.combination===change.combination));
  assert.ok(change.role==='head'||change.role==='second');
  if(change.role==='second'){
   assert.ok(v4.role_coverage[change.lane].second>=.1199,'no second-place blanket quota');
   const candidates=[...v4.head_course_shares].sort((a,b)=>b.relative_share-a.relative_share);
   assert.ok(candidates.slice(0,3).some(x=>x.lane===change.lane));
  }
 }
 assert.ok(v4.bets.every(b=>b.combination.split('-').length===3));
 return v4;
}
const original=base(),v4=validate(original,0);
const five=base();
five.racers[4]={...five.racers[4],national_win_rate:9,motor_top_2_percent:88,
 average_start_timing:.09,exhibition_time:6.44};
five.racers[0]={...five.racers[0],national_win_rate:3.5,motor_top_2_percent:18};
const strongFive=validate(five,1);
assert.ok(strongFive.role_coverage[5].first>v4.role_coverage[5].first,
 'strong #5 receives a stronger first place role score');
const old=T.forecast(five);
assert.equal(old.model,'tactical-1m-conditional-v0.1-untrained');
assert.equal(strongFive.role_coverage[5].secondTickets,
 strongFive.bets.filter(x=>x.combination.split('-')[1]==='5').length);
const veryWeak=base();
veryWeak.racers[4]={...veryWeak.racers[4],
 national_win_rate:2.0,motor_top_2_percent:5,average_start_timing:.29,exhibition_time:7.20};
const weakFive=validate(veryWeak,2);
assert.ok(weakFive.role_coverage[5].first<strongFive.role_coverage[5].first);
assert.ok(weakFive.role_changes.every(x=>!(x.role==='second'&&x.lane===5)),
 'a weak #5 cannot enter 2nd-place just for a quota');
const swapped=base();swapped.racers[0].course=5;swapped.racers[4].course=1;
validate(swapped,3);
for(let seed=0;seed<24;seed++){
 const r=base();
 r.racers=r.racers.map((x,i)=>({...x,
  national_win_rate:3+((i*13+seed*7)%68)/10,
  motor_top_2_percent:10+((i*19+seed*13)%75),
  average_start_timing:.09+((i*7+seed*5)%20)/100,
  exhibition_time:6.4+((i*7+seed*3)%65)/100
 }));
 validate(r,seed+4);
}
const app=fs.readFileSync('app/app.js','utf8');
assert.match(app,/function roleConsistencyPanel\(r,trial\)/);
assert.match(app,/BoatTacticalModel\?\.forecastRoleAware\(r\)/);
assert.match(app,/正式固定の買い目は<strong>別モデル<\/strong>/);
assert.match(app,/固定買い目<br>1着\/2着\/3着/);
assert.match(app,/戦法試験買い目<br>1着\/2着\/3着/);
console.log('Role-aware v0.4: independent role shares, conditional second branches, unchanged historical trials: PASS');
