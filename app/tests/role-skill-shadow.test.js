'use strict';
const assert=require('node:assert/strict');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const skill=require('../role-skill-shadow.js');
const racers=Array.from({length:6},(_,i)=>({
 lane:i+1,course:i+1,national_win_rate:5.4+(i===3?1.3:i*.13),
 average_start_timing:.16+i*.008,motor_top_2_percent:35+i,
 exhibition_time:6.80+i*.02,exhibition_st:.13+i*.01,
 racer_context:{values:{national_top3:48+i*5,local_win:5.0,
  frame_win:5.0,frame_st:.17,frame_start_order:6-i,motor_top3:45}}
}));
const input={venue:'唐津',phase:'exhibition',frozen_at_utc:'2026-10-31T04:00:00Z',
 weather_used:{wind_speed:2,wave_height:1},racers,
 venue_profile:{name:'唐津',code:'23',tactical_focus:'2差し/4カド',course1_reference_rate:.557}};
const frozen=JSON.stringify(input);
const control=bridge.run({...input,venue_tactics_trial:true});
assert.equal(Object.hasOwn(control,'role_skill_shadow'),false,'off by default');
const enabled=bridge.run({...input,venue_tactics_trial:true,role_skill_shadow_trial:true});
assert.deepEqual(enabled.bets,control.bets,'formal bets must never change');
assert.equal(JSON.stringify(input),frozen,'source must stay immutable');
const role=enabled.role_skill_shadow;
assert.equal(role.version,'racer-role-suitability-shadow-v0.1','historical variant stays available');
assert.equal(role.status,'ready');
assert.equal(role.generated_pre_cutoff,true);
assert.equal(role.no_additional_stake,true);
assert.equal(role.result_data_used,false);
assert.equal(role.roles.length,6);
assert.equal(role.control_point_count,enabled.bets.length);
assert.equal(role.bets.length,enabled.bets.length);
assert.equal(new Set(role.bets.map(x=>x.combination)).size,role.bets.length);
assert.equal(role.bets.reduce((s,x)=>s+x.virtual_yen,0),50000);
assert.deepEqual(role.bets.map(x=>x.virtual_yen).sort((a,b)=>a-b),
 enabled.bets.map(x=>x.virtual_yen).sort((a,b)=>a-b),'same stake distribution');
const poisoned=bridge.run({...input,role_skill_shadow_trial:true,venue_tactics_trial:true,
 result:{finish:'6-5-4'},official_results:{payout:9999999},odds:{'1-2-3':10000}});
assert.deepEqual(poisoned.role_skill_shadow,role,'no outcomes or odds leak into shadow');
const absent=structuredClone(input);
absent.racers.forEach(r=>r.racer_context=null);
const without=skill.run(absent,control.bets);
assert.equal(without.roles.filter(x=>x.top3_residual_used).length,0);
assert.ok(without.roles.every(x=>x.second_proxy===1&&x.third_proxy===1),
 'missing data cannot create artificial racer skill');
const swapped=structuredClone(input);
swapped.racers[0].course=4;swapped.racers[3].course=1;
const swappedResult=skill.run(swapped,control.bets);
assert.equal(swappedResult.roles[0].frame_start_order_used,false);
assert.equal(swappedResult.roles[3].frame_start_order_used,false);
assert.equal(role.roles.filter(x=>x.measured_second_finish_rate||x.measured_third_finish_rate).length,0);
const factor=require('../four-factor.js');
const html=factor.panel({four_factor:enabled.four_factor,role_skill_shadow:role});
assert.match(html,/選手の2・3着適性/);
assert.match(html,/正式予想・正式収支には加算しません/);
assert.match(html,/試験買い目/);
assert.throws(()=>skill.run({...input,racers:[...input.racers.slice(0,5),input.racers[0]]},control.bets));
const headSignature=bets=>Array.from({length:6},(_,i)=>bets
 .filter(b=>Number(b.combination[0])===i+1).map(b=>b.virtual_yen).sort((a,b)=>a-b));
// A low-ranked head can be intentionally retained by the main coverage policy.
// Global re-ranking loses it even when the head score itself never changes.
const broadControl=Array.from({length:6},(_,i)=>[
 {combination:[i+1,(i+1)%6+1,(i+2)%6+1].join('-'),virtual_yen:i===0?5000:4000},
 {combination:[i+1,(i+2)%6+1,(i+1)%6+1].join('-'),virtual_yen:i===0?5000:4000}
]).flat();
assert.notDeepEqual(headSignature(skill.run(input,broadControl).bets),headSignature(broadControl),
 'fixture must expose the historical global-rerank failure');
const preserved=skill.run(input,broadControl,{preserveHeadCoverage:true});
assert.equal(preserved.version,'racer-role-suitability-shadow-v0.2-head-preserved');
assert.deepEqual(headSignature(preserved.bets),headSignature(broadControl),
 'each original head keeps its ticket count and exact stake distribution');
assert.equal(new Set(preserved.bets.map(b=>b.combination)).size,broadControl.length);
const viaBridge=bridge.run({...input,venue_tactics_trial:true,role_skill_shadow_trial:true,
 role_skill_head_preserved_trial:true});
assert.deepEqual(viaBridge.bets,control.bets,'v0.2 cannot alter the main forecast');
assert.deepEqual(headSignature(viaBridge.role_skill_shadow.bets),headSignature(control.bets));
const v2Poison=bridge.run({...input,venue_tactics_trial:true,role_skill_shadow_trial:true,
 role_skill_head_preserved_trial:true,result:{finish:'6-5-4'},odds:{'6-5-4':10000}});
assert.deepEqual(v2Poison.role_skill_shadow,viaBridge.role_skill_shadow);
console.log('Role-skill shadow: isolation, provenance, guards, matching point/stake, no-result leakage, role evidence PASS');
