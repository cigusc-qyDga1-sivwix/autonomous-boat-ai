'use strict';
const assert=require('node:assert/strict');
const {run}=require('../../scripts/freeze_second_place_trials.js');
const {audit,projectLedger}=require('../../scripts/audit_second_place_trials.js');
const day='2026-11-09';
const rows=[];for(let a=1;a<=6;a++)for(let b=1;b<=6;b++)for(let c=1;c<=6;c++){
 if(new Set([a,b,c]).size===3)rows.push({combination:[a,b,c].join('-'),relative_score:1});
}
const ranked=rows.map(x=>({...x,relative_score:1/120}));
const bets=rows.slice(0,6).map((x,i)=>({combination:x.combination,virtual_yen:i===0?20000:6000}));
const race={venue:'徳山',race:3,phase:'exhibition',ticket_status:'formal',
 model_version:'four-factor-v2.2-linked-primary-untrained',cutoff_jst:'10:00',
 frozen_at_utc:'2026-11-09T00:24:00Z',sha256:'a'.repeat(64),bets,
 interaction_primary:{canonical_source:'linked-four-factor-venue-st-wake-120',ranked_outcomes:ranked}};
const live={event_date:day,updated_at_utc:'2026-11-09T00:30:00Z',forecast_races:[race]};
const trial=run(live,null,Date.parse('2026-11-09T09:35:00+09:00')).doc;
const official={source:'boatrace_official_pay',verified:true,virtual_stake:50000,
 snapshot_sha256:race.sha256,finish:'1-2-3',payout_per_100:1500};
const ledger={event_date:day,race_records:{'18-3':{venue:'徳山',race:3,versions:[race],official_pay:official}}};
const report=audit(trial,projectLedger(ledger));
assert.equal(report.paired_verified_races,1);
assert.equal(report.formal.races,1);
assert.equal(report.trial.virtual_stake_yen,50000);
assert.equal(report.provisional_commit_time_not_verified,true);
const conflict=structuredClone(ledger);
conflict.race_records['18-3'].official_conflict={reason:'official correction pending'};
assert.equal(audit(trial,projectLedger(conflict)).paired_verified_races,0);
const wrongSha=structuredClone(ledger);
wrongSha.race_records['18-3'].official_pay.snapshot_sha256='b'.repeat(64);
assert.equal(audit(trial,projectLedger(wrongSha)).paired_verified_races,0);
const altered=structuredClone(ledger);
altered.race_records['18-3'].versions[0].bets[0].virtual_yen=19000;
assert.equal(audit(trial,projectLedger(altered)).paired_verified_races,0);
const refunded=structuredClone(ledger);
refunded.race_records['18-3'].official_pay.refunded_boats=[6];
assert.equal(audit(trial,projectLedger(refunded)).paired_verified_races,0);
const badTrial=structuredClone(trial);
badTrial.records[0].second_pair_trial.bets[0].virtual_yen=1000;
assert.equal(audit(badTrial,projectLedger(ledger)).paired_verified_races,0);
console.log('Official-only same-SHA second-pair comparison and refund quarantine: PASS');
