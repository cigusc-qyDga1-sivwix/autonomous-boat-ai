#!/usr/bin/env node
/* Independent pre-cutoff v0.6 vs v0.7 SHA ledger; no retrospective forecasts.
 * All forecasts use already saved pre-race source fields, not race results.
 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const prior=require('./freeze_coupling_trials.js');
const engine=globalThis.BoatTacticalModel;
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x),'utf8').digest('hex');
const dir='app/data/experiments';
function run(live,earlier,nowMs){
 const eligible=prior.run(live,null,nowMs);
 const day=live.event_date;
 const doc=earlier&&earlier.event_date===day?earlier:{
  schema:'boatlabs.outside_start_gap_forward_v1',event_date:day,
  created_at_utc:new Date(nowMs).toISOString(),records:[]};
 if(doc.schema!=='boatlabs.outside_start_gap_forward_v1'||!Array.isArray(doc.records))
  throw Error('Invalid outside-start A/B ledger');
 const seen=new Set(doc.records.map(r=>r.id));
 let newItems=0,existing=0,failed=0,entryWait=0,provisional=0;
 for(const old of eligible.doc.records){
  if(seen.has(old.id)){existing++;continue;}
  const race=live.forecast_races.find(r=>r.venue===old.venue&&r.race===old.race&&
   (r.phase==='exhibition'?'exhibition':'baseline')===old.phase);
  if(!race){failed++;continue;}
  // If a front-taking/entry-change watch is raised, exhibition confirmation
  // is required. Do not backfill using normal lane-course positions.
  if(race.entry_exhibition_gate?.entry_watch&&
    !race.entry_exhibition_gate?.final_eligible){entryWait++;continue;}
  const racers=race.racers.map(r=>({
   lane:r.lane,course:r.course,national_win_rate:r.national_win_rate,
   motor_top_2_percent:r.motor_top_2_percent,
   average_start_timing:r.average_start_timing,
   exhibition_st:r.exhibition_st,exhibition_time:r.exhibition_time,
   original_exhibition:r.original_exhibition||null
  }));
  let model;
  try{model=engine.forecastOutsideStart({
   venue:race.venue,racers,venue_profile:race.venue_profile||null,
   weather_used:race.weather_used,frozen_at_utc:race.frozen_at_utc
  });}catch(e){failed++;continue;}
  const betValid=Array.isArray(model.bets)&&model.bets.length>=4&&model.bets.length<=12&&
   new Set(model.bets.map(x=>x.combination)).size===model.bets.length&&
   model.bets.reduce((a,b)=>a+b.virtual_yen,0)===50000;
  if(!betValid){failed++;continue;}
  const exhibitionEntry=old.input_quality?.entry_confirmed_exhibition===true;
  if(!exhibitionEntry)provisional++;
  const plainBets=m=>m.bets.map(b=>({
   combination:b.combination,virtual_yen:b.virtual_yen,
   head_course:b.head_course,relative_score:b.relative_score,
   conditional_reason:b.conditional_reason
  }));
  const trial={
   id:old.id,date:day,venue:old.venue,race:old.race,phase:old.phase,
   cutoff_jst:old.cutoff_jst,created_at_utc:new Date(nowMs).toISOString(),
   original_fixed_sha256:old.original_fixed_sha256,
   source_updated_at_utc:old.source_updated_at_utc,
   minutes_before_cutoff:old.minutes_before_cutoff,
   source_frozen_at_utc:old.source_frozen_at_utc,
   is_forward_fixed:true,virtual_budget_per_model_yen:50000,
   input_quality:{...old.input_quality,start_exhibition_is_not_race_st:true},
   v06_control:old.v06_coupled,
   v07_start_gap:{model:model.model,bets:plainBets(model),
    st_signals:model.metadata.start_v07.slit_signals,
    role_coverage:model.role_coverage,relative_scores_uncalibrated:true},
   source_restrictions:'pre-cutoff saved racer data only; no results, payouts, actual final ST, or odds'
  };
  trial.record_sha256=hash(trial);
  doc.records.push(trial);seen.add(old.id);newItems++;
 }
 doc.records.sort((a,b)=>a.cutoff_jst.localeCompare(b.cutoff_jst)||
  a.venue.localeCompare(b.venue)||a.phase.localeCompare(b.phase));
 return {doc,status:{schema:'boatlabs.outside_start_gap_status_v1',
  event_date:day,checked_at_utc:new Date(nowMs).toISOString(),
  new_forward_freezes:newItems,total_versions:doc.records.length,
  already_frozen:existing,excluded_entry_watch:entryWait,provisional_entry_new:provisional,
  errors:failed+eligible.status.errors,excluded_late:eligible.status.excluded_late,
  excluded_stale:eligible.status.excluded_stale,stale_source:eligible.status.source_stale,
  note:'Separate immutable v0.6 vs v0.7 trial, not learned actual ST, no official BUY accounting.'}};
}
function main(){
 const live=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
 fs.mkdirSync(dir,{recursive:true});
 const dest=path.join(dir,'outside-start-'+live.event_date+'.json');
 const previous=fs.existsSync(dest)?JSON.parse(fs.readFileSync(dest,'utf8')):null;
 const before=new Map((previous?.records||[]).map(r=>[r.id,r.record_sha256]));
 const {doc,status}=run(live,previous,Date.now());
 for(const [id,sha] of before){
  if(doc.records.find(r=>r.id===id)?.record_sha256!==sha)
   throw Error('Immutable v0.7 forecast was changed: '+id);
 }
 fs.writeFileSync(dest,JSON.stringify(doc,null,2)+'\n');
 fs.writeFileSync(path.join(dir,'outside-start-status-latest.json'),
  JSON.stringify(status,null,2)+'\n');
 console.log(JSON.stringify(status));
}
module.exports={run};
if(require.main===module)main();
