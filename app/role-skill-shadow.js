/* BOAT LAB: forward-only athlete role suitability shadow.
 * Heuristic residuals are NOT observed personal 2nd/3rd rates.
 * It only re-ranks existing same-input pre-cutoff scenario scores.
 * Official predictions and their allocation are unchanged.
 */
(function(root){
'use strict';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const valid=(v,a,b)=>typeof v==='number'&&Number.isFinite(v)&&v>=a&&v<=b?v:null;
function relative(values,scale){
 const numbers=values.filter(v=>v!==null);
 if(numbers.length<2)return values.map(()=>null);
 const mean=numbers.reduce((a,b)=>a+b,0)/numbers.length;
 return values.map(v=>v===null?null:clamp((v-mean)/scale,-1,1));
}
function run(input,controlBets){
 const model=root.BoatTacticalModel,base=root.BoatFourFactor;
 if(!model||!base)throw Error('Pre-cutoff model dependencies unavailable');
 if(!input||!Array.isArray(input.racers)||input.racers.length!==6||
    !Array.isArray(controlBets)||controlBets.length<4||controlBets.length>20||
    !Number.isFinite(Date.parse(input.frozen_at_utc)))throw Error('Invalid frozen shadow input');
 const pre={
  venue:input.venue,phase:input.phase,frozen_at_utc:input.frozen_at_utc,
  venue_profile:input.venue_profile||null,weather_used:input.weather_used||null,
  racers:input.racers.map(r=>({
   lane:r.lane,course:r.course,national_win_rate:r.national_win_rate,
   average_start_timing:r.average_start_timing,motor_top_2_percent:r.motor_top_2_percent,
   exhibition_st:r.exhibition_st,exhibition_time:r.exhibition_time,
   original_exhibition:r.original_exhibition,racer_context:r.racer_context
  }))
 };
 const racers=[...pre.racers].sort((a,b)=>a.lane-b.lane);
 if(racers.some((r,i)=>r.lane!==i+1)||
    new Set(racers.map(r=>r.course)).size!==6||
    racers.some(r=>!Number.isInteger(r.course)||r.course<1||r.course>6))
    throw Error('Six valid and unique real entry courses required');
 if(controlBets.some(b=>!/^([1-6]-){2}[1-6]$/.test(b.combination)||
    new Set(b.combination.split('-')).size!==3||
    !Number.isSafeInteger(b.virtual_yen)||b.virtual_yen<1000)||
    new Set(controlBets.map(b=>b.combination)).size!==controlBets.length||
    controlBets.reduce((sum,b)=>sum+b.virtual_yen,0)!==50000)
    throw Error('Invalid formal control bets');
 const factor=base.evaluate(pre).rows;
 const winners=relative(racers.map(r=>valid(r.national_win_rate,0,10)),2);
 const top3=relative(racers.map(r=>valid(r.racer_context?.values?.national_top3,0,100)),25);
 const order=relative(racers.map(r=>r.course===r.lane?
    valid(r.racer_context?.values?.frame_start_order,1,6):null),1.5);
 const roles=racers.map((r,i)=>{
  // Residual of within-race top-3 tendency relative to national win strength.
  // A standalone top-3 rate would double-reward all-round ability.
  const residual=winners[i]===null||top3[i]===null?0:
    clamp(top3[i]-winners[i],-1,1);
  const orderAdvantage=order[i]===null?0:-order[i];
  return {lane:r.lane,course:r.course,head_proxy:1,
   second_proxy:+clamp(1+.045*residual+.015*orderAdvantage,.94,1.06).toFixed(5),
   third_proxy:+clamp(1+.07*residual+.01*orderAdvantage,.92,1.08).toFixed(5),
   top3_residual_used:winners[i]!==null&&top3[i]!==null,
   frame_start_order_used:order[i]!==null,
   measured_second_finish_rate:false,measured_third_finish_rate:false};
 });
 const original=model.forecastFourFactorPointFree(pre);
 const all=original?.metadata?.four_factor?.ticket_policy?.candidates;
 if(!Array.isArray(all)||all.length!==120||
    new Set(all.map(c=>c.combination)).size!==120)throw Error('Missing 120 pre-cutoff candidates');
 const factorByLane=new Map(factor.map(x=>[x.lane,x.combined_multiplier]));
 const laneByCourse=new Map(racers.map(r=>[r.course,r.lane]));
 const avg=racers.map(r=>valid(r.average_start_timing,.01,.4));
 let followEligible=0,innerEligible=0;
 const ranked=all.map(c=>{
  if(!Number.isFinite(c.relative_score)||c.relative_score<0)throw Error('Invalid candidate');
  const [h,s,t]=c.combination.split('-').map(Number);
  const head=racers[h-1],second=racers[s-1],third=racers[t-1];
  let follow=1,inner=1;
  // Adjacent following is *conditional* on real entry and credible relative ST.
  if(head.course>=3&&second.course===head.course+1&&
     factorByLane.get(s)>=.90*factorByLane.get(h)&&
     avg[s-1]!==null&&avg[h-1]!==null&&avg[s-1]<=avg[h-1]+.025){
       follow=1.035;followEligible++;
  }
  // Inside survival is not automatic after an outside attack.
  const survivor=(lane)=>laneByCourse.get(1)===lane&&
      factorByLane.get(lane)>=.90*factorByLane.get(h)&&
      avg[lane-1]!==null&&avg[h-1]!==null&&avg[lane-1]<=avg[h-1]+.030;
  if(head.course>=3&&(survivor(s)||survivor(t))){
    inner=1.03;innerEligible++;
  }
  const multiplier=clamp(roles[s-1].second_proxy*roles[t-1].third_proxy*follow*inner,.82,1.22);
  return {combination:c.combination,base_score:c.relative_score,
     shadow_score:c.relative_score*multiplier};
 });
 ranked.sort((a,b)=>b.shadow_score-a.shadow_score||a.combination.localeCompare(b.combination));
 const amounts=controlBets.map(b=>b.virtual_yen).sort((a,b)=>b-a);
 const bets=ranked.slice(0,amounts.length).map((c,i)=>({
   combination:c.combination,virtual_yen:amounts[i]
 }));
 if(bets.reduce((sum,b)=>sum+b.virtual_yen,0)!==50000)throw Error('Shadow budget mismatch');
 return {version:'racer-role-suitability-shadow-v0.1',status:'ready',
  model_role:'shadow_validation',generated_pre_cutoff:true,result_data_used:false,
  odds_used:false,calibrated:false,no_additional_stake:true,
  frozen_at_utc:input.frozen_at_utc,control_model:'same_snapshot_main',
  control_point_count:controlBets.length,selected_count:bets.length,
  selected_with_original_stake_distribution:true,
  method:'Same-input 120 scenario rerank; top3-vs-win residual, frame start order, evidence-gated following/inside survival. Head score preserved.',
  limitations:'No racer-specific 1st/2nd/3rd finish rates, attack success rates or movement video are measured. No learned coefficients.',
  evidence:{top3_residual_boats:roles.filter(r=>r.top3_residual_used).length,
    frame_order_boats:roles.filter(r=>r.frame_start_order_used).length,
    eligible_follow_scenarios:followEligible,eligible_inside_survival_scenarios:innerEligible},
  roles,bets};
}
root.BoatRoleSkillShadow={run};
if(typeof module!=='undefined')module.exports=root.BoatRoleSkillShadow;
})(typeof window==='undefined'?globalThis:window);
