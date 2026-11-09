#!/usr/bin/env node
/* Pre-cutoff shadow selector only. Saved canonical scores; no outcome or payout. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const SCHEMA='boatlabs.conditional_second_forward_v1';
const MODEL='conditional-second-coverage-v0.1-shadow-untrained';
// Formal model compatibility is narrow by design. This code is SHADOW ONLY;
// eligibility still requires existing verified pre-cutoff canonical 120.
const SUPPORTED_FORMAL_MODELS=new Set([
 'four-factor-v2.2-linked-primary-untrained',
 'four-factor-v2.3-conditional-second-primary-untrained'
]);
const MIN_LEAD_MS=5*60*1000,MAX_SOURCE_AGE_MS=45*60*1000;
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x),'utf8').digest('hex');
const pair=x=>x.split('-').slice(0,2).join('-');
const coverage=bets=>new Set(bets.map(b=>pair(b.combination))).size;
function canonical(rows){
 if(!Array.isArray(rows)||rows.length!==120)throw Error('canonical_120_missing');
 const required=new Set();
 for(let a=1;a<=6;a++)for(let b=1;b<=6;b++)for(let c=1;c<=6;c++)
  if(a!==b&&a!==c&&b!==c)required.add([a,b,c].join('-'));
 const seen=new Set();let total=0;
 for(const row of rows){
  const name=row?.combination,score=row?.relative_score;
  if(!required.has(name)||seen.has(name)||typeof score!=='number'||
    !Number.isFinite(score)||score<=0)throw Error('canonical_120_invalid');
  seen.add(name);total+=score;
 }
 if(Math.abs(total-1)>0.000001)throw Error('canonical_mass_invalid');
 return rows.map(r=>({combination:r.combination,relative_score:r.relative_score}))
  .sort((a,b)=>b.relative_score-a.relative_score||a.combination.localeCompare(b.combination));
}
function validBets(bets){
 return Array.isArray(bets)&&bets.length>=4&&bets.length<=24&&
  bets.every(b=>typeof b?.combination==='string'&&
   /^[1-6]-[1-6]-[1-6]$/.test(b.combination)&&
   new Set(b.combination.split('-')).size===3&&
   Number.isSafeInteger(b.virtual_yen)&&b.virtual_yen>=1000&&
   b.virtual_yen%1000===0)&&
  new Set(bets.map(b=>b.combination)).size===bets.length&&
  bets.reduce((s,b)=>s+b.virtual_yen,0)===50000;
}
function allocate(selected){
 const n=selected.length,remaining=50-n;
 const total=selected.reduce((s,x)=>s+x.relative_score,0);
 const quotas=selected.map(x=>remaining*x.relative_score/total);
 const extra=quotas.map(Math.floor);
 const deficit=remaining-extra.reduce((s,x)=>s+x,0);
 const order=quotas.map((q,i)=>i).sort((i,j)=>
   (quotas[j]-extra[j])-(quotas[i]-extra[i])||i-j);
 for(const i of order.slice(0,deficit))extra[i]++;
 return selected.map((x,i)=>({combination:x.combination,virtual_yen:1000*(1+extra[i])}));
}
function trialSelection(rows,formalBets){
 const ranked=canonical(rows);
 if(!validBets(formalBets))throw Error('invalid_formal_bets');
 const count=formalBets.length;
 // Hypothesis-only guardrails; 75% and 60% are NOT learned probabilities.
 const minimum=ranked[count-1].relative_score*0.75;
 const pairGoal=Math.ceil(count*0.6);
 const selected=[ranked[0]],used=new Set([ranked[0].combination]);
 const pairs=new Set([pair(ranked[0].combination)]);
 for(const item of ranked.slice(1)){
  if(pairs.size>=pairGoal||item.relative_score<minimum)break;
  const key=pair(item.combination);
  if(pairs.has(key))continue;
  selected.push(item);used.add(item.combination);pairs.add(key);
 }
 for(const item of ranked){
  if(selected.length===count)break;
  if(used.has(item.combination))continue;
  selected.push(item);used.add(item.combination);
 }
 const bets=allocate(selected);
 if(!validBets(bets)||bets.length!==formalBets.length)throw Error('invalid_shadow_bets');
 return {model:MODEL,bets,formal_pair_coverage:coverage(formalBets),
  shadow_pair_coverage:coverage(bets),pair_target:pairGoal,
  candidate_minimum_ratio:0.75,relative_scores_uncalibrated:true};
}
function run(live,previous,nowMs){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(live?.event_date)||!Array.isArray(live?.forecast_races))
  throw Error('invalid_live_snapshot');
 if(!Number.isFinite(nowMs))throw Error('invalid_clock');
 const refreshed=Date.parse(live.updated_at_utc);
 if(!Number.isFinite(refreshed)||refreshed>nowMs+60000)throw Error('invalid_source_clock');
 const stale=nowMs-refreshed>MAX_SOURCE_AGE_MS;
 const doc=previous?.event_date===live.event_date?structuredClone(previous):{
  schema:SCHEMA,event_date:live.event_date,records:[]};
 if(doc.schema!==SCHEMA||!Array.isArray(doc.records))throw Error('invalid_ledger');
 const hashes=new Map();
 for(const row of doc.records){
  const {record_sha256,...original}=row;
  if(!row.id||!row.record_sha256||hashes.has(row.id)||hash(original)!==row.record_sha256)
   throw Error('immutable_record_changed');
  hashes.set(row.id,row.record_sha256);
 }
 const status={schema:'boatlabs.conditional_second_status_v1',
  event_date:live.event_date,checked_at_utc:new Date(nowMs).toISOString(),
  new_forward_freezes:0,already_frozen:0,excluded_late:0,
  excluded_stale:0,excluded_not_formal:0,excluded_missing_120:0,errors:0};
 for(const race of live.forecast_races){
  if(race.phase!=='exhibition'||race.ticket_status!=='formal'||
     !SUPPORTED_FORMAL_MODELS.has(race.model_version)){
    status.excluded_not_formal++;continue;
  }
  const ranked=race.interaction_primary?.ranked_outcomes;
  if(race.interaction_primary?.canonical_source!=='linked-four-factor-venue-st-wake-120'||
     !Array.isArray(ranked)){
    status.excluded_missing_120++;continue;
  }
  const id=[race.venue,race.race,race.sha256].join('|');
  if(hashes.has(id)){status.already_frozen++;continue;}
  const cutoff=Date.parse(live.event_date+'T'+race.cutoff_jst+':00+09:00');
  const frozen=Date.parse(race.frozen_at_utc);
  if(!Number.isFinite(cutoff)||!Number.isFinite(frozen)||
     !/^[0-9a-f]{64}$/.test(race.sha256||'')){status.errors++;continue;}
  if(nowMs>=cutoff-MIN_LEAD_MS||frozen>=cutoff-MIN_LEAD_MS||frozen>nowMs){
   status.excluded_late++;continue;
  }
  if(stale){status.excluded_stale++;continue;}
  let candidate;
  try{candidate=trialSelection(ranked,race.bets);}catch(_){status.errors++;continue;}
  const formal=race.bets.map(b=>({combination:b.combination,virtual_yen:b.virtual_yen}));
  const row={id,date:live.event_date,venue:race.venue,race:race.race,
   phase:'exhibition',cutoff_jst:race.cutoff_jst,
   source_frozen_at_utc:race.frozen_at_utc,
   source_updated_at_utc:live.updated_at_utc,
   original_fixed_sha256:race.sha256,
   created_at_utc:new Date(nowMs).toISOString(),
   minutes_before_cutoff:+((cutoff-nowMs)/60000).toFixed(2),
   is_forward_fixed:true,point_count:formal.length,
   virtual_budget_per_model_yen:50000,
   formal_control:{model:race.model_version,bets:formal},
   second_pair_trial:candidate,
   same_input_same_point_count:true,no_additional_stake:true,
   not_formal:true,provenance:'read-only saved pre-cutoff canonical 120; no results or payouts'};
  row.record_sha256=hash(row);doc.records.push(row);status.new_forward_freezes++;
 }
 doc.records.sort((a,b)=>a.id.localeCompare(b.id));
 for(const [id,s] of hashes)
  if(doc.records.find(row=>row.id===id)?.record_sha256!==s)throw Error('immutable_record_changed');
 status.total_versions=doc.records.length;status.source_stale=stale;
 status.note='Count only GH-committed pre-cutoff records and match official snapshot SHA in later audit.';
 return {doc,status};
}
function main(){
 const live=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
 const dir='app/data/experiments',out=path.join(dir,'conditional-second-'+live.event_date+'.json');
 fs.mkdirSync(dir,{recursive:true});
 const previous=fs.existsSync(out)?JSON.parse(fs.readFileSync(out,'utf8')):null;
 const {doc,status}=run(live,previous,Date.now());
 fs.writeFileSync(out,JSON.stringify(doc,null,2)+'\n');
 fs.writeFileSync(path.join(dir,'conditional-second-status-latest.json'),
  JSON.stringify(status,null,2)+'\n');
 process.stdout.write(JSON.stringify(status)+'\n');
}
module.exports={canonical,validBets,trialSelection,run,MIN_LEAD_MS,SUPPORTED_FORMAL_MODELS};
if(require.main===module)main();
