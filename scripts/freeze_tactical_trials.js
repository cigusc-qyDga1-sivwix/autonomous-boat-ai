#!/usr/bin/env node
/* BOAT LAB pre-cutoff A/B freeze: immutable forecast comparison, virtual only.
 * This command must run on GitHub Actions after daily source ingestion and
 * before committing updated snapshot data. Outcomes/payouts are never read.
 */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
require('../app/tactical-1m.js');
const engine=globalThis.BoatTacticalModel;
const SOURCE='app/data/live/latest.json', DIR='app/data/experiments';
const MIN_CUTOFF_LEAD_MS=3*60*1000;
const MAX_SOURCE_LAG_MS=45*60*1000;
const hash=value=>crypto.createHash('sha256').update(JSON.stringify(value),'utf8').digest('hex');
const dateAt=(day,clock)=>Date.parse(day+'T'+clock+':00+09:00');
const parseDate=iso=>Date.parse(iso);
function validateBets(bets,modelVersion){
 const free=modelVersion==='four-factor-v1.5-point-free-untrained',unit=free?100:1000;
 return Array.isArray(bets)&&bets.length>=(free?1:4)&&bets.length<=(free?120:12)&&
    new Set(bets.map(x=>x.combination)).size===bets.length&&
    bets.every(x=>/^[1-6]-[1-6]-[1-6]$/.test(x.combination)&&Number.isInteger(x.virtual_yen)&&x.virtual_yen>=unit&&(!free||x.virtual_yen%unit===0))&&
    bets.reduce((s,b)=>s+b.virtual_yen,0)===50000;
}
function run(live,earlier,nowMs){
 const day=live.event_date;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day))throw Error('Missing source event date');
 if(!Array.isArray(live.forecast_races))throw Error('Missing forecasts');
 const refreshed=Date.parse(live.updated_at_utc);
 if(!Number.isFinite(refreshed)||refreshed>nowMs+60000)throw Error('Untrusted source update time');
 const stale=nowMs-refreshed>MAX_SOURCE_LAG_MS;
 const doc=earlier&&earlier.event_date===day?earlier:{
  schema:'boatlabs.tactical_ab_forward_v1',
  event_date:day,created_at_utc:new Date(nowMs).toISOString(),records:[]};
 if(doc.schema!=='boatlabs.tactical_ab_forward_v1')throw Error('Bad ledger schema');
 const keys=new Set(doc.records.map(x=>x.id));
 let skippedLate=0,skippedStale=0,skippedExisting=0,errors=0,created=0;
 for(const race of live.forecast_races){
   const phase=race.phase==='exhibition'?'exhibition':'baseline';
   const id=race.venue+'|'+race.race+'|'+phase;
   if(keys.has(id)){skippedExisting++;continue}
   const cutoff=dateAt(day,race.cutoff_jst);
   if(!Number.isFinite(cutoff)||cutoff-nowMs<=MIN_CUTOFF_LEAD_MS){skippedLate++;continue}
   if(stale){skippedStale++;continue}
   const fixedAt=parseDate(race.frozen_at_utc);
   // No original evidence after the cutoff, and not before our experiment.
   if(!Number.isFinite(fixedAt)||fixedAt>cutoff-MIN_CUTOFF_LEAD_MS||fixedAt>nowMs) {errors++;continue}
   if(!validateBets(race.bets,race.model_version)){errors++;continue}
   let newTrial;
   try{
      newTrial=engine.forecast({
       venue:race.venue,phase,
       racers:race.racers.map(r=>({
         lane:r.lane,course:r.course,national_win_rate:r.national_win_rate,
         motor_top_2_percent:r.motor_top_2_percent,average_start_timing:r.average_start_timing,
         exhibition_st:r.exhibition_st,exhibition_time:r.exhibition_time,
         original_exhibition:r.original_exhibition||null
       })),
       weather_used:race.weather_used,venue_profile:race.venue_profile||null,
       frozen_at_utc:race.frozen_at_utc,bets:race.bets
      });
   }catch(e){errors++;continue}
   if(!validateBets(newTrial.bets)){errors++;continue}
   const frozenAt=new Date(nowMs).toISOString();
   const oldTicket=race.bets.map(b=>({combination:b.combination,virtual_yen:b.virtual_yen}));
   const newTicket=newTrial.bets.map(b=>({
      combination:b.combination,virtual_yen:b.virtual_yen,
      scenario:b.scenario,head_course:b.head_course,relative_score:b.relative_score
   }));
   const binding={id,date:day,venue:race.venue,race:race.race,phase,cutoff_jst:race.cutoff_jst,
     source_updated_at_utc:live.updated_at_utc,source_frozen_at_utc:race.frozen_at_utc,
     original_fixed_sha256:race.sha256,created_at_utc:frozenAt,
     minutes_before_cutoff:+((cutoff-nowMs)/60000).toFixed(2),
     is_forward_fixed:true,virtual_budget_per_model_yen:50000,
     input_quality:{
       exhibition_confirmed_in_original:phase==='exhibition',
       source_age_minutes:+((nowMs-refreshed)/60000).toFixed(1),
       scope:'pre-cutoff original racer snapshot only; no outcomes/payouts or later exhibitions'
     },
     baseline:{model:race.model_version,bets:oldTicket,source_sha256:race.sha256},
     tactical:{model:newTrial.model,bets:newTicket,
       head_course_shares:newTrial.head_course_shares,
       relative_scores_uncalibrated:true}
   };
   binding.record_sha256=hash(binding);
   doc.records.push(binding);
   keys.add(id);created++;
 }
 doc.records.sort((a,b)=>dateAt(day,a.cutoff_jst)-dateAt(day,b.cutoff_jst)||a.venue.localeCompare(b.venue)||a.phase.localeCompare(b.phase));
 const status={schema:'boatlabs.tactical_ab_status_v1',event_date:day,checked_at_utc:new Date(nowMs).toISOString(),
  source_updated_at_utc:live.updated_at_utc,
  source_age_minutes:+((nowMs-refreshed)/60000).toFixed(1),
  stale_source:stale,new_forward_freezes:created,total_versions:doc.records.length,
  already_frozen:skippedExisting,excluded_late:skippedLate,excluded_stale:skippedStale,errors,
  baseline_versions:doc.records.filter(x=>x.phase==='baseline').length,
  exhibition_versions:doc.records.filter(x=>x.phase==='exhibition').length,
  notes:'Only confirmed GH-created before-cutoff version is counted for prospective test. Old data is preserved. No alerts, wagers or results used.'};
 return {doc,status};
}
function main(){
 const source=JSON.parse(fs.readFileSync(SOURCE,'utf8'));
 const fname=source.event_date+'.json',destination=path.join(DIR,fname),statusPath=path.join(DIR,'status-latest.json');
 fs.mkdirSync(DIR,{recursive:true});
 const earlier=fs.existsSync(destination)?JSON.parse(fs.readFileSync(destination,'utf8')):null;
 const before=earlier?.records?.map(x=>x.record_sha256)||[];
 const {doc,status}=run(source,earlier,Date.now());
 const after=doc.records.slice(0,before.length).map(x=>x.record_sha256);
 if(JSON.stringify(before)!==JSON.stringify(after)){
   // Date/phase ordering may insert new records between old ones, so verify by IDs.
   const lookup=new Map(doc.records.map(x=>[x.id,x.record_sha256]));
   if(earlier.records.some(x=>lookup.get(x.id)!==x.record_sha256))throw Error('Mutation of frozen record rejected');
 }
 fs.writeFileSync(destination,JSON.stringify(doc,null,2)+'\n');
 fs.writeFileSync(statusPath,JSON.stringify(status,null,2)+'\n');
 process.stdout.write(JSON.stringify(status)+'\n');
}
module.exports={run,validateBets,MIN_CUTOFF_LEAD_MS};
if(require.main===module)main();
