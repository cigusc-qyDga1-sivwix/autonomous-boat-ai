#!/usr/bin/env node
/* Forward-only v0.5 vs v0.6: immutable SHA, common inputs and result-free A/B.
 * NEVER retroactively create forecasts or read settlement data into a model.
 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const base=require('./freeze_tactical_trials.js');
const engine=globalThis.BoatTacticalModel;
const DIR='app/data/experiments';
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x),'utf8').digest('hex');
function features(r){
 return {venue:r.venue,phase:r.phase,weather_used:r.weather_used,
  venue_profile:r.venue_profile||null,frozen_at_utc:r.frozen_at_utc,
  racers:r.racers.map(x=>({lane:x.lane,course:x.course,
   national_win_rate:x.national_win_rate,motor_top_2_percent:x.motor_top_2_percent,
   average_start_timing:x.average_start_timing,exhibition_st:x.exhibition_st,
   exhibition_time:x.exhibition_time,original_exhibition:x.original_exhibition||null}))};
}
const tickets=m=>m.bets.map(b=>({combination:b.combination,virtual_yen:b.virtual_yen,
 head_course:b.head_course,conditional_reason:b.conditional_reason,relative_score:b.relative_score}));
function run(live,earlier,nowMs){
 const eligible=base.run(live,null,nowMs);
 const day=live.event_date;
 const doc=earlier&&earlier.event_date===day?earlier:{
  schema:'boatlabs.six_boat_coupling_forward_v1',event_date:day,
  created_at_utc:new Date(nowMs).toISOString(),records:[]};
 if(doc.schema!=='boatlabs.six_boat_coupling_forward_v1'||!Array.isArray(doc.records))
  throw Error('Invalid v0.6 ledger');
 const keys=new Set(doc.records.map(x=>x.id));
 let added=0,existing=0,errors=0,unconfirmedEntry=0;
 for(const old of eligible.doc.records){
  if(keys.has(old.id)){existing++;continue;}
  const race=live.forecast_races.find(r=>r.venue===old.venue&&r.race===old.race&&
   (r.phase==='exhibition'?'exhibition':'baseline')===old.phase);
  if(!race){errors++;continue;}
  let control,trial;
  try{
   const f=features(race);
   control=engine.forecastOutsideRole(f);
   trial=engine.forecastCoupled(f);
  }catch(err){errors++;continue;}
  if(!base.validateBets(control.bets)||!base.validateBets(trial.bets)){errors++;continue;}
  const entryConfirmed=race.phase==='exhibition'&&race.racers.every(x=>
   Number.isInteger(Number(x.course))&&Number(x.course)>=1&&Number(x.course)<=6);
  if(!entryConfirmed)unconfirmedEntry++;
  const record={
   id:old.id,date:day,venue:old.venue,race:old.race,phase:old.phase,
   cutoff_jst:old.cutoff_jst,created_at_utc:new Date(nowMs).toISOString(),
   source_updated_at_utc:old.source_updated_at_utc,
   source_frozen_at_utc:race.frozen_at_utc,
   original_fixed_sha256:old.original_fixed_sha256,
   minutes_before_cutoff:old.minutes_before_cutoff,is_forward_fixed:true,
   virtual_budget_per_model_yen:50000,
   input_quality:{...old.input_quality,entry_confirmed_exhibition:entryConfirmed,
     note:entryConfirmed?'Exhibition course observed in pre-cutoff source':'Course provisional: do not assume a verified entry; especially pre-entry changes'},
   v05_control:{model:control.model,bets:tickets(control)},
   v06_coupled:{model:trial.model,bets:tickets(trial),
     interaction_graph:trial.metadata.coupled_v06.interaction_graph,
     relative_scores_uncalibrated:true},
   source_restrictions:'saved pre-race features only; NO results, odds, payouts or historical tuning'
  };
  record.record_sha256=hash(record);
  doc.records.push(record);keys.add(old.id);added++;
 }
 doc.records.sort((a,b)=>a.cutoff_jst.localeCompare(b.cutoff_jst)||
  a.venue.localeCompare(b.venue)||a.phase.localeCompare(b.phase));
 return {doc,status:{schema:'boatlabs.six_boat_coupling_status_v1',
  event_date:day,checked_at_utc:new Date(nowMs).toISOString(),
  new_forward_freezes:added,total_versions:doc.records.length,
  already_frozen:existing,entry_provisional_new:unconfirmedEntry,
  excluded_late:eligible.status.excluded_late,excluded_stale:eligible.status.excluded_stale,
  errors:errors+eligible.status.errors,source_stale:eligible.status.stale_source,
  note:'Experimental v0.6 vs v0.5, frozen BEFORE cutoff; never overwrite prior records; not trained probabilities or real betting.'}};
}
function main(){
 const live=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
 fs.mkdirSync(DIR,{recursive:true});
 const file=path.join(DIR,'coupling-'+live.event_date+'.json');
 const previous=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):null;
 const priorHash=new Map((previous?.records||[]).map(x=>[x.id,x.record_sha256]));
 const {doc,status}=run(live,previous,Date.now());
 for(const [id,sha] of priorHash)if(doc.records.find(x=>x.id===id)?.record_sha256!==sha)
  throw Error('Existing six-boat coupling forecast modified: '+id);
 fs.writeFileSync(file,JSON.stringify(doc,null,2)+'\n');
 fs.writeFileSync(path.join(DIR,'coupling-status-latest.json'),JSON.stringify(status,null,2)+'\n');
 process.stdout.write(JSON.stringify(status)+'\n');
}
module.exports={run};
if(require.main===module)main();
