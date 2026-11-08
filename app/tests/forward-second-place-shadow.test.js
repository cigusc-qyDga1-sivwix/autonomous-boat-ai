'use strict';
const assert=require('node:assert/strict');
const {canonical,validBets,trialSelection,run}=
 require('../../scripts/freeze_second_place_trials.js');
const rows=[];
for(let a=1;a<=6;a++)for(let b=1;b<=6;b++)for(let c=1;c<=6;c++)
 if(a!==b&&a!==c&&b!==c)rows.push({
  combination:[a,b,c].join('-'),
  relative_score:a===1&&b===2?10:a===1&&b===3?8:a===1&&b===4?7:1
 });
const total=rows.reduce((s,x)=>s+x.relative_score,0);
const normalized=rows.map(x=>({...x,relative_score:x.relative_score/total}));
const ranked=canonical(normalized);
const formal=ranked.slice(0,6).map((x,i)=>({
 combination:x.combination,virtual_yen:i===0?20000:6000}));
assert.equal(validBets(formal),true);
const shadow=trialSelection(normalized,formal);
assert.equal(shadow.bets.length,formal.length);
assert.equal(validBets(shadow.bets),true);
assert.ok(shadow.shadow_pair_coverage>shadow.formal_pair_coverage);
assert.notDeepEqual(shadow.bets,formal);
assert.throws(()=>canonical(normalized.slice(1)),/canonical_120_missing/);
assert.throws(()=>canonical(normalized.map((r,i)=>
 i===1?{...r,combination:normalized[0].combination}:r)),/canonical_120_invalid/);
assert.throws(()=>canonical(normalized.map((r,i)=>
 i===0?{...r,relative_score:0}:r)),/canonical_120_invalid/);
const day='2026-11-09',now=Date.parse(day+'T09:35:00+09:00');
const base={venue:'徳山',race:1,phase:'exhibition',ticket_status:'formal',
 model_version:'four-factor-v2.2-linked-primary-untrained',
 sha256:'f'.repeat(64),cutoff_jst:'10:00',frozen_at_utc:day+'T00:24:00Z',
 bets:formal,interaction_primary:{canonical_source:'linked-four-factor-venue-st-wake-120',
 ranked_outcomes:normalized}};
const live={event_date:day,updated_at_utc:day+'T00:30:00Z',
 forecast_races:[base]};
const first=run(live,null,now);
assert.equal(first.status.new_forward_freezes,1);
assert.equal(first.doc.records.length,1);
assert.equal(first.doc.records[0].not_formal,true);
assert.equal(first.doc.records[0].original_fixed_sha256,base.sha256);
assert.equal(first.doc.records[0].point_count,6);
assert.match(first.doc.records[0].record_sha256,/^[a-f0-9]{64}$/);
const repeat=run(live,first.doc,now+1000);
assert.equal(repeat.status.new_forward_freezes,0);
assert.equal(repeat.status.already_frozen,1);
assert.deepEqual(repeat.doc,first.doc);
assert.equal(run(live,null,Date.parse(day+'T09:57:00+09:00')).status.excluded_late,1);
assert.equal(run({...live,updated_at_utc:'2026-11-08T23:45:00Z'},null,now).status.excluded_stale,1);
assert.equal(run({...live,forecast_races:[{...base,ticket_status:'provisional'}]},null,now).status.excluded_not_formal,1);
assert.equal(run({...live,forecast_races:[{...base,interaction_primary:{}}]},null,now).status.excluded_missing_120,1);
assert.equal(run({...live,forecast_races:[{...base,sha256:'e'.repeat(64)}]},first.doc,now).status.new_forward_freezes,1);
assert.throws(()=>run(live,{...first.doc,records:[
 {...first.doc.records[0],record_sha256:'bad'}]},now),/immutable_record_changed/);
console.log('Second-place conditional shadow / equal-budget / pre-cutoff gates: PASS');
