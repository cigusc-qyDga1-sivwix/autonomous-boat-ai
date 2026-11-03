#!/usr/bin/env node
'use strict';
const fs=require('node:fs');
require('./main_four_factor_bridge.js');
const shadow=require('../app/counterplay-shadow.js');
function run(ledger){
 const out={event_date:ledger.event_date,research_only:true,forward_evidence:false,
  eligible:0,unavailable:0,unverified:0,active_duel_races:0,
  main:{n:0,hits:0,stake:0,payout:0},same_selector_control:{n:0,hits:0,stake:0,payout:0},
  trial:{n:0,hits:0,stake:0,payout:0}};
 for(const r of Object.values(ledger.race_records)){
  const v=r.versions.filter(v=>Number.isFinite(Date.parse(v.frozen_at_utc))&&
    Date.parse(v.frozen_at_utc)<Date.parse(v.cutoff_iso_jst))
    .sort((a,b)=>Date.parse(a.frozen_at_utc)-Date.parse(b.frozen_at_utc)).at(-1);
  if(!v||v.phase!=='exhibition'){out.unavailable++;continue;}
  let trial;
  try{trial=shadow.run({venue:v.venue,phase:v.phase,cutoff_iso_jst:v.cutoff_iso_jst,
    frozen_at_utc:v.frozen_at_utc,racers:v.racers,weather_used:v.weather_used,venue_profile:v.venue_profile},v.bets);}
  catch(_){out.unavailable++;continue;}
  out.eligible++;out.active_duel_races+=Number(trial.active_duels>0);
  const pay=r.official_pay;
  if(!pay?.verified||!/^([1-6]-){2}[1-6]$/.test(pay.finish)||
    new Set(pay.finish.split('-')).size!==3||!Number.isFinite(pay.payout_per_100)){out.unverified++;continue;}
  for(const [name,bets] of [['main',v.bets],['same_selector_control',trial.same_selector_control_bets],['trial',trial.bets]]){
   const s=out[name];s.n++;s.stake+=bets.reduce((a,b)=>a+b.virtual_yen,0);
   const hit=bets.find(b=>b.combination===pay.finish);
   if(hit){s.hits++;s.payout+=hit.virtual_yen*pay.payout_per_100/100;}
  }
 }
 for(const s of [out.main,out.same_selector_control,out.trial])s.roi_pct=s.stake?+(100*s.payout/s.stake).toFixed(2):null;
 return out;
}
module.exports={run};
if(require.main===module)process.stdout.write(JSON.stringify(run(JSON.parse(fs.readFileSync(process.argv[2],'utf8'))),null,2)+'\n');
