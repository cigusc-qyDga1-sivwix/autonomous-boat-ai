'use strict';
const assert=require('node:assert/strict');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const {run}=require('../../scripts/replay_role_follower_coverage.js');
const input={venue:'唐津',phase:'exhibition',frozen_at_utc:'2026-11-04T00:00:00Z',
 venue_tactics_trial:true,role_skill_shadow_trial:true,role_skill_head_preserved_trial:true,
 racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,national_win_rate:5+i*.2,
 average_start_timing:.15,exhibition_st:.1,exhibition_time:6.8+i*.01,motor_top_2_percent:35}))};
const v={...input,...bridge.run(input),cutoff_iso_jst:'2026-11-04T10:00:00+09:00'};
const finish=v.bets[0].combination;
const post={...structuredClone(v),frozen_at_utc:'2026-11-04T02:00:00Z',bets:[]};
const ledger={event_date:'2026-11-04',race_records:{a:{versions:[v,post],
 official_pay:{finish,payout_per_100:2000,verified:true}},b:{versions:[v],official_pay:null},
 c:{versions:[v],official_pay:{finish:'1-1-4',payout_per_100:1000,verified:true}}}};
const frozen=JSON.stringify(ledger),result=run(ledger);
assert.equal(result.records,3);assert.equal(result.unverified,2);
assert.equal(result.control.n,1);assert.equal(result.control.hits,1);
assert.equal(result.control.stake,50000);assert.equal(result.trial.stake,50000);
assert.equal(result.stored_v02_mismatches,0);assert.equal(result.forward_evidence,false);
assert.equal(JSON.stringify(ledger),frozen,'research must not rewrite saved bets');
console.log('Replay audit: excludes post-cutoff, unverified and malformed results; immutable ledger PASS');
