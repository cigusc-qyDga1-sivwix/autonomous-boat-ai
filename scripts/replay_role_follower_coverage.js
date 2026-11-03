#!/usr/bin/env node
'use strict';
// Retrospective diagnostics only. Never rewrite an input ledger or formal bets.
const fs=require('node:fs');
require('./main_four_factor_bridge.js');
const skill=require('../app/role-skill-shadow.js');
function run(ledger){
 const total={date:ledger.event_date,research_only:true,forward_evidence:false,
  records:0,unverified:0,stored_v02_mismatches:0,changed:0,
  control:{n:0,hits:0,stake:0,payout:0,head_miss:0,second_miss:0,third_miss:0},
  outside:{actual_by_position:[0,0,0],covered_by_position:[0,0,0],third_pair_misses:0,
   supported_boat_records:0,verified_supported:0,supported_wins:0,supported_top3:0},
  trial:{n:0,hits:0,stake:0,payout:0,head_miss:0,second_miss:0,third_miss:0}};
 const signature=b=>JSON.stringify(b.map(t=>[t.combination,t.virtual_yen]).sort());
 for(const record of Object.values(ledger.race_records)){
  const versions=record.versions.filter(v=>Number.isFinite(Date.parse(v.frozen_at_utc))&&
   Number.isFinite(Date.parse(v.cutoff_iso_jst))&&Date.parse(v.frozen_at_utc)<Date.parse(v.cutoff_iso_jst))
   .sort((a,b)=>Date.parse(a.frozen_at_utc)-Date.parse(b.frozen_at_utc));
  const v=versions.at(-1);if(!v)continue;
  const pre={venue:v.venue,phase:v.phase,frozen_at_utc:v.frozen_at_utc,
   racers:v.racers,venue_profile:v.venue_profile,weather_used:v.weather_used};
  const previous=skill.run(pre,v.bets,{preserveHeadCoverage:true});
  const trial=skill.run(pre,v.bets,{preserveHeadCoverage:true,preserveFollowerCoverage:true});
  total.records++;
  if(v.role_skill_shadow?.version==='racer-role-suitability-shadow-v0.2-head-preserved'&&
    signature(previous.bets)!==signature(v.role_skill_shadow.bets))total.stored_v02_mismatches++;
  if(signature(trial.bets)!==signature(v.bets))total.changed++;
  const pay=record.official_pay;
  for(const e of v.postrace_conditional_v13?.observations||[]){
   if(e.course<4||!e.outside_head_supported)continue;
   total.outside.supported_boat_records++;
   if(pay?.verified&&/^([1-6]-){2}[1-6]$/.test(pay.finish)&&
      new Set(pay.finish.split('-')).size===3&&Number.isFinite(pay.payout_per_100)){
    total.outside.verified_supported++;
    total.outside.supported_wins+=Number(pay.finish.split('-')[0]===String(e.lane));
    total.outside.supported_top3+=Number(pay.finish.split('-').includes(String(e.lane)));
   }
  }
  if(!pay?.verified||!/^([1-6]-){2}[1-6]$/.test(pay.finish)||
    new Set(pay.finish.split('-')).size!==3||!Number.isFinite(pay.payout_per_100)){
   total.unverified++;continue;
  }
  const finish=pay.finish.split('-');
  finish.forEach((lane,pos)=>{
   if(Number(lane)<4)return;
   total.outside.actual_by_position[pos]++;
   total.outside.covered_by_position[pos]+=Number(v.bets.some(b=>b.combination.split('-')[pos]===lane));
  });
  if(Number(finish[2])>=4&&!v.bets.some(b=>b.combination===pay.finish)&&
    v.bets.some(b=>b.combination.startsWith(`${finish[0]}-${finish[1]}-`)))total.outside.third_pair_misses++;
  for(const [name,bets] of [['control',v.bets],['trial',trial.bets]]){
   const stats=total[name];stats.n++;stats.stake+=bets.reduce((s,b)=>s+b.virtual_yen,0);
   const hit=bets.find(b=>b.combination===pay.finish);
   if(hit){stats.hits++;stats.payout+=hit.virtual_yen*pay.payout_per_100/100;}
   else{
    const [h,s]=pay.finish.split('-');
    const kind=!bets.some(b=>b.combination.split('-')[0]===h)?'head_miss':
     !bets.some(b=>b.combination.startsWith(`${h}-${s}-`))?'second_miss':'third_miss';stats[kind]++;
   }
  }
 }
 for(const stats of [total.control,total.trial])stats.roi_pct=stats.stake?+(100*stats.payout/stats.stake).toFixed(2):null;
 return total;
}
module.exports={run};
if(require.main===module)process.stdout.write(JSON.stringify(run(JSON.parse(fs.readFileSync(process.argv[2],'utf8'))),null,2)+'\n');
