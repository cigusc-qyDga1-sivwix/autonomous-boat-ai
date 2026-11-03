'use strict';
const assert=require('node:assert/strict');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const shadow=require('../counterplay-shadow.js');
function fixture(){return {venue:'唐津',phase:'exhibition',frozen_at_utc:'2026-11-04T00:00:00Z',
 cutoff_iso_jst:'2026-11-04T10:00:00+09:00',venue_tactics_trial:true,
 racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,national_win_rate:i===3?6.3:6,
 motor_top_2_percent:40,average_start_timing:.15,exhibition_st:.15,exhibition_time:i===3?6.7:6.9}))};}
const input=fixture(),copy=JSON.stringify(input),main=bridge.run(input);
assert.equal(Object.hasOwn(main,'counterplay_shadow'),false);
const enabled=bridge.run({...input,counterplay_shadow_trial:true}),s=enabled.counterplay_shadow;
assert.equal(s.status,'ready');assert.equal(s.active_duels,1);
assert.deepEqual(enabled.bets,main.bets);assert.equal(JSON.stringify(input),copy);
const duel=s.duels.find(d=>d.attacker_lane===4);
assert.equal(duel.defender_lane,3);assert.equal(duel.resistance_plausible,true);
assert.deepEqual(duel.branches.map(b=>b.kind),['attack_succeeds','inside_holds','attack_fails_to_place','contested_third_party']);
for(const branch of duel.branches)assert.ok(branch.alternatives.length);
for(const a of duel.branches.find(b=>b.kind==='attack_fails_to_place').alternatives)
 assert.ok(!a.combination.split('-').includes('4'),'failed attacker must not be forced into podium');
for(const a of duel.branches.find(b=>b.kind==='contested_third_party').alternatives)
 assert.ok(!['3','4'].includes(a.combination.split('-')[0]));
assert.equal(s.bets.length,main.bets.length);
assert.equal(new Set(s.bets.map(b=>b.combination)).size,s.bets.length);
assert.deepEqual(s.bets.map(b=>b.virtual_yen).sort((a,b)=>a-b),main.bets.map(b=>b.virtual_yen).sort((a,b)=>a-b));
assert.equal(s.bets.reduce((n,b)=>n+b.virtual_yen,0),50000);
assert.ok(s.candidates.every(c=>c.multiplier>=.85&&c.multiplier<=1.08));
const poison={...input,counterplay_shadow_trial:true,result:{finish:'6-5-4'},odds:{'6-5-4':1000},opponent_intent:'mark lane 4'};
assert.deepEqual(bridge.run(poison).counterplay_shadow,s,'no results, odds or invented intentions');
const weak=fixture();weak.racers[2].national_win_rate=2;weak.racers[2].average_start_timing=.35;
const ws=bridge.run({...weak,counterplay_shadow_trial:true}).counterplay_shadow;
assert.equal(ws.duels.find(d=>d.attacker_lane===4).resistance_plausible,false);
assert.equal(ws.active_duels,0,'strong boat cannot be penalized without a capable opponent');
assert.deepEqual(ws.bets,bridge.run(weak).bets.map(({combination,virtual_yen})=>({combination,virtual_yen})));
const missing=fixture();missing.racers[2].average_start_timing=null;
const ms=bridge.run({...missing,counterplay_shadow_trial:true}).counterplay_shadow;
assert.ok(ms.duels.find(d=>d.attacker_lane===4).missing_fields.includes('average_start_timing'));
assert.equal(ms.duels.find(d=>d.attacker_lane===4).resistance_plausible,false);
assert.equal(ms.duels.find(d=>d.attacker_lane===4).turn_comparison,'unavailable');
const flying=fixture();flying.racers[3].exhibition_st=-.2;
const absent=fixture();absent.racers[3].exhibition_st=null;
const fs=bridge.run({...flying,counterplay_shadow_trial:true}).counterplay_shadow;
const ns=bridge.run({...absent,counterplay_shadow_trial:true}).counterplay_shadow;
assert.equal(fs.duels.find(d=>d.attacker_lane===4).estimated_st_gap_sec,ns.duels.find(d=>d.attacker_lane===4).estimated_st_gap_sec);
assert.deepEqual(fs.duels.find(d=>d.attacker_lane===4).exhibition_f_ignored,[4]);
const entry=fixture();entry.racers[3].course=6;entry.racers[5].course=4;
const es=bridge.run({...entry,counterplay_shadow_trial:true}).counterplay_shadow;
assert.equal(es.duels.find(d=>d.attacker_lane===4).defender_lane,5,'opponent follows actual entry, not boat number');
const late={...input,frozen_at_utc:'2026-11-04T01:00:00Z'};
assert.throws(()=>shadow.run(late,main.bets));
assert.deepEqual(bridge.run({...late,counterplay_shadow_trial:true}).bets,bridge.run(late).bets);
assert.equal(bridge.run({...late,counterplay_shadow_trial:true}).counterplay_shadow.status,'unavailable');
assert.equal(bridge.run({...input,cutoff_iso_jst:null,counterplay_shadow_trial:true}).counterplay_shadow.status,'unavailable');
assert.equal(bridge.run({...input,phase:'baseline',counterplay_shadow_trial:true}).counterplay_shadow.status,'unavailable');
console.log('Counterplay: resistant vs unopposed attacker, failure/no-podium, third-party branch, no-leakage, entry mapping, cutoff and formal isolation PASS');
const {run:replay}=require('../../scripts/replay_counterplay_shadow.js');
const snap={...input,...main};
const hit=main.bets[0].combination;
const ledger={event_date:'2026-11-04',race_records:{a:{versions:[snap,
 {...snap,frozen_at_utc:'2026-11-04T02:00:00Z',bets:[]}],
 official_pay:{finish:hit,payout_per_100:2000,verified:true}},
 b:{versions:[snap],official_pay:{finish:'4-4-3',payout_per_100:1000,verified:true}},
 c:{versions:[{...snap,phase:'baseline'}]}}};
const ledgerCopy=JSON.stringify(ledger),audit=replay(ledger);
assert.equal(audit.eligible,2);assert.equal(audit.unavailable,1);assert.equal(audit.unverified,1);
assert.equal(audit.main.hits,1);assert.equal(audit.main.stake,50000);
assert.equal(JSON.stringify(ledger),ledgerCopy);
console.log('Counterplay replay: only pre-cutoff exhibition versions, malformed outcomes excluded, immutable ledger PASS');
