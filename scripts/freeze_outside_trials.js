#!/usr/bin/env node
/* BOAT LAB v0.2 independent forward-only experiment.
 * Reuse v0.1's cutoff, freshness and ticket validity gates. NEVER rewrite
 * the existing v0.1 ledger, official settlement or historical predictions.
 */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const baseline=require('./freeze_tactical_trials.js');
const engine=globalThis.BoatTacticalModel;
const hash=value=>crypto.createHash('sha256').update(JSON.stringify(value),'utf8').digest('hex');
const DIR='app/data/experiments';
function run(live,earlier,nowMs){
  // The original A/B validator rejects late/stale/invalid snapshot inputs.
  const eligible=baseline.run(live,null,nowMs);
  const day=live.event_date;
  const doc=earlier&&earlier.event_date===day?earlier:{
    schema:'boatlabs.outside_makuri_forward_v1',event_date:day,
    created_at_utc:new Date(nowMs).toISOString(),records:[]};
  if(doc.schema!=='boatlabs.outside_makuri_forward_v1')throw Error('Invalid outside-ledger schema');
  if(!Array.isArray(doc.records))throw Error('Invalid outside-ledger records');
  const frozen=new Set(doc.records.map(x=>x.id));
  let created=0,skippedExisting=0,errors=0;
  for(const old of eligible.doc.records){
    if(frozen.has(old.id)){skippedExisting++;continue;}
    const race=live.forecast_races.find(r=>r.venue===old.venue&&r.race===old.race&&
       (r.phase==='exhibition'?'exhibition':'baseline')===old.phase);
    if(!race){errors++;continue;}
    let trial;
    try{
      trial=engine.forecastOutside({
        venue:race.venue,racers:race.racers.map(r=>({
          lane:r.lane,course:r.course,national_win_rate:r.national_win_rate,
          motor_top_2_percent:r.motor_top_2_percent,
          average_start_timing:r.average_start_timing,
          exhibition_st:r.exhibition_st,exhibition_time:r.exhibition_time,
          original_exhibition:r.original_exhibition||null
        })),
        weather_used:race.weather_used,venue_profile:race.venue_profile||null,
        frozen_at_utc:race.frozen_at_utc,bets:race.bets
      });
    }catch(e){errors++;continue;}
    if(!baseline.validateBets(trial.bets)){errors++;continue;}
    const entry={
      id:old.id,date:day,venue:old.venue,race:old.race,phase:old.phase,
      cutoff_jst:old.cutoff_jst,created_at_utc:new Date(nowMs).toISOString(),
      source_updated_at_utc:old.source_updated_at_utc,
      original_fixed_sha256:old.original_fixed_sha256,
      minutes_before_cutoff:old.minutes_before_cutoff,
      virtual_budget_per_model_yen:50000,is_forward_fixed:true,
      input_quality:old.input_quality,
      previous_model:{model:old.tactical.model,bets:old.tactical.bets},
      outside_model:{model:trial.model,bets:trial.bets.map(b=>({
        combination:b.combination,virtual_yen:b.virtual_yen,
        head_course:b.head_course,scenario:b.scenario,relative_score:b.relative_score
      })),head_course_shares:trial.head_course_shares,
        attack_signals:trial.metadata.outside_attack_signals,
        relative_scores_uncalibrated:true}
    };
    entry.record_sha256=hash(entry);
    doc.records.push(entry);frozen.add(old.id);created++;
  }
  doc.records.sort((a,b)=>a.cutoff_jst.localeCompare(b.cutoff_jst)||
    a.venue.localeCompare(b.venue)||a.phase.localeCompare(b.phase));
  const status={
    schema:'boatlabs.outside_makuri_status_v1',event_date:day,
    checked_at_utc:new Date(nowMs).toISOString(),new_forward_freezes:created,
    total_versions:doc.records.length,already_frozen:skippedExisting,
    excluded_late:eligible.status.excluded_late,
    excluded_stale:eligible.status.excluded_stale,
    source_stale:eligible.status.stale_source,
    errors:errors+eligible.status.errors,
    note:'Forward-only v0.1 vs outside-v0.2 research. No results or payouts are model inputs. No real bets.'
  };
  return {doc,status};
}
function main(){
  const live=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
  const output=path.join(DIR,'outside-'+live.event_date+'.json');
  fs.mkdirSync(DIR,{recursive:true});
  const previous=fs.existsSync(output)?JSON.parse(fs.readFileSync(output,'utf8')):null;
  const before=new Map((previous?.records||[]).map(x=>[x.id,x.record_sha256]));
  const {doc,status}=run(live,previous,Date.now());
  for(const [id,sha] of before){
    if(doc.records.find(x=>x.id===id)?.record_sha256!==sha)
      throw Error('Existing outside trial was modified: '+id);
  }
  fs.writeFileSync(output,JSON.stringify(doc,null,2)+'\n');
  fs.writeFileSync(path.join(DIR,'outside-status-latest.json'),
    JSON.stringify(status,null,2)+'\n');
  process.stdout.write(JSON.stringify(status)+'\n');
}
module.exports={run};
if(require.main===module)main();
