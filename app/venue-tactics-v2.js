/* BOAT LAB venue scenario prior v1.4 -- prospective UNTRAINED TEST only.
 * Historical winner-method shares per venue are shares OF ALL VENUE WINS,
 * not P(method | course, racer, weather). Do not infer actual trajectories.
 * Aggregates: https://kachitei-lab.com/article/v_venue_decision
 * Page describes 2016-2025, and elsewhere May 2026; exact cohort ambiguous.
 * Qualitative 24-venue reference: https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_01_07_01.html
 * Current athlete and start-gap evidence required. Never consume results,
 * payout, odds, actual race ST or video observations in forward inference.
 */
(function(root){
'use strict';
// Venue-order matches BOATRACE official stadium codes. 03 江戸川 explicitly excluded.
// escape / makuri / sashi / makurizashi percentages across ALL races at that venue.
// Numbers are historical, not a race's expected winner/finish probability.
const HISTORY=Object.freeze({
 '桐生':[49.7,18.0,12.0,13.4],
 '戸田':[40.7,25.6,13.4,11.8],
 '江戸川':[42.7,19.3,15.6,10.3],
 '平和島':[42.3,18.0,18.3,12.6],
 '多摩川':[50.5,16.9,13.4,12.0],
 '浜名湖':[49.9,14.0,13.3,14.8],
 '蒲郡':[53.7,16.7,9.8,13.3],
 '常滑':[55.1,15.7,10.5,12.1],
 '津':[54.9,11.7,14.1,11.7],
 '三国':[51.0,13.7,16.0,11.3],
 'びわこ':[51.5,14.5,14.0,12.6],
 '住之江':[56.8,14.4,12.3,9.7],
 '尼崎':[57.4,13.6,11.3,11.4],
 '鳴門':[46.0,17.3,15.1,12.8],
 '丸亀':[53.9,12.8,14.4,12.0],
 '児島':[53.9,12.5,13.6,12.7],
 '宮島':[54.6,15.9,11.1,11.3],
 '徳山':[60.5,10.9,12.8,8.4],
 '下関':[57.8,13.0,11.5,10.5],
 '若松':[54.3,14.4,12.4,10.1],
 '芦屋':[58.5,13.1,9.8,11.0],
 '福岡':[52.1,18.5,12.7,7.8],
 '唐津':[51.9,14.3,13.8,11.9],
 '大村':[60.5,11.2,10.8,10.3]
});
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
const BASE={makuri:15.0,sashi:13.0,makurizashi:12.0};
const SOURCE='https://kachitei-lab.com/article/v_venue_decision';
function evaluate(input){
 const venue=input?.venue,profile=input?.venue_profile;
 const row=HISTORY[venue],excluded=venue==='江戸川';
 const profileValid=!!row&&!!profile&&profile.name===venue&&
   typeof profile.tactical_focus==='string'&&!!profile.tactical_focus&&
   profile.code!=='03';
 const eligible=!!row&&profileValid&&!excluded;
 const active=eligible&&!input?.venue_tactics_disabled;
 const byCourse=input.byCourse||[];
 const move=input.move||[];
 const signals=input.startSignals||[];
 const methods=row?{escape:row[0],makuri:row[1],sashi:row[2],makurizashi:row[3]}:null;
 const ratios=methods?{
   makuri:clamp((methods.makuri-BASE.makuri)/10,-1,1),
   sashi:clamp((methods.sashi-BASE.sashi)/10,-1,1),
   makurizashi:clamp((methods.makurizashi-BASE.makurizashi)/10,-1,1)
 }:null;
 // These are *model scenario mixtures*, NOT measured method-by-course rates.
 const MIX={2:{sashi:1},3:{makuri:.6,makurizashi:.4},
   4:{makuri:.75,makurizashi:.25},
   5:{makuri:.30,makurizashi:.70},
   6:{makuri:.15,makurizashi:.85}};
 const head_course_multipliers=[1,1,1,1,1,1];
 const attack=[];
 for(let course=2;course<=6;course++){
   const sig=signals[course-1],own=move[byCourse[course-1]],inside=move[byCourse[course-2]];
   const go=own&&inside?own.go/Math.max(.38,inside.go):null;
   const turn=own&&inside?own.turn/Math.max(.35,inside.turn):null;
   const st=sig?.nearest_gap_sec;
   const evidence=!!(active&&sig?.confidence>=.60&&st!==null&&
     Number.isFinite(st)&&st>=.012&&go>=.87&&turn>=.80);
   const raw=MIX[course];
   const method_diff=ratios?Object.keys(raw).reduce((sum,k)=>sum+raw[k]*ratios[k],0):0;
   const signal= evidence ? clamp((st-.012)/.06,.12,1)*clamp((go-.83)/.25,.16,1) : 0;
   const multiplier=evidence?clamp(1+.045*method_diff*signal,.955,1.045):1;
   head_course_multipliers[course-1]=+multiplier.toFixed(6);
   attack.push({course,evidence,method_scenario_mix:raw,
     historical_method_deviation:+method_diff.toFixed(4),st_gap_sec:st??null,
     relative_go:go===null?null:+go.toFixed(3),relative_turn:turn===null?null:+turn.toFixed(3),
     head_multiplier:head_course_multipliers[course-1]});
 }
 const byAttack=Object.fromEntries(attack.map(x=>[x.course,x]));
 function secondMultiplier(head,second){
   if(!active)return 1;
   const e=byAttack[head],leader=move[byCourse[head-1]];
   const chaser=move[byCourse[second-1]];
   const inside=move[byCourse[0]];
   if(!leader||!chaser||!inside)return 1;
   // Separately score following outside course versus surviving course 1.
   // Conditional labels are assumptions, not video-derived routes.
   if(head>=3&&e?.evidence&&second===head+1&&
      chaser.go>=.84*leader.go&&chaser.turn>=.80*leader.turn){
      return +(1+.032*(.5+.5*clamp(e.historical_method_deviation,-1,1))).toFixed(6);
   }
   if(head>=3&&e?.evidence&&second===1&&
      inside.go>=.63*leader.go&&inside.turn>=.70*leader.turn){
      return +(1+.024*clamp(methods.escape/53,.65,1.25)).toFixed(6);
   }
   // No universal "+2 boat for head 1" or fixed frame-neighbor rule.
   return 1;
 }
 function thirdMultiplier(head,second,third){
   if(!active)return 1;
   const e=byAttack[head],leader=move[byCourse[head-1]];
   const inside=move[byCourse[0]];
   if(head>=3&&e?.evidence&&third===1&&second===head+1&&
      leader&&inside&&inside.go>=.60*leader.go&&inside.turn>=.66*leader.turn)
      return +(1+.028*clamp(methods.escape/53,.65,1.25)).toFixed(6);
   // When course 1 has already finished 2nd, do not re-add it for 3rd.
   return 1;
 }
 return {
  version:'venue-tactics-v2-23venues-ex-edogawa',venue,excluded,eligible,
  applied:active&&attack.some(x=>x.head_multiplier!==1),
  role_scenarios_enabled:active,disabled:input?.venue_tactics_disabled===true,
  historical_winning_method_share_pct:methods,
  registered_tactical_focus:profileValid?profile.tactical_focus:null,
  source_url:SOURCE,
  source_cohort:'provider mixed 2016-2025/2026 header; unverified cohort; descriptive only',
  source_uncertainty:'No venue-specific 2nd/3rd conditional stats. All role modifiers are pre-race hypotheses, not calibrated probability.',
  pre_cutoff_only:true,result_data_used:false,
  head_course_multipliers,attack_evidence:attack,
  secondMultiplier,thirdMultiplier
 };
}
root.BoatVenueTacticsV2={evaluate,HISTORY,SOURCE};
})(typeof window==='undefined'?globalThis:window);
