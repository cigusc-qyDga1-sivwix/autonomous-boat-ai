/* BOAT LAB athlete & race-scoped expectation research indices v1.
 * Only pre-race frozen racer data and the already available tactical model.
 * No results, payouts, odds, or scraped private data. Does not change picks.
 */
(function(global){
'use strict';
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const number=x=>x!==null&&x!==undefined&&x!==''&&Number.isFinite(Number(x))?Number(x):null;
const fixed=x=>Math.round(clamp(x,0,100));
const BASE_COURSE=[76,68,66,65,62,60]; // transparent hypotheses, NOT win-rate odds
const WEIGHTS={racer:.45,motor:.30,course_fit:.25};
function validCourse(x){
 const c=number(x);
 return c!==null&&Number.isInteger(c)&&c>=1&&c<=6;
}
function blocked(r){
 return !!(r?.entry_exhibition_gate?.entry_watch&&!r.entry_exhibition_gate?.final_eligible);
}
function forecastForRace(r){
 if(blocked(r))return null;
 const api=global.BoatTacticalModel;
 if(!api)return null;
 // The canonical main v0.7/v0.9 is shadow-read only when
 // the saved snapshot really has a uniquely verified 6-course formation.
 const eligible=r?.model_role==='main'&&r?.entry_exhibition_gate?.final_eligible===true&&
  Array.isArray(r.racers)&&new Set(r.racers.map(x=>number(x.course))).size===6&&
  r.racers.every(x=>validCourse(x.course));
 try{
  const forecast=eligible?(r.model_version?.includes('v0.9')?api.forecastWakeIntegrated?.(r):api.forecastOutsideStart?.(r)):api.forecastRoleAware?.(r);
  return forecast||api.forecast?.(r)||null;
 }catch{
  if(eligible){try{return api.forecastRoleAware?.(r)||null}catch{}}
  return null;
 }
}
function rate(r,opts={}){
 const racers=Array.isArray(r?.racers)?[...r.racers].sort((a,b)=>number(a.lane)-number(b.lane)):[];
 if(racers.length!==6||racers.some((x,i)=>number(x.lane)!==i+1)){
  return {status:'unknown',message:'6艇の出走データが揃っていません',byLane:{},rows:[]};
 }
 const courses=racers.map(x=>number(x.course));
 // Six distinct numbers alone do not prove that the pre-race exhibition
 // entry formation was confirmed: baseline snapshots often record lane=course.
 const entryVerified=r?.entry_exhibition_gate?.final_eligible===true||
   (r?.entry_exhibition_gate==null&&r?.phase==='exhibition');
 const confirmed=!!entryVerified&&courses.every(validCourse)&&new Set(courses).size===6;
 const courseOrder=confirmed?courses:[1,2,3,4,5,6];
 const byCourse=Array.from({length:6},(_,i)=>racers[courseOrder.indexOf(i+1)]);
 const avgST=x=>{const n=number(x.average_start_timing);return n!==null&&n>=.01&&n<=.4?n:null;};
 const expo=x=>{const n=number(x.exhibition_time);return n!==null&&n>=5&&n<=10?n:null;};
 const turn=x=>{const n=number(x.original_exhibition?.turn_time);return n!==null&&n>=4&&n<=15?n:null;};
 const stValues=racers.map(avgST),expoValues=racers.map(expo),turnValues=racers.map(turn);
 const allExpo=expoValues.every(x=>x!==null);
 const allTurn=turnValues.every(x=>x!==null);
 const expoMean=allExpo?expoValues.reduce((a,b)=>a+b,0)/6:null;
 const turnMean=allTurn?turnValues.reduce((a,b)=>a+b,0)/6:null;
 const result={status:blocked(r)?'hold':'ready',model:null,provisional:!confirmed,weights:{...WEIGHTS},
  byLane:{},rows:[],explanation:'全国勝率、モーター2連対率、実進入コースと平均ST・取得済み展示タイムの相対差から作る未校正指数'};
 const snapshot=blocked(r)?null:(opts.forecast===undefined?forecastForRace(r):opts.forecast);
 const shares=snapshot?.role_coverage;
 const heads=snapshot?.head_course_shares;
 const validShares=Array.isArray(heads)&&heads.length===6&&shares&&
  racers.every(x=>{
   const l=x.lane,a=shares[l];
   return a&&['first','second','third'].every(k=>Number.isFinite(number(a[k]))&&number(a[k])>=0&&number(a[k])<=1);
  })&&['first','second','third'].every(k=>Math.abs(racers.reduce((sum,x)=>sum+number(shares[x.lane][k]),0)-1)<.025);
 const raws={};
 if(validShares){
  result.model=snapshot.model||'tactical-research-unknown';
  for(const x of racers){
   const z=shares[x.lane];
   raws[x.lane]=.55*number(z.first)+.30*number(z.second)+.15*number(z.third);
  }
 }
 const best=validShares?Math.max(...Object.values(raws)):null;
 for(const x of racers){
  const lane=x.lane,course=courseOrder[lane-1];
  const win=number(x.national_win_rate),motor=number(x.motor_top_2_percent);
  const st=avgST(x),e=expo(x),t=turn(x);
  const sources={racer:win!==null&&win>=0&&win<=10,motor:motor!==null&&motor>=0&&motor<=100,
    average_st:st!==null,course:confirmed,exhibition_time:allExpo,turn_time:allTurn};
  // Individual base athlete strength includes legal average-start timing when
  // present. Missing ST uses neutral adjustment, never a fabricated observation.
  const racerScore=sources.racer?fixed(50+11.5*(win-5.5)+(st===null?0:95*(.17-st))):null;
  const motorScore=sources.motor?fixed(50+1.15*(motor-35)):null;
  const previous=course>1?byCourse[course-2]:null;
  const innerST=previous?avgST(previous):null;
  const ownStartEdge=st!==null&&innerST!==null?clamp(350*(innerST-st),-18,18):0;
  const expoEdge=allExpo?clamp(95*(expoMean-e),-6,6):0;
  const turnEdge=allTurn?clamp(28*(turnMean-t),-6,6):0;
  // This is tactical fit, not historical racer-by-course win rate. Outside
  // courses may score highly if start/turn evidence supports making the move.
  const fitScore=confirmed?fixed(BASE_COURSE[course-1]+ownStartEdge+expoEdge+turnEdge):null;
  const composite=racerScore!==null&&motorScore!==null&&fitScore!==null?
   fixed(WEIGHTS.racer*racerScore+WEIGHTS.motor*motorScore+WEIGHTS.course_fit*fitScore):null;
  const role=validShares?shares[lane]:null;
  const expected=!blocked(r)&&best!==null&&best>0?fixed(100*raws[lane]/best):null;
  const record={lane,course,course_confirmed:confirmed,name:String(x.name||'未取得'),
   athlete:racerScore,motor:motorScore,course_fit:fitScore,ability:composite,
   race_expectation:expected,role_weights:role?{
    first:+number(role.first).toFixed(4),
    second:+number(role.second).toFixed(4),
    third:+number(role.third).toFixed(4)}:null,
   available:sources,confidence:sources.racer&&sources.motor&&confirmed?
    st!==null&&allExpo?'reference_with_exhibition':'partial_reference':'insufficient',
   start_edge_points:+ownStartEdge.toFixed(1),
   exhibition_edge_points:+expoEdge.toFixed(1),
   turn_edge_points:+turnEdge.toFixed(1)};
  result.rows.push(record);
  result.byLane[lane]=record;
 }
 return result;
}
global.BoatRacerRating={rate,forecastForRace,BASE_COURSE,WEIGHTS,version:'athlete-motor-course-race-index-v1-untrained'};
})(typeof window!=='undefined'?window:globalThis);
