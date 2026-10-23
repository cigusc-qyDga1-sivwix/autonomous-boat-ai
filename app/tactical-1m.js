/* BOAT LAB tactical first-mark candidate scenarios v0.1.
 * Separate, explicitly NON-FROZEN research calculation.
 * Only frozen pre-race fields; no outcomes, payouts, odds or real betting.
 * Not calibrated probabilities. The six-way branch is a structural hypothesis.
 */
(function(global){
'use strict';
const START_PRIORS=[.48,.18,.16,.105,.05,.025];
const RATE_BY_VENUE={
 '桐生':.515,'戸田':.429,'江戸川':.477,'平和島':.446,'多摩川':.535,
 '浜名湖':.525,'蒲郡':.565,'常滑':.583,'津':.564,'三国':.525,
 'びわこ':.534,'住之江':.582,'尼崎':.587,'鳴門':.475,'丸亀':.565,
 '児島':.560,'宮島':.555,'徳山':.632,'下関':.601,'若松':.581,
 '芦屋':.592,'福岡':.568,'唐津':.557,'大村':.620
};
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
const finite=(x,fallback)=>x!==''&&x!==null&&x!==undefined&&Number.isFinite(Number(x))?Number(x):fallback;
const assign=(r,course)=>{
 let x=r.find(z=>finite(z.course,z.lane)===course);
 return x||r[course-1]||null;
};
const nameTactic=['','先マイ・逃げ','差し','まくり差し','カドまくり','外からのまくり差し','外の展開連動'];
function forecast(input){
 const outsideTrial=input?.experimental_variant==='outside-makuri-v0.2';
 const runners=input?.racers;
 if(!Array.isArray(runners)||runners.length!==6)throw Error('6艇の保存済み出走情報が必要');
 const sorted=[...runners].sort((a,b)=>a.lane-b.lane);
 if(sorted.some((r,i)=>Number(r.lane)!==i+1))throw Error('艇番号1〜6が必要');
 const rawCourses=sorted.map(r=>finite(r.course,r.lane));
 const courses=[...new Set(rawCourses)].length===6&&rawCourses.every(x=>x>=1&&x<=6&&Number.isInteger(x))?
   rawCourses:sorted.map(r=>r.lane);
 const byCourse=Array.from({length:6},(_,i)=>courses.indexOf(i+1));
 const byLane=sorted;
 const v=sorted.map((r,i)=>{
   const win=clamp(finite(r.national_win_rate,4.5),1,10);
   const motor=clamp(finite(r.motor_top_2_percent,30),0,100);
   const st=finite(r.average_start_timing,.17);
   const avg=st>=.01&&st<=.4?st:.17;
   const exhibit=finite(r.exhibition_time,null),est=finite(r.exhibition_st,null);
   const lap=finite(r.original_exhibition?.lap_time,null);
   const turn=finite(r.original_exhibition?.turn_time,null);
   const straight=finite(r.original_exhibition?.straight_time,null);
   return {lane:i+1,course:courses[i],win,motor,avg,exhibit,est,lap,turn,straight};
 });
 const mean=(key)=>v.reduce((s,x)=>s+x[key],0)/6;
 const meanWin=mean('win'),meanMotor=mean('motor'),meanST=mean('avg');
 const validMetrics=['exhibit','lap','turn','straight'].filter(key=>v.every(x=>x[key]!=null));
 const metricMean=Object.fromEntries(validMetrics.map(k=>[k,mean(k)]));
 const move=v.map(x=>{
  let skill=Math.exp(clamp(.145*(x.win-meanWin),-.45,.45));
  let motor=Math.exp(clamp(.010*(x.motor-meanMotor),-.35,.35));
  let start=Math.exp(clamp(2.6*(meanST-x.avg),-.25,.25));
  // Actual pre-race exhibition F cannot be interpreted as super-fast start.
  if(x.est!==null&&x.est>=0&&x.est<=.5)start*=Math.exp(clamp(1.6*(.16-x.est),-.12,.12));
  let go=skill*motor*start;
  if(validMetrics.includes('exhibit'))go*=Math.exp(clamp(.48*(metricMean.exhibit-x.exhibit),-.22,.22));
  let turn=skill*Math.pow(motor,1.12);
  if(validMetrics.includes('turn'))turn*=Math.exp(clamp(.11*(metricMean.turn-x.turn),-.22,.22));
  if(validMetrics.includes('lap'))turn*=Math.exp(clamp(.065*(metricMean.lap-x.lap),-.16,.16));
  let straight=skill*Math.pow(motor,1.05);
  if(validMetrics.includes('straight'))straight*=Math.exp(clamp(.09*(metricMean.straight-x.straight),-.15,.15));
  return {go:clamp(go,.38,2.8),turn:clamp(turn,.35,2.8),
          straight:clamp(straight,.35,2.8),overall:clamp(skill*motor,.3,2.8)};
 });
 // V0.2 research only. Start pressure is relative to the neighboring actual
 // *course*, not the boat number. No result, odds or future data is consulted.
 const outsideAttacks=[4,5,6].map(course=>{
  const own=move[byCourse[course-1]];
  const inner=move[byCourse[course-2]];
  const one=move[byCourse[0]];
  const launch=own.go/Math.max(.38,.72*inner.go+.28*one.go);
  const steering=own.turn/Math.max(.38,inner.turn);
  // A fast 4th-course attack can open a lane for 5 and 6; it does not
  // automatically mean either following boat will win the race.
  const preceding=course===4?0:Math.max(0,move[byCourse[course-2]].go/
     move[byCourse[course-3]].go-1);
  const multiplier=clamp(1+.85*Math.max(0,launch-1)+.35*Math.max(0,steering-1)+
     .28*preceding-.65*Math.max(0,.95-launch),.72,1.65);
  return {course,launch,steering,preceding,multiplier};
 });
 const rate=finite(input.venue_profile?.course1_reference_rate,RATE_BY_VENUE[input.venue]??.55);
 const head1=clamp(rate,.38,.67);
 // Retain conservative venue dependence, but no hardcoded course-1 winner.
 let rateImpact=clamp(head1/.55,.7,1.3);
 const wind=finite(input.weather_used?.wind_speed,null);
 let hedge=wind!==null&&wind>=6?.82:wind!==null&&wind>=4?.9:1;
 let strength=START_PRIORS.map((prior,c)=>{
  const idx=byCourse[c],m=move[idx];
  const base=prior*(c===0?rateImpact:((1-rateImpact*.49)/.51));
  const skill= Math.pow(m.go,c===0?.85:1.55)*
    Math.pow(m.turn,c===0?.8:c===1?1.25:1.1)*
    Math.pow(m.straight,c>=2?1.05:.4);
  const penalty=c===0?hedge:(2-hedge)**.65;
  return Math.max(.0001,base*clamp(skill,.25,3.1)*penalty);
 });
 // If outside racer has demonstrably quicker legal exhibition ST and comparable
 // ability, reduce inside/2's assumed clean turn and shift to attack branches.
 const i1=move[byCourse[0]],i3=move[byCourse[2]];
 if(i3.go>i1.go*1.22&&i3.turn>i1.turn*.85){
  const shift=clamp((i3.go/i1.go-1.22)*.30,0,.12);
  strength[0]*=1-shift;strength[2]*=1+shift*1.8;
 }
 if(outsideTrial){
  for(const signal of outsideAttacks)strength[signal.course-1]*=signal.multiplier;
  // A plausible kadomakuri slightly lowers the odds of an unchallenged
  // inside turn; never erase the inner survivor scenario.
  strength[0]*=clamp(1-.13*Math.max(0,outsideAttacks[0].multiplier-1),.92,1);
 }
 const denom=strength.reduce((a,b)=>a+b,0),shares=strength.map(v=>v/denom);
 // Condition second and third on WHICH first-turn maneuver succeeded. If c=3
 // attacks, nearby c2 and inside c1 can survive; if c1 escapes, c2/c3 can chase.
 function secondWeight(headCourse,secondCourse){
  let relation;
  if(headCourse===1)relation=({2:1.45,3:1.3,4:1.02,5:.72,6:.43})[secondCourse]||.5;
  else if(headCourse===2)relation=({1:1.40,3:1.38,4:1.00,5:.64,6:.42})[secondCourse]||.5;
  else if(headCourse===3)relation=({1:1.25,2:1.5,4:1.03,5:.86,6:.52})[secondCourse]||.5;
  else relation=secondCourse===headCourse-1?1.48:secondCourse===1?1.33:
       secondCourse===2?1.22:secondCourse===headCourse+1?1.18:.76;
  const z=move[byCourse[secondCourse-1]];
  if(outsideTrial){
   // When an outer boat attacks, its next outer neighbor may follow through.
   if(headCourse>=4&&secondCourse===headCourse+1)relation*=1.32;
   if(headCourse>=4&&secondCourse>=4&&secondCourse!==headCourse+1)relation*=1.12;
   if(headCourse>=4&&secondCourse===1)
      relation*=clamp(.9+.18*(move[byCourse[0]].turn-1),.78,1.08);
   // Even if the inside survives, a strong outer turn can take second.
   if(headCourse===1&&secondCourse>=4)
      relation*=clamp(.95+.4*(z.turn-1)+.2*(z.go-1),.78,1.3);
  }
  return Math.max(.01,relation*Math.pow(z.turn,.85)*Math.pow(z.go,.3));
 }
 function thirdWeight(h,s,c){
  const x=move[byCourse[c-1]];
  let consistency=(c===1?1.27:c===2?1.25:c===3?1.12: c===4?1.03:c===5?.90:.76);
  if(h===3&&s===2&&c===1)consistency*=1.65; // possible 3-2-1 turn scenario
  if(h===3&&s===1&&c===2)consistency*=1.28;
  if(h===1&&s===2&&c===3)consistency*=1.2;
  if(h===2&&s===1&&c===3)consistency*=1.22;
  if(h>=4&&c===1)consistency*=1.22;
  if(outsideTrial){
   // Preserve the outside-following and inner-survival branches separately.
   if(h>=4&&c>=4&&c!==h)consistency*=1.24;
   if(h===1&&s>=4&&c===s+1)consistency*=1.26;
   if(h>=4&&s>=4&&c===1)consistency*=1.1;
  }
  return Math.max(.01,consistency*Math.pow(x.turn,.65)*Math.pow(x.overall,.3));
 }
 const candidates=[];
 for(let h=1;h<=6;h++){
  const heads=Array.from({length:6},(_,i)=>i+1).filter(c=>c!==h);
  const secondScores=new Map(heads.map(c=>[c,secondWeight(h,c)]));
  const secondTotal=[...secondScores.values()].reduce((a,b)=>a+b,0);
  for(const s of heads){
   const thirds=heads.filter(c=>c!==s);
   const thirdScores=new Map(thirds.map(c=>[c,thirdWeight(h,s,c)]));
   const thirdTotal=[...thirdScores.values()].reduce((a,b)=>a+b,0);
   for(const t of thirds) {
    const boats=[byCourse[h-1],byCourse[s-1],byCourse[t-1]].map(i=>v[i].lane);
    const combo=boats.join('-');
    const pseudo=shares[h-1]*(secondScores.get(s)/secondTotal)*(thirdScores.get(t)/thirdTotal);
    candidates.push({combination:combo,pseudo,headCourse:h,
      scenario:nameTactic[h],secondCourse:s,thirdCourse:t,headShare:shares[h-1]});
   }
  }
 }
 candidates.sort((a,b)=>b.pseudo-a.pseudo||a.combination.localeCompare(b.combination));
 const dominant=Math.max(...shares);
 const close=shares.filter(x=>x>=.12).length;
 const count=clamp(Math.round(6+5*close/4+4*(.58-dominant)),4,12);
 let picks=candidates.slice(0,count);
 // Provide 1M branches rather than silently dropping plausible runner-ups.
 for(let head=2;head<=6;head++){
  if(shares[head-1]<.12||picks.some(x=>x.headCourse===head))continue;
  const alternative=candidates.find(x=>x.headCourse===head);
  if(!alternative)continue;
  const replace=picks.findLastIndex(x=>x.headCourse===1);
  if(replace!==-1)picks[replace]=alternative;
 }
 if(outsideTrial){
  // Include an explainable outside-head branch only where attack strength is
  // supported by pre-race signals. No blanket 4/5/6 ticket quota.
  const strongOutside=outsideAttacks.filter(a=>a.multiplier>=1.14&&
     shares[a.course-1]>=.045).sort((a,b)=>shares[b.course-1]-shares[a.course-1]);
  for(const a of strongOutside.slice(0,2)){
   if(picks.some(p=>p.headCourse===a.course))continue;
   const candidate=candidates.find(p=>p.headCourse===a.course);
   const replace=picks.findLastIndex(p=>p.headCourse===1);
   if(candidate&&replace>=0)picks[replace]=candidate;
  }
 }
 picks.sort((a,b)=>b.pseudo-a.pseudo||a.combination.localeCompare(b.combination));
 const remaining=50-picks.length;
 const powered=picks.map(x=>Math.pow(x.pseudo,.8));
 const totalPower=powered.reduce((a,b)=>a+b,0);
 const target=powered.map(x=>remaining*x/totalPower);
 const floor=target.map(Math.floor);
 let unused=remaining-floor.reduce((a,b)=>a+b,0);
 const remainders=target.map((x,i)=>({delta:x-floor[i],i})).sort((a,b)=>b.delta-a.delta||a.i-b.i);
 remainders.slice(0,unused).forEach(o=>floor[o.i]++);
 const bets=picks.map((c,i)=>({combination:c.combination,virtual_yen:(floor[i]+1)*1000,
  head_course:c.headCourse,scenario:c.scenario,conditional_reason:c.scenario+'が成立 → '+c.secondCourse+'コースが追走 → '+c.thirdCourse+'コース残存',relative_score:+c.pseudo.toFixed(6)}));
 if(new Set(bets.map(x=>x.combination)).size!==bets.length||bets.reduce((sum,b)=>sum+b.virtual_yen,0)!==50000)throw Error('Invalid experimental virtual allocation');
 return {
   model:outsideTrial?'tactical-outside-makuri-v0.2-untrained':'tactical-1m-conditional-v0.1-untrained',
   basis:'保存済み発走前選手情報と場別参考値のみ。結果・払戻・オッズ不使用。',
   venue:input.venue,head_course_shares:shares.map((s,i)=>({course:i+1,lane:v[byCourse[i]].lane,relative_share:+s.toFixed(4),tactic:nameTactic[i+1]})),
   metadata:{venue_reference_rate:rate,wind_speed:wind,validMetrics,exhibition_used:validMetrics.length>0,
     source_at_utc:input.frozen_at_utc||null,
     ...(outsideTrial?{research_only:true,outside_attack_signals:outsideAttacks.map(a=>({
       course:a.course,launch:+a.launch.toFixed(4),steering:+a.steering.toFixed(4),
       preceding:+a.preceding.toFixed(4),multiplier:+a.multiplier.toFixed(4)}))}:{})},
   bets,top:bets[0]?.combination,
   differs_from_frozen:JSON.stringify(bets.map(x=>[x.combination,x.virtual_yen]))!==
     JSON.stringify((input.bets||[]).map(x=>[x.combination,x.virtual_yen])),
   is_frozen:false
 };
}
global.BoatTacticalModel={forecast,
 forecastOutside:input=>forecast({...input,experimental_variant:'outside-makuri-v0.2'}),
 RATE_BY_VENUE,nameTactic,version:'trial-v0.1-20261023'};
})(typeof window!=='undefined'?window:globalThis);
