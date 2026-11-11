/* BOAT LAB: first-mark defensive block and third-boat openings.
 * Pre-race, UNCALIBRATED scenario research. No actual positions, results,
 * payouts, odds or post-cutoff fields. No mid-race recovery inference.
 * The model never treats a possible block as an observed event.
 */
(function(root){
'use strict';
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const num=(v,f)=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v):f;
function score(input){
 if(!input||!Array.isArray(input.racers)||input.racers.length!==6)
  throw Error('Six pre-race racers required');
 const rs=[...input.racers].sort((a,b)=>Number(a.lane)-Number(b.lane));
 if(rs.some((r,i)=>Number(r.lane)!==i+1))throw Error('Invalid lane identity');
 const cs=rs.map(r=>num(r.course,r.lane));
 if(new Set(cs).size!==6||cs.some(c=>!Number.isInteger(c)||c<1||c>6))
  throw Error('Confirmed six-boat entry required');
 const byCourse=Array.from({length:6},(_,i)=>rs[cs.indexOf(i+1)]);
 const strength=r=>{
  const ex=r.original_exhibition||{};
  const st=num(r.average_start_timing,.17);
  const est=num(r.exhibition_st,null);
  const validEx=est!==null&&est>=0&&est<=.45;
  const start=clamp(1+2.2*(.17-st)+(validEx?.55*(.17-est):0),.65,1.4);
  const turn=clamp(1+.12*(5.9-num(ex.turn_time,5.9))+
    .035*(37-num(ex.lap_time,37)),.75,1.25);
  const motor=clamp(1+.009*(num(r.motor_top_2_percent,30)-30),.75,1.55);
  const skill=clamp(1+.07*(num(r.national_win_rate,5)-5),.72,1.35);
  return {start,turn,motor,skill,overall:start*turn*motor*skill};
 };
 const m=byCourse.map(strength),inside=m[0],attacker=m[2],two=m[1];
 // 3-course attack and 1-course resistance can BOTH be plausible.
 const pressure=clamp(.45+.9*(attacker.start/inside.start-1)+
   .38*(attacker.turn/inside.turn-1),0,1);
 const defense=clamp(.48+.65*(inside.start/attacker.start-1)+
   .4*(inside.turn/attacker.turn-1)+.10*(inside.skill-1),0,1);
 const contest=clamp(pressure*defense*2.1,0,1);
 const insideSashi=clamp(.45+.30*(two.turn-1)+.24*(two.start-1),.2,.85);
 const paths=[];
 // Course 2 can pass inside after 1 defends against 3.
 paths.push({kind:'block-inside-sashi',winner_lane:byCourse[1].lane,
  blocked_attacker_lane:byCourse[2].lane,defender_lane:byCourse[0].lane,
  relative_evidence:+(contest*insideSashi).toFixed(4),
  rationale:'3-course attack meets 1-course defense; 2-course inside sashi opening'});
 // A later outside follower can enter a makuri-sashi opening. Never grant
 // automatic advantage to 5: demand start/turn/motor evidence and course access.
 for(let c=4;c<=6;c++){
  const x=m[c-1],lead=m[c-2];
  const access=clamp(.46+.36*(x.start/lead.start-1)+
   .22*(x.turn/lead.turn-1),0,1);
  const quality=clamp(.40+.24*(x.motor-1)+.20*(x.skill-1)+
   .22*(x.turn-1),0,1);
  paths.push({kind:'block-outside-makurisashi',winner_lane:byCourse[c-1].lane,
   blocked_attacker_lane:byCourse[2].lane,defender_lane:byCourse[0].lane,
   relative_evidence:+(contest*access*quality).toFixed(4),
   rationale:'3-course attack meets 1-course defense; outside follower seeks makuri-sashi'});
 }
 // Contest between two boats for a lower place may free a route for a
 // third. This is a 3rd-place candidate hypothesis, NOT observed collision.
 for(let a=3;a<=6;a++)for(let b=a+1;b<=6;b++){
  const rivalry=clamp(.45-.4*Math.abs(m[a-1].overall-m[b-1].overall),0,1);
  for(let c=2;c<=6;c++){
   if(c===a||c===b)continue;
   const x=m[c-1];
   const clean=clamp(.4+.22*(x.turn-1)+.2*(x.start-1),0,1);
   const evidence=contest*.4*rivalry*clean;
   if(evidence<.025)continue;
   paths.push({kind:'third-boat-through-rivalry',winner_lane:null,
    third_lane:byCourse[c-1].lane,contesting_lanes:[byCourse[a-1].lane,byCourse[b-1].lane],
    relative_evidence:+evidence.toFixed(4),
    rationale:'Two boats contest a lower position; third boat may take a clean line'});
  }
 }
 return {model:'first-mark-block-third-boat-v0.1-untrained',pre_cutoff_only:true,
  no_midrace_recovery_model:true,contest_evidence:+contest.toFixed(4),
  paths:paths.sort((a,b)=>b.relative_evidence-a.relative_evidence),
  caveat:'Scenario weights are uncalibrated relative evidence, not probabilities'};
}
const api={score};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.BoatFirstMarkBlock=api;
})(typeof globalThis!=='undefined'?globalThis:this);
