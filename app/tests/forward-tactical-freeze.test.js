const assert=require('node:assert/strict');
const {run,validateBets}=require('../../scripts/freeze_tactical_trials.js');
const day='2026-10-23',now=Date.parse('2026-10-23T16:33:00+09:00');
const racers=Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,national_win_rate:[6.5,5.9,7.8,6.4,5.2,5.1][i],
  average_start_timing:[.16,.15,.10,.16,.17,.19][i],
  motor_top_2_percent:[30,35,49,41,32,20][i]
}));
const bets=['1-2-3','1-3-2','2-1-3','3-1-2','1-2-4','3-2-1'].map((x,i)=>
  ({combination:x,virtual_yen:i===0?10000:8000}));
const base=(race,cutoff,phase='baseline')=>({
  venue:'大村',race,cutoff_jst:cutoff,phase,
  racers,bets,model_version:'old-v0.5',sha256:'a'.repeat(64),
  frozen_at_utc:'2026-10-23T05:00:00Z',
  weather_used:{wind_speed:3},venue_profile:{course1_reference_rate:.620}
});
const make=(stamp='2026-10-23T07:32:00Z')=>({
  event_date:day,updated_at_utc:stamp,
  forecast_races:[base(1,'16:34'),base(2,'16:51'),base(3,'17:15')]
});
const first=run(make(),null,now);
assert.equal(first.status.new_forward_freezes,2,'too close must be excluded');
assert.equal(first.status.excluded_late,1);
assert.equal(first.doc.records.length,2);
const record=first.doc.records[0];
assert.equal(record.is_forward_fixed,true);
assert.equal(record.virtual_budget_per_model_yen,50000);
assert.ok(record.minutes_before_cutoff>3);
assert.match(record.record_sha256,/^[a-f0-9]{64}$/);
assert.equal(record.original_fixed_sha256,'a'.repeat(64));
assert.ok(validateBets(record.baseline.bets));
assert.ok(validateBets(record.tactical.bets));
assert.equal(record.tactical.model,'tactical-1m-conditional-v0.1-untrained');
assert.equal(record.input_quality.exhibition_confirmed_in_original,false);
assert.equal(first.status.exhibition_versions,0);
const unchanged=run(make(),first.doc,now+1000);
assert.equal(unchanged.status.new_forward_freezes,0);
assert.equal(unchanged.status.already_frozen,2);
assert.deepEqual(unchanged.doc.records.map(x=>x.record_sha256),first.doc.records.map(x=>x.record_sha256));
const stale=run(make('2026-10-23T05:20:00Z'),null,now);
assert.equal(stale.doc.records.length,0);
assert.equal(stale.status.excluded_stale,2);
const later={event_date:day,updated_at_utc:'2026-10-23T07:42:00Z',
forecast_races:[base(3,'17:15','exhibition')]};
const after=run(later,first.doc,Date.parse('2026-10-23T16:43:00+09:00'));
assert.equal(after.status.new_forward_freezes,1);
assert.equal(after.doc.records.length,3);
assert.equal(after.status.exhibition_versions,1);
assert.equal(after.doc.records.filter(x=>x.race===3).length,2,'baseline+exhibition independent versions');
assert.equal(after.doc.records.find(x=>x.phase==='baseline'&&x.race===3).record_sha256,
 first.doc.records.find(x=>x.phase==='baseline'&&x.race===3).record_sha256);
assert.throws(()=>run({...make(),event_date:'not-a-day'},null,now),/Missing source event date/);
const many=Array.from({length:6},(_,a)=>Array.from({length:6},(_,b)=>Array.from({length:6},(_,c)=>
 a!==b&&b!==c&&a!==c?[a+1,b+1,c+1].join('-'):null))).flat(2).filter(Boolean).slice(0,14)
 .map((combination,i)=>({combination,virtual_yen:i===0?11000:3000}));
assert.equal(validateBets(many,'four-factor-v1.4-venue-aware-23-untrained','2026-11-02'),true);
assert.equal(validateBets(many,'four-factor-v1.4-venue-aware-23-untrained','2026-10-28'),false);
assert.equal(validateBets([{combination:'1-1-2',virtual_yen:50000}],
 'four-factor-v1.5-point-free-untrained','2026-11-02'),false);
const expanded={event_date:'2026-11-02',updated_at_utc:'2026-11-02T01:00:00Z',forecast_races:[{
 ...base(4,'14:00'),model_version:'four-factor-v1.4-venue-aware-23-untrained',bets:many,
 frozen_at_utc:'2026-11-02T00:30:00Z'}]};
const recovered=run(expanded,null,Date.parse('2026-11-02T01:01:00Z'));
assert.equal(recovered.status.new_forward_freezes,1,'valid current 14-point source is not silently dropped');
assert.equal(recovered.status.errors,0);
console.log('Pre-cutoff tactical A/B seal, 3-minute safety, replay separation and no overwrite: PASS');
