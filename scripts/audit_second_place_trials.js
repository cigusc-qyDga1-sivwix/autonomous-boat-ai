#!/usr/bin/env node
/* Read-only postrace comparison. NEVER creates/changes predictions or picks. */
'use strict';
const fs=require('node:fs');
const sha=require('node:crypto').createHash;
const {validBets,SUPPORTED_FORMAL_MODELS}=require('./freeze_second_place_trials.js');
function signature(bets){return bets.map(b=>b.combination+':'+b.virtual_yen).sort().join('|');}
function score(bets,finish,pay){
 const bet=bets.find(b=>b.combination===finish);
 const heads=new Set(bets.map(b=>b.combination.slice(0,1)));
 const pairs=new Set(bets.map(b=>b.combination.slice(0,3)));
 const stage=bet?'hit':heads.has(finish[0])?(pairs.has(finish.slice(0,3))?'third_miss':'second_miss'):'head_miss';
 return {stage,hit:Number(!!bet),first_second_captured:Number(!!bet||stage==='third_miss'),
         paid:bet?bet.virtual_yen*pay/100:0};
}
function audit(trials,live){
 if(trials?.schema!=='boatlabs.conditional_second_forward_v1'||
    trials.event_date!==live?.event_date||!Array.isArray(trials.records))
  throw Error('audit_date_or_schema_mismatch');
 const date=trials.event_date;
 const forecast=new Map((live.forecast_races||[]).map(r=>[[r.venue,r.race,r.sha256].join('|'),r]));
 const pay=live.official_results||{}, alerts=live.settlement_alerts||{};
 const included=[],excluded={};
 const skip=k=>excluded[k]=(excluded[k]||0)+1;
 for(const r of trials.records){
  const {record_sha256,...unsigned}=r;
  const actualHash=sha('sha256').update(JSON.stringify(unsigned),'utf8').digest('hex');
  if(actualHash!==record_sha256){skip('record_hash_mismatch');continue;}
  const cutoff=Date.parse(date+'T'+r.cutoff_jst+':00+09:00');
  const archived=Date.parse(r.created_at_utc);
  const originalFreeze=Date.parse(r.source_frozen_at_utc);
  if(!Number.isFinite(cutoff)||!Number.isFinite(archived)||!Number.isFinite(originalFreeze)||
     archived>cutoff-5*60*1000||originalFreeze>cutoff-5*60*1000){skip('late_or_unproven');continue;}
  const x=forecast.get(r.id);
  if(!x||x.sha256!==r.original_fixed_sha256||
     !SUPPORTED_FORMAL_MODELS.has(x.model_version)||
     x.model_version!==r.formal_control?.model||
     signature(x.bets||[])!==signature(r.formal_control?.bets||[])){
    skip('source_sha_or_ticket_mismatch');continue;
  }
  const id=date+'|'+r.venue+'|'+r.race;
  if(alerts[id]){skip('refund_cancellation_conflict');continue;}
  const p=pay[id];
  if(!p||p.verified!==true||p.source!=='boatrace_official_pay'||
     p.snapshot_sha256&&p.snapshot_sha256!==x.sha256||
     p.virtual_stake!==50000||
     !Number.isInteger(p.payout_per_100)||p.payout_per_100<100||
     typeof p.finish!=='string'||! /^[1-6]-[1-6]-[1-6]$/.test(p.finish)||
     new Set(p.finish.split('-')).size!==3){skip('unverified_official_result');continue;}
  const b=r.second_pair_trial?.bets;
  if(!validBets(b)||!validBets(r.formal_control?.bets)||
     b.length!==r.formal_control.bets.length){skip('invalid_or_unequal_bets');continue;}
  included.push({venue:r.venue,race:r.race,finish:p.finish,
   official_payout_per_100:p.payout_per_100,
   formal:score(r.formal_control.bets,p.finish,p.payout_per_100),
   trial:score(b,p.finish,p.payout_per_100)});
 }
 const metrics=k=>{
  const n=included.length,hits=included.reduce((s,x)=>s+x[k].hit,0);
  const paired=included.reduce((s,x)=>s+x[k].first_second_captured,0);
  const paid=included.reduce((s,x)=>s+x[k].paid,0),stake=50000*n;
  return {races:n,hits,hit_rate:n?hits/n:null,first_second_captured:paired,
   pair_capture_rate:n?paired/n:null,virtual_stake_yen:stake,
   virtual_payout_yen:paid,virtual_profit_yen:paid-stake,
   return_rate:stake?paid/stake:null,
   head_miss:included.filter(x=>x[k].stage==='head_miss').length,
   second_miss:included.filter(x=>x[k].stage==='second_miss').length,
   third_miss:included.filter(x=>x[k].stage==='third_miss').length};
 };
 return {schema:'boatlabs.conditional_second_reconciliation_v1',
  event_date:date,paired_verified_races:included.length,
  exclusions:excluded,formal:metrics('formal'),trial:metrics('trial'),
  observed_differences:{hit_count:metrics('trial').hits-metrics('formal').hits,
   pair_capture_count:metrics('trial').first_second_captured-metrics('formal').first_second_captured,
   virtual_profit_yen:metrics('trial').virtual_profit_yen-metrics('formal').virtual_profit_yen},
  provisional_commit_time_not_verified:true,
  forward_evidence_note:'GitHub publish/commit time still needs verification before qualifying these rows as prospectively frozen.',
  not_formal:true,no_additional_stake:true,
  records:included};
}
function projectLedger(ledger){
 if(!ledger||!ledger.event_date||!ledger.race_records)throw Error('dated_ledger_required');
 const forecast_races=[],official_results={},settlement_alerts={};
 for(const record of Object.values(ledger.race_records)){
  const versions=record?.versions||[];
  if(!versions.length)continue;
  const last=versions[versions.length-1];
  forecast_races.push({...last,venue:last.venue||record.venue,
    race:last.race||record.race});
  const key=ledger.event_date+'|'+record.venue+'|'+record.race;
  if(record.official_pay)official_results[key]={
   ...record.official_pay,
   // Raw dated ledgers store official pay without a derived stake/SHA.
   // Bind it read-only to the immutable latest snapshot, then require
   // the independently frozen trial's SHA to match that snapshot.
   virtual_stake:record.official_pay.virtual_stake??(Array.isArray(last.bets)?
     last.bets.reduce((sum,b)=>sum+(b.virtual_yen||0),0):0),
   snapshot_sha256:record.official_pay.snapshot_sha256||last.sha256
  };
  if(record.official_review||record.official_conflict||
     record.official_pay?.void_trifecta||
     record.official_pay?.refunded_boats?.length)settlement_alerts[key]=true;
 }
 return {event_date:ledger.event_date,forecast_races,official_results,settlement_alerts};
}
function main(){
 const day=process.argv[2]||new Intl.DateTimeFormat('en-CA',{
  timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const base='app/data/experiments/conditional-second-'+day+'.json';
 const source='app/data/live/'+day+'.json';
 if(!fs.existsSync(base)||!fs.existsSync(source)){
  process.stdout.write(JSON.stringify({date:day,status:'NO_SAME_DATE_TRIAL_AND_RESULT_LEDGER'})+'\n');
  return;
 }
 const result=audit(JSON.parse(fs.readFileSync(base,'utf8')),
   projectLedger(JSON.parse(fs.readFileSync(source,'utf8'))));
 process.stdout.write(JSON.stringify(result)+'\n');
}
module.exports={audit,score,projectLedger};
if(require.main===module)main();
