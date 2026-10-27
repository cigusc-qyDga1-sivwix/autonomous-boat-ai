#!/usr/bin/env node
/* Canonical pre-cutoff engine adapter: untrained four-factor same browser
 * calculation as the BOAT LAB browser, no duplicated Python coefficients.
 * Reads only explicit incoming pre-race data. Returns JSON to stdout.
 * No URLs, result lookup, payouts, notifications or actual betting.
 */
'use strict';
const fs=require('node:fs');
require('../app/four-factor.js');
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
 const coverage=input.head_coverage_trial===true;
 const forecast=coverage?model.forecastFourFactorCoverage:model.forecastFourFactorOpen;
 const result=forecast({
  venue:input.venue,phase:input.phase,racers:input.racers,
  weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
  frozen_at_utc:input.frozen_at_utc,
  surface_trial_disabled:input.surface_trial_disabled===true
 });
 if(result.model!==(coverage?'four-factor-v1.2-head-coverage-untrained':'four-factor-v1.1-untrained')||!validBets(result.bets))
  throw Error('Four-factor model returned invalid prediction / allocation');
 const surface=result.metadata?.venue_surface_v1||null;
 if(!surface||surface.version!=='venue-surface-v1-ex-edogawa')
  throw Error('Missing prospective venue surface diagnostics');
 const surfaceControl=surface.applied?forecast({
  venue:input.venue,phase:input.phase,racers:input.racers,
  weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
  frozen_at_utc:input.frozen_at_utc,surface_trial_disabled:true
 }):null;
 if(surfaceControl&&!validBets(surfaceControl.bets))
  throw Error('Invalid same-time surface control');
 if(!Array.isArray(result.head_course_shares)||result.head_course_shares.length!==6||
    result.metadata?.start_v07?.slit_signals?.length!==6||
    result.metadata?.wake_v09?.pre_cutoff_only!==true||
    result.metadata?.wake_v09?.head_course_exposure?.length!==6)
  throw Error('Missing ST / head coverage diagnostics');
 return {
  model_version:result.model,
  head_coverage_control:coverage?{
   model_version:'four-factor-v1.1-untrained',
   bets:model.forecastFourFactorOpen({...input}).bets,
   frozen_at_utc:input.frozen_at_utc,generated_pre_cutoff:true,
   scope:'same-input ticket selection control only; no additional formal stake'
  }:null,
  four_factor:result.metadata.four_factor,
  venue_surface_v1:surface,
  venue_surface_ab:surfaceControl?{
   control_model:'four-factor-v1.1-without-venue-surface',
   control_bets:surfaceControl.bets,
   trial_bets:result.bets,
   generated_pre_cutoff:true,
   same_inputs_except_surface:true,
   scope:'shadow_research_only_no_formal_stake'
  }:null,
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
 }catch(e){process.stderr.write('MAIN_FOUR_FACTOR_BRIDGE: '+String(e?.message||e)+'\n');process.exitCode=1;}
}
module.exports={run,validBets};
if(require.main===module)main();
