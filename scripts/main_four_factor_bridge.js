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
require('../app/venue-motor-exhibition.js');
require('../app/three-leg-primary.js');
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
// Compare actual 3連単 combinations and virtual allocations, not score drift or display order.
function ticketSignature(bets){
 return JSON.stringify(bets.map(b=>[b.combination,b.virtual_yen]).sort((a,b)=>a[0].localeCompare(b[0])));
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
  linked_primary_trial:input.linked_primary_trial===true,
  three_leg_primary_trial:input.three_leg_primary_trial===true,
  formal_insight_v24:input.formal_insight_v24===true,
  formal_head_risk_v25:input.formal_head_risk_v25===true,
  weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
  frozen_at_utc:input.frozen_at_utc,
  surface_trial_disabled:input.surface_trial_disabled===true,
  venue_tactics_disabled:input.venue_tactics_disabled===true
 });
 if(result.model!==(venueAware?'four-factor-v1.4-venue-aware-23-untrained':conditional?'four-factor-v1.3-conditional-scenarios-untrained':coverage?'four-factor-v1.2-head-coverage-untrained':'four-factor-v1.1-untrained')||!validBets(result.bets,model.ticketMaxPoints(input)))
  throw Error('Four-factor model returned invalid prediction / allocation');
 // Formal v2.4 is strictly forward-only. Freeze a same-instant v2.3
 // 120-outcome control BEFORE results; no later reconstruction is allowed.
 const insightRequested=input.formal_insight_v24===true;
 let insightV23Control=null;
 if(insightRequested){
  if(input.venue==='江戸川'||input.phase!=='exhibition'||input.linked_primary_trial!==true)
   throw Error('v2.4 requires linked exhibition and non-Edogawa venue');
  const previous=forecast({...input,formal_insight_v24:false,formal_head_risk_v25:false});
  if(!Array.isArray(previous.ranked_outcomes)||previous.ranked_outcomes.length!==120||
     !Array.isArray(result.ranked_outcomes)||result.ranked_outcomes.length!==120||
     previous.metadata?.four_factor?.formal_exhibition_balance_v24?.applied===true||
     result.metadata?.four_factor?.formal_exhibition_balance_v24?.requested!==true||
     result.metadata?.formal_inside_pressure_v24?.pre_cutoff_only!==true)
   throw Error('v2.4 same-time v2.3 canonical control missing');
  insightV23Control={
    prior_model:'four-factor-v2.3-conditional-second-primary-untrained',
    ranked_outcomes:previous.ranked_outcomes,
    formal_exhibition_balance:result.metadata.four_factor.formal_exhibition_balance_v24,
    formal_inside_pressure:result.metadata.formal_inside_pressure_v24,
    generated_pre_cutoff:true,result_data_used:false,
    same_120_canonical_inputs_except_v24:true,calibrated:false,
    frozen_at_utc:input.frozen_at_utc
  };
 }
 // v2.5 keeps the same 120-way canonical forecast and freezes its v2.4
 // control at the same time. This is a separate forward-only formal identity.
 let headRiskV25Control=null;
 if(input.formal_head_risk_v25===true){
  if(!insightRequested||input.phase!=='exhibition'||input.venue==='江戸川'||
     input.linked_primary_trial!==true)
   throw Error('v2.5 head switch requires eligible formal v2.4 exhibition');
  const control=forecast({...input,formal_head_risk_v25:false});
  const risk=result.metadata?.formal_inside_pressure_v25;
  if(!risk||risk.requested!==true||risk.pre_cutoff_only!==true||
     risk.result_data_used!==false||
     !Array.isArray(control.ranked_outcomes)||control.ranked_outcomes.length!==120||
     !Array.isArray(result.ranked_outcomes)||result.ranked_outcomes.length!==120||
     !validBets(control.bets,model.ticketMaxPoints(input)))
   throw Error('v2.5 same-time v2.4 ranked control missing');
  headRiskV25Control={
   prior_model:'four-factor-v2.4-entry-exhibition-balance-untrained',
   ranked_outcomes:control.ranked_outcomes,
   control_bets:control.bets,
   inside_head_rebalance:risk,
   generated_pre_cutoff:true,result_data_used:false,
   no_additional_stake:true,calibrated:false,
   frozen_at_utc:input.frozen_at_utc
  };
 }
 // Formal leg redistribution is explicitly gated by Python's pre-cutoff
 // policy. Freeze SAME-input old linked 120 outcomes as the true control.
 // A display diagnostic must never be substituted for a probability model.
 const legRequested=input.three_leg_primary_trial===true;
 const legEvidence=legRequested?result.metadata?.three_leg_primary_v1:null;
 if(legRequested&&(
    input.linked_primary_trial!==true||
    !legEvidence||
    legEvidence.version!=='three-leg-formal-redistribution-v0.1-untrained'||
    legEvidence.result_data_used!==false||
    legEvidence.source_exhibition_weight_unchanged!==true&&legEvidence.applied===true||
    !Array.isArray(legEvidence.rows)))
   throw Error('Invalid formal three-leg provenance');
 let threeLegControlRanked=null;
 if(legEvidence?.applied===true){
   const old=forecast({...input,three_leg_primary_trial:false});
   if(!validBets(old.bets,model.ticketMaxPoints(input))||
      !Array.isArray(old.ranked_outcomes)||old.ranked_outcomes.length!==120||
      !Array.isArray(result.ranked_outcomes)||result.ranked_outcomes.length!==120)
     throw Error('Missing old canonical linked control; cannot freeze leg primary');
   threeLegControlRanked=old.ranked_outcomes;
 }
 const surface=result.metadata?.venue_surface_v1||null;
 if(!surface||surface.version!=='venue-surface-v1-ex-edogawa')
  throw Error('Missing prospective venue surface diagnostics');
 const surfaceControl=surface.applied?forecast({
  venue:input.venue,phase:input.phase,racers:input.racers,
  linked_primary_trial:input.linked_primary_trial===true,
  three_leg_primary_trial:input.three_leg_primary_trial===true,
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
  try{roleSkillShadow=globalThis.BoatRoleSkillShadow.run(input,result.bets,{
    preserveHeadCoverage:input.role_skill_head_preserved_trial===true,
    preserveFollowerCoverage:input.role_skill_follower_coverage_trial===true
  });}
  catch(_){roleSkillShadow={version:input.role_skill_follower_coverage_trial===true?
    'racer-role-suitability-shadow-v0.3-follower-coverage':input.role_skill_head_preserved_trial===true?
    'racer-role-suitability-shadow-v0.2-head-preserved':'racer-role-suitability-shadow-v0.1',
    status:'unavailable',reason:'isolated_shadow_computation_failed',
    model_role:'shadow_validation',no_additional_stake:true};}
 }
 // Same-instant matched shadow, NEVER a replacement for the formal pick.
 // Failure is isolated: do not suppress the main forecast.
 let motorExhibitionShadow=null;
 if(input.venue_motor_exhibition_shadow_trial===true){
  try{
   const shadow=forecast({
     venue:input.venue,phase:input.phase,racers:input.racers,
  linked_primary_trial:input.linked_primary_trial===true,
     three_leg_primary_trial:input.three_leg_primary_trial===true,
     weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
     frozen_at_utc:input.frozen_at_utc,
     surface_trial_disabled:input.surface_trial_disabled===true,
     venue_tactics_disabled:input.venue_tactics_disabled===true,
     venue_motor_exhibition_shadow_trial:true
   });
   const detail=shadow.metadata?.venue_motor_exhibition_v1;
   if(!detail||detail.version!=='venue-motor-exhibition-shadow-v0.1'||
      detail.pre_cutoff_only!==true||detail.result_data_used!==false||
      !validBets(shadow.bets,model.ticketMaxPoints(input)))
     throw Error('invalid motor/exhibition shadow provenance or tickets');
   // Independent one-metric-at-a-time prospective comparisons.
   // This is NOT v2.3 ablation: the canonical four-factor component and
   // all source inputs stay unchanged. Only venue-motor concordance is removed.
   // Each variant must be computed at the SAME pre-cutoff instant, before
   // any race results, and cannot overwrite either the main or full shadow.
   const ablations=[];
   if(detail.status==='ready'&&detail.applied===true){
     const originalKeys=[...new Set(detail.metric_coverage||[])];
     for(const key of originalKeys){
       try{
         if(!Object.prototype.hasOwnProperty.call(globalThis.BoatVenueMotorExhibition.METRICS,key))
           throw Error('unexpected_metric');
         const candidate=forecast({
           venue:input.venue,phase:input.phase,racers:input.racers,
           linked_primary_trial:input.linked_primary_trial===true,
           three_leg_primary_trial:input.three_leg_primary_trial===true,
           weather_used:input.weather_used||null,venue_profile:input.venue_profile||null,
           frozen_at_utc:input.frozen_at_utc,
           surface_trial_disabled:input.surface_trial_disabled===true,
           venue_tactics_disabled:input.venue_tactics_disabled===true,
           venue_motor_exhibition_shadow_trial:true,
           venue_metric_ablation_key:key
         });
         const meta=candidate.metadata?.venue_motor_exhibition_v1;
         if(meta?.ablated_metric!==key||
            !validBets(candidate.bets,model.ticketMaxPoints(input)))
           throw Error('invalid_ablation_forecast');
         ablations.push({
           metric:key,status:'ready',
           bets:candidate.bets,
           same_point_count:candidate.bets.length===shadow.bets.length,
           same_virtual_budget:true,
           ticket_or_allocation_changed:ticketSignature(candidate.bets)!==ticketSignature(shadow.bets),
           original_metric_present:originalKeys.includes(key),
           actual_results_used:false,
           frozen_at_utc:input.frozen_at_utc,
           model_role:'shadow_validation',not_formal:true,no_additional_stake:true
         });
       }catch(e){
         ablations.push({metric:key,status:'unavailable',
           reason:String(e?.message||e).slice(0,90),not_formal:true,no_additional_stake:true});
       }
     }
   }
   motorExhibitionShadow={
     ...detail,status:detail.status,
     metric_ablation_protocol:'venue-shadow-v0.2-one-metric-removed',
     metric_ablations:ablations,
     trial_model_version:'venue-motor-exhibition-v0.1-shadow-untrained',
     control_model_version:result.model,
     control_bets:result.bets,
     trial_bets:shadow.bets,
     frozen_at_utc:input.frozen_at_utc,
     same_inputs_except_shadow:true,
     point_count_equal:result.bets.length===shadow.bets.length,
     bet_changes:ticketSignature(result.bets)!==ticketSignature(shadow.bets),
     score_or_order_changes:JSON.stringify(result.bets)!==JSON.stringify(shadow.bets),
     no_additional_stake:true,not_formal:true
   };
  }catch(_){
   motorExhibitionShadow={version:'venue-motor-exhibition-shadow-v0.1',
     status:'unavailable',reason:'isolated_shadow_computation_failed',
     model_role:'shadow_validation',not_formal:true,no_additional_stake:true};
  }
 }
 return {
  model_version:result.model,
  ...(insightV23Control?{formal_insight_v24:insightV23Control}:{}),
  ...(headRiskV25Control?{formal_head_risk_v25:headRiskV25Control}:{}),
  ...(input.linked_primary_trial===true?{ranked_outcomes:result.ranked_outcomes,ranked_source:result.ranked_source}:{}),
  ...(legRequested?{three_leg_primary_v1:legEvidence,
    ...(threeLegControlRanked?{three_leg_control_ranked:threeLegControlRanked}:{})}:{}),

  ...(motorExhibitionShadow?{venue_motor_exhibition_shadow:motorExhibitionShadow}:{}),
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
module.exports={run,validBets,ticketSignature};
if(require.main===module)main();
