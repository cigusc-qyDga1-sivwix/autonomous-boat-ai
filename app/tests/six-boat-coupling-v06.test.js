'use strict';
/* Shadow-v0.6: causal branches are pre-race hypotheses, not race playback. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const w={};vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),{window:w,Number,Intl});
const T=w.BoatTacticalModel;
const racers=Array.from({length:6},(_,i)=>({
 lane:i+1,course:i+1,national_win_rate:[4.8,4.6,4.5,8.8,7.5,5.6][i],
 motor_top_2_percent:[30,25,25,78,65,43][i],
 average_start_timing:[.19,.19,.18,.08,.11,.16][i],
 exhibition_st:[.18,.18,.17,.06,.09,.14][i],
 exhibition_time:[6.85,6.85,6.86,6.56,6.61,6.77][i],
 original_exhibition:{}
}));
const source={venue:'鳴門',racers,weather_used:{wind_speed:2}};
const immutable=JSON.stringify(source);
const control=T.forecastOutsideRole(source),coupled=T.forecastCoupled(source);
assert.equal(JSON.stringify(source),immutable);
assert.equal(control.model,'tactical-outside-role-v0.5-untrained');
assert.equal(coupled.model,'tactical-six-boat-coupling-v0.6-untrained');
assert.equal(coupled.metadata.coupled_v06.calibrated,false);
assert.equal(coupled.metadata.coupled_v06.interaction_graph.length,6);
const fourth=coupled.metadata.coupled_v06.interaction_graph[3];
assert.equal(fourth.head_course,4);
assert.equal(fourth.head_lane,4);
assert.equal(fourth.follower_course,5);
assert.equal(fourth.follower_lane,5);
assert.ok(fourth.pressure>.1,'strong 4C must have a credible attacking hypothesis');
assert.equal(fourth.inside.length,3);
assert.ok(fourth.inside.every(x=>x.risk>=0&&x.risk<=.9));
assert.ok(coupled.role_coverage[5].second>control.role_coverage[5].second,
 'strong outside attacker should improve fifth-boat follow in the conditional 2nd branch');
assert.ok(coupled.bets.some(x=>x.conditional_reason.includes('仮説')));
const weak={...source,racers:racers.map((r,i)=>i===3?{...r,
 national_win_rate:3.0,motor_top_2_percent:10,average_start_timing:.28,
 exhibition_st:.3,exhibition_time:7.2}:r)};
const lower=T.forecastCoupled(weak).metadata.coupled_v06.interaction_graph[3];
assert.equal(lower.pressure,0,'weak 4C must not create a fictional attack');
assert.ok(lower.inside.every(x=>x.risk===0));
const modified={...source,racers:racers.map((r,i)=>({...r,course:[2,4,5,1,6,3][i]}))};
const changed=T.forecastCoupled(modified);
assert.equal(changed.metadata.coupled_v06.interaction_graph[3].head_lane,2,
 '4C attack must come from the actual entry lane');
assert.equal(changed.metadata.coupled_v06.interaction_graph[3].follower_lane,3);
assert.throws(()=>T.forecastCoupled({...source,racers:racers.map((r,i)=>({...r,course:i===0?2:i===1?2:i+1}))}),
 /実進入が未確認/);
const settled=T.forecastCoupled({...source,official_results:{'鳴門|1':{finish:'4-5-6'}},
 result:{finish:'5-1-2'},payout:{yen_per_100:9000},finish:'4-1-5'});
assert.equal(JSON.stringify(settled),JSON.stringify(coupled),
 'outcomes, payouts and settlement MUST have no effect on pre-cutoff predictions');
for(const m of [control,coupled]){
 assert.ok(m.bets.length>=4&&m.bets.length<=12);
 assert.equal(m.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
 assert.equal(new Set(m.bets.map(b=>b.combination)).size,m.bets.length);
 assert.ok(m.bets.every(b=>/^\d-\d-\d$/.test(b.combination)));
}
assert.equal(T.forecastOutsideRole(source).model,control.model,'older trial remains callable');
console.log('BOAT LAB six-boat directed coupling / no leakage / entry / ticket invariants: PASS');
