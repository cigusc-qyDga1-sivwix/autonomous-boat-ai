#!/usr/bin/env node
/* Canonical pre-cutoff engine adapter: untrained four-factor same browser
 * calculation as the BOAT LAB browser, no duplicated Python coefficients.
 * Reads only explicit incoming pre-race data. Returns JSON to stdout.
 * No URLs, result lookup, payouts, notifications or actual betting.
 */
'use strict';
const fs=require('node:fs');
require('../app/four-factor.js');
require('../app/venue-tactics-v2.js');
require('../app/tactical-1m.js');
require('../app/role-skill-shadow.js');
const model=globalThis.BoatTacticalModel;
function validBets(bets,maxPoints=12){
 return Array.isArray(bets)&&bets.length>=4&&bets.length<=maxPoints&&
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
 const venueAware=input.venue_tactics_trial===true;
 const conditional=!venueAware&&input.postrace_conditional_trial===true;
 const coverage=!conditional&&!venueAware&&input.head_coverage_trial===true;
 const forecast=venueAware?model.forecastFourFactorVenueAware:
   conditional?model.forecastFourFactorConditional:
   coverage?model.forecastFourFactorCoverage:model.forecastFourFactorOpen;
 const result=forecast({
  venue:input.venue,phase:input.phase,racers:input.racers,
  weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
  frozen_at_utc:input.frozen_at_utc,
  surface_trial_disabled:input.surface_trial_disabled===true,
  venue_tactics_disabled:input.venue_tactics_disabled===true
 });
 if(result.model!==(venueAware?'four-factor-v1.4-venue-aware-23-untrained':conditional?'four-factor-v1.3-conditional-scenarios-untrained':coverage?'four-factor-v1.2-head-coverage-untrained':'four-factor-v1.1-untrained')||!validBets(result.bets,model.ticketMaxPoints(input)))
  throw Error('Four-factor model returned invalid prediction / allocation');
 const surface=result.metadata?.venue_surface_v1||null;
 if(!surface||surface.version!=='venue-surface-v1-ex-edogawa')
  throw Error('Missing prospective venue surface diagnostics');
 const surfaceControl=surface.applied?forecast({
  venue:input.venue,phase:input.phase,racers:input.racers,
  weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
  frozen_at_utc:input.frozen_at_utc,surface_trial_disabled:true,
  venue_tactics_disabled:input.venue_tactics_disabled===true
 }):null;
 if(surfaceControl&&!validBets(surfaceControl.bets,model.ticketMaxPoints(input)))
  throw Error('Invalid same-time surface control');
 if(!Array.isArray(result.head_course_shares)||result.head_course_shares.length!==6||
    result.metadata?.start_v07?.slit_signals?.length!==6||
    result.metadata?.wake_v09?.pre_cutoff_only!==true||
    result.metadata?.wake_v09?.head_course_exposure?.length!==6)
  throw Error('Missing ST / head coverage diagnostics');
 if((conditional||venueAware)&&(!result.metadata?.postrace_v13?.pre_cutoff_only||
    result.metadata.postrace_v13.result_data_used!==false))
  throw Error('Missing result-blind v1.3 provenance');
 const venueMeta=venueAware?result.metadata?.venue_tactics_v2:null;
 if(venueAware&&(!venueMeta||venueMeta.version!=='venue-tactics-v2-23venues-ex-edogawa'||
    venueMeta.pre_cutoff_only!==true||venueMeta.result_data_used!==false))
    throw Error('Missing venue v1.4 pre-cutoff provenance');
 const venueControl=venueAware?model.forecastFourFactorVenueAware({
   ...input,venue_tactics_disabled:true,
   experimental_variant:'four-factor-v1.4'
 }):null;
 if(venueControl&&!validBets(venueControl.bets,model.ticketMaxPoints(input)))throw Error('Invalid venue v1.4 ablation bets');
 // Isolated research calculation. Failure must never suppress a formal forecast.
 let roleSkillShadow=null;
 if(input.role_skill_shadow_trial===true){
  try{roleSkillShadow=globalThis.BoatRoleSkillShadow.run(input,result.bets);}
  catch(_){roleSkillShadow={version:'racer-role-suitability-shadow-v0.1',
    status:'unavailable',reason:'isolated_shadow_computation_failed',
    model_role:'shadow_validation',no_additional_stake:true};}
 }
 return {
  model_version:result.model,
  ...(roleSkillShadow?{role_skill_shadow:roleSkillShadow}:{}),
  venue_tactics_v2:venueMeta,
  venue_tactics_ab:venueAware?{
   control_model:'four-factor-v1.4-without-venue-tactics',
   control_bets:venueControl.bets,trial_bets:result.bets,
   prior_model:'four-factor-v1.3-conditional-scenarios-untrained',
   prior_bets:model.forecastFourFactorConditional({...input,experimental_variant:'four-factor-v1.3'}).bets,
   frozen_at_utc:input.frozen_at_utc,generated_pre_cutoff:true,
   point_count_unchanged:true,no_additional_stake:true,
   same_inputs_except_venue_tactics:true
  }:null,
  postrace_conditional_v13:(conditional||venueAware)?result.metadata?.postrace_v13:null,
  postrace_conditional_control:(conditional||venueAware)?{
   model_version:'four-factor-v1.2-head-coverage-untrained',
   bets:model.forecastFourFactorCoverage({...input,postrace_conditional_trial:false,head_coverage_trial:true}).bets,
   frozen_at_utc:input.frozen_at_utc,generated_pre_cutoff:true,
   scope:'same-input v1.2 head-coverage research control, no extra stake'
  }:null,
  head_coverage_control:coverage?{
   model_version:'four-factor-v1.1-untrained',
   bets:model.forecastFourFactorOpen({...input}).bets,
   frozen_at_utc:input.frozen_at_utc,generated_pre_cutoff:true,
   scope:'same-input ticket selection control only; no additional formal stake'
  }:null,
  four_factor:result.metadata.four_factor,
  venue_surface_v1:surface,
  venue_surface_ab:surfaceControl?{
   control_model:venueAware?'four-factor-v1.4-without-venue-surface':coverage?'four-factor-v1.2-head-coverage-without-venue-surface':'four-factor-v1.1-without-venue-surface',
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
