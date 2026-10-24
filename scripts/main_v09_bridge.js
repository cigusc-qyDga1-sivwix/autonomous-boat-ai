#!/usr/bin/env node
/* Canonical pre-cutoff engine adapter: untrained v0.9 same browser
 * calculation as the BOAT LAB browser, no duplicated Python coefficients.
 * Reads only explicit incoming pre-race data. Returns JSON to stdout.
 * No URLs, result lookup, payouts, notifications or actual betting.
 */
'use strict';
const fs=require('node:fs');
require('../app/tactical-1m.js');
const model=globalThis.BoatTacticalModel;
function validBets(bets){
 return Array.isArray(bets)&&bets.length>=4&&bets.length<=12&&
  new Set(bets.map(x=>x.combination)).size===bets.length&&
  bets.every(x=>/^[1-6]-[1-6]-[1-6]$/.test(x.combination)&&
    new Set(x.combination.split('-')).size===3&&
    Number.isSafeInteger(x.virtual_yen)&&x.virtual_yen>=1000&&
    x.virtual_yen%1000===0)&&
  bets.reduce((s,x)=>s+x.virtual_yen,0)===50000;
}
function run(input){
 if(!input||typeof input!=='object'||!Array.isArray(input.racers)||
    input.racers.length!==6)throw Error('Six complete pre-cutoff racers required');
 if(!input.venue||!Number.isFinite(Date.parse(input.frozen_at_utc)))throw Error('Pre-cutoff source identity required');
 const result=model.forecastWakeIntegrated({
  venue:input.venue,phase:input.phase,racers:input.racers,
  weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
  frozen_at_utc:input.frozen_at_utc
 });
 if(result.model!=='tactical-outside-start-wake-v0.9-untrained'||!validBets(result.bets))
  throw Error('v0.9 wake model returned invalid prediction / allocation');
 if(!Array.isArray(result.head_course_shares)||result.head_course_shares.length!==6||
    result.metadata?.start_v07?.slit_signals?.length!==6||
    result.metadata?.wake_v09?.pre_cutoff_only!==true||
    result.metadata?.wake_v09?.head_course_exposure?.length!==6)
  throw Error('Missing ST / head coverage diagnostics');
 return {
  model_version:result.model,
  bets:result.bets,
  head_course_shares:result.head_course_shares,
  role_coverage:result.role_coverage,
  role_changes:result.role_changes,
  start_v07:result.metadata.start_v07,
  coupled_v06:result.metadata.coupled_v06,
  wake_v09:result.metadata.wake_v09,
  relative_scores_uncalibrated:true
 };
}
function main(){
 try{
  const input=JSON.parse(fs.readFileSync(0,'utf8'));
  const payload=run(input);
  process.stdout.write(JSON.stringify(payload)+'\n');
 }catch(e){process.stderr.write('MAIN_V09_BRIDGE: '+String(e?.message||e)+'\n');process.exitCode=1;}
}
module.exports={run,validBets};
if(require.main===module)main();
