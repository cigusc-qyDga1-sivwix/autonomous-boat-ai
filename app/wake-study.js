/* BOAT LAB wake-contact research v0.8 (UNTRAINED).
 * Qualitative, conditional flags for every scenario. The pre-race snapshot
 * cannot locate physical wakes or quantify hull speed. This module is a
 * visualization-only counterfactual and never changes frozen picks or odds.
 */
(function(global){
'use strict';
const num=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v):null;
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
function courseOf(r,lane){
 const boat=(r?.racers||[]).find(x=>Number(x.lane)===lane);
 const course=num(boat?.course);
 return Number.isInteger(course)&&course>=1&&course<=6?course:lane;
}
function analysis(combo,r){
 const parts=typeof combo==='string'?combo.split('-').map(Number):[];
 if(parts.length!==3||parts.some(x=>!Number.isInteger(x)||x<1||x>6)||
    new Set(parts).size!==3)
  return {status:'unknown',exposures:[],affected_lanes:[],explanation:'レース展開を識別できません'};
 const all=(r?.racers||[]),headLane=parts[0],headCourse=courseOf(r,headLane);
 const winner=all.find(x=>Number(x.lane)===headLane);
 const validEntry=all.length===6&&all.every(x=>courseOf(r,Number(x.lane))>=1);
 const means=all.map(x=>num(x.average_start_timing)).filter(x=>x!==null&&x>=.01&&x<=.4);
 const firstRacerST=means.length===6?means.reduce((a,b)=>a+b,0)/6:null;
 const candidates=[];
 // 1M: center/outer attack can cross the path of INNER opponents, but not
 // every inner course is automatically hit. Surviving top-three boats are
 // kept as low-risk alternatives, NOT deleted from the simulated finishing.
 if(headCourse>=3){
  for(const b of all){
   const lane=Number(b.lane),course=courseOf(r,lane);
   if(!Number.isInteger(lane)||lane<1||lane>6||course>=headCourse)continue;
   const survives=parts.includes(lane);
   const st=num(b.average_start_timing);
   const turn=num(b.original_exhibition?.turn_time);
   const top=all.map(x=>num(x.original_exhibition?.turn_time));
   const complete=top.every(x=>x!==null&&x>=4&&x<=15);
   const turnMean=complete?top.reduce((a,b)=>a+b,0)/6:null;
   const escapeSkill=turn!==null&&turnMean!==null?clamp((turnMean-turn)*.55,-.12,.12):0;
   // Heuristic exposure bands, not actual contact odds or speed loss.
   const baseline=.25+.075*Math.min(3,headCourse-course)+
    (survives?-.23:.12)-escapeSkill;
   const risk=clamp(baseline,.12,.82);
   candidates.push({lane,course,source_lane:headLane,phase:'1M',
    mechanism:'攻め艇が内側を通過するときの引き波・差し場の乱れ',
    risk:+risk.toFixed(3),severity:risk>=.53?'high':risk>=.34?'medium':'low',
    evidence:'展開仮説（実際の引き波通過は未確認）',
    note:survives?'上位残存の可能性も維持':'内側艇の失速候補、着外確定ではない'});
  }
 }
 // 2M and beyond: even an inside winner produces a wake in the path of a
 // pursuing 2nd/3rd craft. A following boat may avoid the rough water;
 // reduce the qualitative risk for strong turning/straight data.
 for(const [j,lane] of parts.slice(1).entries()){
  const b=all.find(x=>Number(x.lane)===lane);
  const currentCourse=courseOf(r,lane);
  const st=num(b?.average_start_timing);
  const fastST=st!==null&&firstRacerST!==null&&st<firstRacerST-.015;
  const readyTurn=num(b?.original_exhibition?.turn_time);
  const sourceCourse=courseOf(r,parts[j]);
  const frontCourse=courseOf(r,headLane);
  const parallel=sourceCourse!==currentCourse&&Math.abs(sourceCourse-currentCourse)>=2;
  const risk=clamp((j===0?.30:.39)-(fastST?.06:0)-
    (readyTurn!==null&&readyTurn<=5.65?.07:0)-(parallel?.05:0),.10,.55);
  candidates.push({lane,course:currentCourse,source_lane:parts[j],
   phase:'2M+',mechanism:'先行艇への追走時に引き波を横切る可能性',
   risk:+risk.toFixed(3),severity:risk>=.53?'high':risk>=.34?'medium':'low',
   evidence:'2M以降の後続艇リスク（航跡・艇間距離は未観測）',
   note:'追走や差し直しで回避できる場合もある'});
 }
 const sorted=candidates.sort((a,b)=>b.risk-a.risk||a.lane-b.lane);
 // Avoid duplicate labels at same moment: preserve 1M and 2M+ differences.
 return {
  status:validEntry?'hypothesis':'partial',head_lane:headLane,head_course:headCourse,
  exposures:sorted,affected_lanes:[...new Set(sorted.filter(x=>x.risk>=.34).map(x=>x.lane))].sort((a,b)=>a-b),
  studied_phases:['1M','2M+'],
  evidence_quality:'unmeasured_schematic_only',
  calibrated:false,
  explanation:'全艇の引き波影響を展開別に検討。接触・減速・着順の実測ではなく、無条件に全艇を失速させない。'
 };
}
global.BoatWakeStudy={analysis,courseOf,version:'wake-qualitative-v0.8-untrained'};
})(typeof window!=='undefined'?window:globalThis);
