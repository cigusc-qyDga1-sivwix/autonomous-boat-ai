const assert=require('node:assert/strict');
const {classify}=require('../ticket-policy.js');
const day='2026-10-25';
const r={phase:'exhibition',sha256:'a'.repeat(64),cutoff_jst:'12:00',frozen_at_utc:'2026-10-25T02:57:00Z',racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,exhibition_st:.15,exhibition_time:6.8}))};
assert.equal(classify(r,day).formal,true);
assert.equal(classify({...r,phase:'baseline',entry_exhibition_gate:{final_eligible:true}},day).formal,false);
assert.equal(classify({...r,frozen_at_utc:'2026-10-25T03:01:00Z'},day).formal,false);
assert.equal(classify({...r,frozen_at_utc:'2026-10-25T02:59:00Z'},day).formal,false);
assert.equal(classify({...r,racers:r.racers.slice(1)},day).formal,false);
const duplicate=structuredClone(r);duplicate.racers[5].course=1;
assert.equal(classify(duplicate,day).formal,false);
const missing=structuredClone(r);missing.racers[5].exhibition_st=null;
assert.equal(classify(missing,day).formal,false);
assert.equal(classify(r,'2026-10-26').formal,false);
// A recalculation that leaves ticket combinations unchanged is still formal.
assert.equal(classify({...r,exhibition_change:{bets_changed:false}},day).formal,true);
console.log('Formal exhibition ticket eligibility: PASS');

require('../cumulative-settlement.js');
const bets=['1-2-3','1-3-2','2-1-3','2-3-1','3-1-2'].map(combination=>({combination,virtual_yen:10000}));
const record=snap=>({venue:'鳴門',race:1,versions:[{...snap,venue:'鳴門',race:1,bets,cutoff_iso_jst:day+'T12:00:00+09:00'}],official_pay:{source:'boatrace_official_pay',verified:true,finish:'1-2-3',payout_per_100:1000,snapshot_sha256:r.sha256}});
const doc={event_date:day,race_records:{'14-1':record(r)}};
assert.equal(globalThis.BoatCumulative.summary(doc,day,true).checked,1);
doc.race_records['14-1'].versions.push({...doc.race_records['14-1'].versions[0],phase:'baseline'});
assert.equal(globalThis.BoatCumulative.summary(doc,day,true).checked,0,'never fall back to an older formal version');
assert.equal(globalThis.BoatCumulative.summary(doc,day).checked,1,'provisional remains research only');
console.log('Formal settlement excludes baseline and selects one latest version: PASS');
