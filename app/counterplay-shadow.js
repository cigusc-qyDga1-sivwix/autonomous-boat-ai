/* Opponent-response hypotheses. No inferred intent, measured trajectories or
 * calibrated probabilities. An independent opt-in shadow, never formal picks. */
(function(root){
'use strict';
const numeric=(x,a,b)=>typeof x==='number'&&Number.isFinite(x)&&x>=a&&x<=b?x:null;
const clamp=(x,a,b)=>Math.min(b,Math.max(a,x));
function run(input,controlBets){
 const frozen=Date.parse(input?.frozen_at_utc),cutoff=Date.parse(input?.cutoff_iso_jst);
 if(!Number.isFinite(frozen)||!Number.isFinite(cutoff)||frozen>=cutoff)
  throw Error('Explicit pre-cutoff freeze required');
 if(input.phase!=='exhibition')throw Error('Exhibition input required');
 const racers=input.racers?.map(r=>({lane:r.lane,course:r.course,
  national_win_rate:r.national_win_rate,motor_top_2_percent:r.motor_top_2_percent,
  average_start_timing:r.average_start_timing,exhibition_st:r.exhibition_st,
  exhibition_time:r.exhibition_time,original_exhibition:r.original_exhibition,
  racer_context:r.racer_context})).sort((a,b)=>a.lane-b.lane);
 if(!racers||racers.length!==6||racers.some((r,i)=>r.lane!==i+1)||
   new Set(racers.map(r=>r.course)).size!==6||racers.some(r=>!Number.isInteger(r.course)||r.course<1||r.course>6))
  throw Error('Six explicit unique entry courses required');
 if(!Array.isArray(controlBets)||controlBets.length<4||controlBets.length>20||
   new Set(controlBets.map(b=>b.combination)).size!==controlBets.length||
   controlBets.some(b=>!/^([1-6]-){2}[1-6]$/.test(b.combination)||new Set(b.combination.split('-')).size!==3||
    !Number.isSafeInteger(b.virtual_yen)||b.virtual_yen<1000||b.virtual_yen%1000!==0)||
   controlBets.reduce((s,b)=>s+b.virtual_yen,0)!==50000)throw Error('Invalid control bets');
 const pre={venue:input.venue,phase:input.phase,frozen_at_utc:input.frozen_at_utc,
  venue_profile:input.venue_profile||null,weather_used:input.weather_used||null,racers};
 const factors=root.BoatFourFactor.evaluate(pre).rows;
 const all=root.BoatTacticalModel.forecastFourFactorPointFree(pre)?.metadata?.four_factor?.ticket_policy?.candidates;
 if(!Array.isArray(all)||all.length!==120||new Set(all.map(c=>c.combination)).size!==120||
    all.some(c=>!Number.isFinite(c.relative_score)||c.relative_score<0))throw Error('120 valid candidates required');
 const byCourse=[...racers].sort((a,b)=>a.course-b.course);
 const avg=r=>numeric(r.average_start_timing,.01,.4);
 const st=r=>{const a=avg(r),e=numeric(r.exhibition_st,0,.45);return a===null?null:e===null?a:.8*a+.2*e;};
 const metric=(r,key,lo,hi)=>numeric(r.original_exhibition?.[key],lo,hi);
 const expoComplete=racers.every(r=>numeric(r.exhibition_time,5,10)!==null);
 const strength=r=>factors[r.lane-1].combined_multiplier;
 const duels=[];
 for(const attacker of byCourse.slice(1)){
  const defender=byCourse[attacker.course-2],ast=st(attacker),dst=st(defender);
  const fields=[['national_win_rate',0,10],['motor_top_2_percent',0,100]];
  const missing=fields.filter(([k,a,b])=>numeric(attacker[k],a,b)===null||numeric(defender[k],a,b)===null).map(([k])=>k);
  if(ast===null||dst===null)missing.push('average_start_timing');
  if(!expoComplete)missing.push('six_boat_exhibition_time');
  const relative=strength(attacker)/strength(defender);
  const lead=expoComplete?defender.exhibition_time-attacker.exhibition_time:null;
  const gap=ast===null||dst===null?null:dst-ast;
  // Attention is NOT an input. These nominate an attack hypothesis only.
  const nominated=!missing.length&&(relative>=1.03||lead>=.03||gap>=.015);
  const attackTurn=metric(attacker,'turn_time',4,15),defendTurn=metric(defender,'turn_time',4,15);
  const turnsMeasured=attackTurn!==null&&defendTurn!==null;
  // A defender not clearly late, with comparable skill, can resist. Missing
  // turn data never gets filled by the same composite strength a second time.
  const resistance=nominated&&dst<=ast+.015&&
    defender.national_win_rate>=.90*attacker.national_win_rate&&
    (!turnsMeasured||defendTurn<=attackTurn+.20);
  const alternatives=resistance?racers.filter(r=>r.lane!==attacker.lane&&r.lane!==defender.lane&&
    st(r)!==null&&numeric(r.national_win_rate,0,10)!==null&&numeric(r.motor_top_2_percent,0,100)!==null&&
    strength(r)>=.90*Math.max(strength(attacker),strength(defender))&&
    st(r)<=Math.max(ast,dst)+.02).map(r=>({lane:r.lane,course:r.course})):[];
  const branch=(kind,predicate)=>({kind,conditional_hypothesis:true,
    alternatives:all.filter(c=>predicate(c.combination.split('-').map(Number)))
     .sort((a,b)=>b.relative_score-a.relative_score||a.combination.localeCompare(b.combination))
     .slice(0,3).map(c=>({combination:c.combination,base_relative_score:c.relative_score,
       in_control:controlBets.some(b=>b.combination===c.combination)}))});
  const branches=nominated?[
   branch('attack_succeeds',([h])=>h===attacker.lane),
   branch('inside_holds',([h,s,t])=>h===defender.lane&&[s,t].includes(attacker.lane)),
   branch('attack_fails_to_place',([h,s,t])=>h===defender.lane&&![s,t].includes(attacker.lane)),
   ...(resistance&&alternatives.length?[branch('contested_third_party',([h])=>alternatives.some(r=>r.lane===h))]:[])
  ]:[];
  duels.push({attacker_lane:attacker.lane,attacker_course:attacker.course,
    defender_lane:defender.lane,defender_course:defender.course,nominated,
    resistance_plausible:resistance,missing_fields:missing,estimated_st_gap_sec:gap,
    exhibition_lead_sec:lead,composite_strength_ratio:relative,
    turn_comparison:turnsMeasured?'original_exhibition_pair':'unavailable',
    exhibition_f_ignored:[attacker,defender].filter(r=>typeof r.exhibition_st==='number'&&r.exhibition_st<0).map(r=>r.lane),
    opportunity_candidates:alternatives,branches});
 }
 const active=duels.filter(d=>d.resistance_plausible);
 const ranked=all.map(c=>{
  const [h,s,t]=c.combination.split('-').map(Number);let multiplier=1;const reasons=[];
  for(const d of active){
   if(h===d.attacker_lane){multiplier*=.94;reasons.push({attacker:d.attacker_lane,defender:d.defender_lane,kind:'resisted_attack'});}
   else if(h===d.defender_lane){multiplier*=1.04;reasons.push({attacker:d.attacker_lane,defender:d.defender_lane,
     kind:[s,t].includes(d.attacker_lane)?'inside_holds':'attack_fails_to_place'});}
   else if(d.opportunity_candidates.some(r=>r.lane===h)){
    multiplier*=1.04;reasons.push({attacker:d.attacker_lane,defender:d.defender_lane,kind:'contested_third_party'});
   }
  }
  multiplier=clamp(multiplier,.85,1.08);
  return {combination:c.combination,base_relative_score:c.relative_score,multiplier,
   shadow_relative_score:c.relative_score*multiplier,reasons};
 }).sort((a,b)=>b.shadow_relative_score-a.shadow_relative_score||a.combination.localeCompare(b.combination));
 // With no resistance evidence, keep control exactly; do not attribute a
 // generic 120-combination rerank to an opponent response effect.
 const stakes=controlBets.map(b=>b.virtual_yen).sort((a,b)=>b-a);
 const selectorControl=[...all].sort((a,b)=>b.relative_score-a.relative_score||a.combination.localeCompare(b.combination))
  .slice(0,stakes.length).map((c,i)=>({combination:c.combination,virtual_yen:stakes[i]}));
 const bets=active.length?ranked.slice(0,stakes.length).map((c,i)=>({combination:c.combination,virtual_yen:stakes[i]})):
   controlBets.map(b=>({combination:b.combination,virtual_yen:b.virtual_yen}));
 for(const d of duels)for(const b of d.branches)for(const a of b.alternatives)
  a.in_shadow=bets.some(b=>b.combination===a.combination);
 return {version:'counterplay-shadow-v0.1',status:'ready',model_role:'shadow_validation',not_formal:true,
  frozen_at_utc:input.frozen_at_utc,cutoff_iso_jst:input.cutoff_iso_jst,generated_pre_cutoff:true,
  result_data_used:false,odds_used:false,calibrated:false,no_additional_stake:true,
  psychological_intent_inferred:false,measured_trajectories:false,
  point_count_equal:true,stake_distribution_preserved:true,head_set_may_change:true,
  coefficients:{resisted_attack:.94,inside_hold:1.04,third_party:1.04,bounds:[.85,1.08],untrained:true},
  limitations:'Opponent response and attack failure are hypotheses, not measured intent, interference or calibrated branch probabilities. Composite strength is not measured speed or turn ability. No blind strong-boat penalty.',
  active_duels:active.length,duels,candidates:ranked,
  same_selector_control_bets:active.length?selectorControl:controlBets.map(b=>({combination:b.combination,virtual_yen:b.virtual_yen})),bets};
}
root.BoatCounterplayShadow={run};
if(typeof module!=='undefined')module.exports=root.BoatCounterplayShadow;
})(typeof window==='undefined'?globalThis:window);
