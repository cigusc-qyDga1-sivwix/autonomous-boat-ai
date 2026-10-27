/* BOAT LAB tactical first-mark candidate scenarios v0.1.
 * Separate, explicitly NON-FROZEN research calculation.
 * Only frozen pre-race fields; no outcomes, payouts, odds or real betting.
 * Not calibrated probabilities. The six-way branch is a structural hypothesis.
 */
(function(global){
'use strict';
const START_PRIORS=[.48,.18,.16,.105,.05,.025];
// Verified venue 2026 Q3 course rates; informational / shadow trial only.
// Course-specific historical rates are NOT athlete-specific win probabilities.
const OUTSIDE_VENUE_COURSES={
 '唐津':{first:[.567,.127,.129,.106,.066,.015],second:[.196,.285,.192,.159,.140,.039],third:[.078,.204,.220,.197,.202,.110],source:'https://www.boatrace-karatsu.jp/modules/datafile/?page=index_suimen'},
 'びわこ':{first:[.566,.138,.138,.087,.060,.018],second:[.187,.245,.214,.165,.135,.063],third:[.080,.198,.198,.212,.169,.150],source:'https://www.boatrace-biwako.jp/modules/datafile/?kind=course&page=index_datacourse'},
 '福岡':{first:[.618,.141,.143,.063,.032,.009],second:[.172,.278,.250,.147,.112,.047],third:[.082,.183,.197,.264,.193,.088],source:'https://boatrace-fukuoka.com/modules/fukuokainfo/?page=index_jodata'}
};
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
// 2026-10-27 venue-surface trial: Edogawa is explicitly OUT OF SCOPE.
 // Every other venue retains its existing historical 1-course prior.
 // Extra tactical multipliers require official venue evidence AND independent
 // pre-race ST / relative movement support. No tide height, flow or wind angle
 // is invented. Only the four documented venues have an extra tactical test.
const SURFACE_OFFICIAL=Object.freeze({
 '戸田':{courses:[3,4],source:'https://www.boatrace-toda.jp/data/suimen_guide.html',focus:'狭い水面・大きな1Mの振り／センター速攻'},
 '平和島':{courses:[4,5],source:'https://www.boatrace.jp/owpc/pc/site/place/stadium/br04/',focus:'1M振り・ダッシュ攻め／風向未校正'},
 '福岡':{courses:[3,4],source:'https://www.boatrace.jp/owpc/pc/site/place/stadium/br22/',focus:'1Mの振り・センター攻め／満潮は未観測なら補正なし'},
 '唐津':{courses:[4],source:'https://www.boatrace-karatsu.jp/modules/datafile/?page=index_suimen',focus:'2025年12月ピット変更後・実進入とカド攻めを監視'}
});
function surfaceVenueTrial(input,move,byCourse,startSignals,primary){
 const name=input.venue,excluded=name==='江戸川';
 const profile=input.venue_profile;
 const profileValid=!!profile&&profile.name===name&&profile.code!=='03';
 const eligible=!!primary&&profileValid&&!excluded&&input.surface_trial_disabled!==true;
 const official=SURFACE_OFFICIAL[name]||null;
 const multipliers=[1,1,1,1,1,1],evidence=[];
 if(eligible&&official&&Array.isArray(startSignals)){
  for(const course of official.courses){
   const signal=startSignals[course-1],own=move[byCourse[course-1]],inside=move[byCourse[course-2]];
   if(!signal||!own||!inside)continue;
   const gap=signal.nearest_gap_sec,go=own.go/Math.max(.38,inside.go);
   const turn=own.turn/Math.max(.35,inside.turn);
   // Do not turn a venue anecdote into a free outside-lane bonus:
   // need a measured average ST gap and usable boat-speed support.
   if(signal.confidence<.60||gap===null||gap<.020||go<.95||turn<.90)continue;
   const stPart=.020*clamp((gap-.015)/.040,0,1);
   const movementPart=.025*clamp((go-.98)/.20,0,1);
   const multiplier=1+Math.min(.045,stPart+movementPart);
   if(multiplier<=1)continue;
   multipliers[course-1]=+multiplier.toFixed(6);
   evidence.push({course,st_gap_sec:gap,go_ratio:+go.toFixed(3),
                  turn_ratio:+turn.toFixed(3),multiplier:multipliers[course-1]});
  }
 }
 return {version:'venue-surface-v1-ex-edogawa',venue:name,excluded,
  eligible,applied:evidence.length>0,official_evidence:official?.source||null,
  registered_focus:profileValid?profile.tactical_focus:null,
  registered_water_type:profileValid?profile.water_type:null,
  center_attack_evidence:evidence,head_course_multipliers:multipliers,
  limitations:'場別基準1コース率は従来どおり。追加は公式確認4場で最大+4.5%の試験補正のみ。残り19場は観測根拠待ち。潮位・風向からの推測補正なし。確率未校正。',
  control_disabled:input.surface_trial_disabled===true};
}
// Trial ticket selection only. Scores, maneuvers and number of points stay fixed.
function headCoveragePicks(candidates,count,shares){
 const ranked=shares.map((share,i)=>({course:i+1,share})).sort((a,b)=>b.share-a.share||a.course-b.course);
 const selected=[];let mass=0;
 for(const row of ranked){
  if(selected.length && (mass>=.80 || row.share<.10))break;
  if((selected.length+1)*2>count)break;
  selected.push(row.course);mass+=row.share;
 }
 const reserved=selected.flatMap(h=>candidates.filter(c=>c.headCourse===h).slice(0,2));
 const keys=new Set(reserved.map(c=>c.combination));
 const picks=[...reserved];
 for(const c of candidates){if(picks.length>=count)break;if(!keys.has(c.combination)){picks.push(c);keys.add(c.combination);}}
 picks.sort((a,b)=>b.pseudo-a.pseudo||a.combination.localeCompare(b.combination));
 return {picks,policy:{version:'head-coverage-v1',calibrated:false,
  target_relative_mass:.80,min_head_relative_share:.10,tickets_per_selected_head:2,
  selected_head_courses:selected,selected_relative_mass:mass,point_count_unchanged:true,
  head_scores_unchanged:true,scope:'2026-10-27 pending cohort only; not a win probability guarantee'}};
}
function forecast(input){
 const headCoverage=input?.experimental_variant==='four-factor-v1.2';
 const openChasers=input?.experimental_variant==='four-factor-v1.1'||headCoverage;
 const fourFactor=input?.experimental_variant==='four-factor-v1.0'||openChasers;
 const wakeIntegrated=input?.experimental_variant==='outside-start-wake-v0.9'||fourFactor;
 const startTrial=input?.experimental_variant==='outside-start-gap-v0.7'||wakeIntegrated;
 const coupledTrial=input?.experimental_variant==='six-boat-coupling-v0.6'||startTrial;
 const wakeTrial=input?.experimental_variant==='wake-attrition-v0.3'||coupledTrial;
 const outerStudyTrial=input?.experimental_variant==='outside-role-v0.5'||coupledTrial;
 const roleAwareTrial=input?.experimental_variant==='role-consistency-v0.4'||outerStudyTrial;
 const outsideTrial=input?.experimental_variant==='outside-makuri-v0.2'||wakeTrial||outerStudyTrial;
 const runners=input?.racers;
 if(!Array.isArray(runners)||runners.length!==6)throw Error('6艇の保存済み出走情報が必要');
 const sorted=[...runners].sort((a,b)=>a.lane-b.lane);
 if(sorted.some((r,i)=>Number(r.lane)!==i+1))throw Error('艇番号1〜6が必要');
 const rawCourses=sorted.map(r=>finite(r.course,r.lane));
 const uniqueCourses=[...new Set(rawCourses)].length===6&&
   rawCourses.every(x=>x>=1&&x<=6&&Number.isInteger(x));
 if(wakeTrial&&!uniqueCourses)throw Error('引き波試験：6艇の実進入が未確認');
 const courses=uniqueCourses?
   rawCourses:sorted.map(r=>r.lane);
 const byCourse=Array.from({length:6},(_,i)=>courses.indexOf(i+1));
 const byLane=sorted;
 const v=sorted.map((r,i)=>{
   const win=clamp(finite(r.national_win_rate,4.5),1,10);
   const motor=clamp(finite(r.motor_top_2_percent,30),0,100);
   const st=finite(r.average_start_timing,.17);
   const avgValid=st>=.01&&st<=.4&&r.average_start_timing!==null&&r.average_start_timing!==undefined;
   const avg=avgValid?st:.17;
   const exhibit=finite(r.exhibition_time,null),est=finite(r.exhibition_st,null);
   const estValid=est!==null&&est>=0&&est<=.45; // Exhibition F is NOT a faster start.

   const lap=finite(r.original_exhibition?.lap_time,null);
   const turn=finite(r.original_exhibition?.turn_time,null);
   const straight=finite(r.original_exhibition?.straight_time,null);
   return {lane:i+1,course:courses[i],win,motor,avg,avgValid,exhibit,est,estValid,lap,turn,straight};
 });
 const mean=(key)=>v.reduce((s,x)=>s+x[key],0)/6;
 const meanWin=mean('win'),meanMotor=mean('motor'),meanST=mean('avg');
 const validMetrics=['exhibit','lap','turn','straight'].filter(key=>v.every(x=>x[key]!=null));
 const metricMean=Object.fromEntries(validMetrics.map(k=>[k,mean(k)]));
 const factorModel=fourFactor?global.BoatFourFactor?.evaluate(input):null;
 if(fourFactor&&!factorModel)throw Error('Four-factor engine unavailable');
 const move=v.map((x,i)=>{
  if(fourFactor){const score=factorModel.rows[i].combined_multiplier;return {go:score,turn:score,straight:score,overall:score};}
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
 // v0.7 ST research: predict relative SLIT formation from pre-race estimates
 // only; exhibition F is excluded, not interpreted as "exceptionally early".
 // No real start times, results or after-cutoff data enter this function.
 const startSignals=startTrial?Array.from({length:6},(_,i)=>{
   const own=v[byCourse[i]];
   const inner=i>0?v[byCourse[i-1]]:null;
   const stEstimate=x=>fourFactor?(x.avgValid?x.avg:null):x.avgValid?(x.estValid?
     .72*x.avg+.28*x.est:x.avg):(x.estValid?x.est:null);
   const ownST=stEstimate(own),innerST=inner?stEstimate(inner):null;
   const allInner=Array.from({length:i},(_,j)=>v[byCourse[j]]);
   const innerValid=allInner.map(stEstimate).filter(x=>x!==null);
   const nearestGap=ownST!==null&&innerST!==null?innerST-ownST:null;
   const innerGap=ownST!==null&&innerValid.length?
     innerValid.reduce((sum,st)=>sum+st,0)/innerValid.length-ownST:null;
   const wallHole=allInner.some(x=>{
     const s=stEstimate(x);
     return ownST!==null&&s!==null&&s-ownST>=.035;
   });
   const confidence=own.avgValid&&inner?.avgValid?(own.estValid&&inner.estValid?.88:.64):
     ownST!==null&&innerST!==null?.42:0;
   const go=move[byCourse[i]];
   const neighbor=inner?move[byCourse[i-1]]:null;
   const speedEdge=neighbor?go.go/Math.max(.38,neighbor.go):1;
   const turnEdge=neighbor?go.turn/Math.max(.35,neighbor.turn):1;
   const headEligible=i>=3&&confidence>=.60&&nearestGap!==null&&
     nearestGap>=.022&&speedEdge>=.92&&turnEdge>=.78;
   const secondEligible=i>=3&&confidence>=.42&&nearestGap!==null&&
     nearestGap>=.012&&go.go>=.72&&go.turn>=.70;
   const tactics=[];
   if(headEligible&&speedEdge>=1.05&&nearestGap>=.04)tactics.push('まくり先行');
   if(headEligible&&wallHole&&turnEdge>=.85)tactics.push('まくり差しの差し場');
   if(secondEligible)tactics.push('攻め残り・追走2着');
   return {course:i+1,lane:own.lane,estimated_st:ownST===null?null:+ownST.toFixed(3),
     nearest_gap_sec:nearestGap===null?null:+nearestGap.toFixed(3),
     inside_mean_gap_sec:innerGap===null?null:+innerGap.toFixed(3),
     wall_hole:wallHole,confidence:+confidence.toFixed(2),
     speed_ratio:+speedEdge.toFixed(3),turn_ratio:+turnEdge.toFixed(3),
     head_evidence:!!headEligible,second_evidence:!!secondEligible,
     tactic_candidates:tactics,exhibition_f_ignored:own.est!==null&&!own.estValid};
 }):[];
 const rate=finite(input.venue_profile?.course1_reference_rate,RATE_BY_VENUE[input.venue]??.55);
 const head1=clamp(rate,.38,.67);
 // Retain conservative venue dependence, but no hardcoded course-1 winner.
 let rateImpact=clamp(head1/.55,.7,1.3);
 const wind=finite(input.weather_used?.wind_speed,null);
 let hedge=fourFactor?1:wind!==null&&wind>=6?.82:wind!==null&&wind>=4?.9:1;
 const officialReference=outerStudyTrial?OUTSIDE_VENUE_COURSES[input.venue]||null:null;
 const refBlend=.35;
 const effectivePriors=officialReference?
   START_PRIORS.map((prior,c)=>prior*(1-refBlend)+officialReference.first[c]*refBlend):
   [...START_PRIORS];
 let strength=effectivePriors.map((prior,c)=>{
  const idx=byCourse[c],m=move[idx];
  const base=prior*(c===0?rateImpact:((1-rateImpact*.49)/.51));
  const skill= Math.pow(m.go,c===0?.85:1.55)*
    Math.pow(m.turn,c===0?.8:c===1?1.25:1.1)*
    Math.pow(m.straight,c>=2?1.05:.4);
  const penalty=c===0?hedge:(2-hedge)**.65;
  return Math.max(.0001,base*clamp(skill,.25,3.1)*penalty);
 });
 const venueSurface=surfaceVenueTrial(input,move,byCourse,startSignals,openChasers);
 if(venueSurface.applied){
  for(let course=1;course<=6;course++)
   strength[course-1]*=venueSurface.head_course_multipliers[course-1];
 }
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
 // V0.5: an outside boat receives an additional correction ONLY with
 // independent pre-race evidence of attack and turn strength.
 const outsideEvidence={};
 if(outerStudyTrial){
  for(const signal of outsideAttacks){
   const course=signal.course,m=move[byCourse[course-1]];
   const inner=move[byCourse[course-2]];
   const entry=signal.launch>=1.04&&signal.steering>=.91&&
     m.go>=Math.max(.68,inner.go*.97);
   const confidence=entry?clamp((signal.launch-1.025)*1.8+
     (signal.steering-.93)*.65,0,.7):0;
   const followerCourse=course<6?course+1:null;
   const follower=followerCourse?move[byCourse[followerCourse-1]]:null;
   const follows=!!(confidence>=.10&&follower&&
     follower.go>=m.go*.74&&follower.turn>=m.turn*.72);
   outsideEvidence[course]={course,attack:entry,confidence:+confidence.toFixed(4),
     follower_course:followerCourse,following_supported:follows,
     launch:+signal.launch.toFixed(4),steering:+signal.steering.toFixed(4)};
   if(entry)strength[course-1]*=1+.7*confidence;
  }
  if(outsideEvidence[4]?.confidence>=.10)
   strength[0]*=clamp(1-.15*outsideEvidence[4].confidence,.92,1);
 }
 // V0.7 bounded head-role correction when an outside starter may arrive early.
 // Venue priors still apply; a fast ST by itself never guarantees a win.
 if(startTrial){
  for(const signal of startSignals.slice(3)){
   if(!signal.head_evidence)continue;
   const strengthOfEvidence=clamp((signal.nearest_gap_sec-.015)/.06,0,1);
   strength[signal.course-1]*=1+clamp(.55*strengthOfEvidence+
     .32*Math.max(0,signal.speed_ratio-1)+.22*(signal.wall_hole?1:0),0,1.18);
  }
  if(startSignals.slice(3).some(s=>s.head_evidence&&s.wall_hole))
   strength[0]*=.96; // Do not automatically erase an inside survival branch.
 }
 // Incomplete hydrodynamic proxy: a makuri or sweeping outer turn may put
 // an inner boat across its wake. This score is not an observed trajectory,
 // probability, or a guarantee of losing the top 3.
 function estimatedWakeRisk(headCourse,otherCourse){
  if(!wakeTrial||headCourse<3||otherCourse>=headCourse)return 0;
  const attacker=move[byCourse[headCourse-1]];
  const inner=move[byCourse[otherCourse-1]];
  if(!attacker||!inner)return 0;
  const speedRatio=attacker.go/Math.max(.38,inner.go);
  const turnRatio=attacker.turn/Math.max(.35,inner.turn);
  // 4-course makuri is the clearest case; for 3/5/6-course labels the
  // actual turn type is unknown, so the hypothetical wave impact is lighter.
  const tacticScale=headCourse===4?1:headCourse===3?.42:.48;
  const crossing=clamp((speedRatio-.98)*.70+(turnRatio-.96)*.24,0,.88);
  const distance=clamp(1-.07*Math.max(0,headCourse-otherCourse-1),.68,1);
  return clamp(crossing*tacticScale*distance,0,.75);
 }
 // V0.6: directed interactions between an ATTACKER and the other five boats.
 // This is a bounded, untrained mechanistic hypothesis: NOT observed trajectories,
 // NOT a calibrated probability and NOT inferred from the race result.
 const coupling=coupledTrial?Array.from({length:6},(_,i)=>{
   const h=i+1,attacker=move[byCourse[i]];
   const nearest=h>=2?move[byCourse[h-2]]:null;
   const innerFast=h>=3?Math.max(...Array.from({length:h-1},(_,j)=>move[byCourse[j]].go)):0;
   const reference=nearest?Math.max(.35,.72*nearest.go+.28*innerFast):null;
   const goRatio=reference?attacker.go/reference:1;
   const turnRatio=nearest?attacker.turn/Math.max(.35,nearest.turn):1;
   const pressure=h>=3?clamp(1.05*(goRatio-1)+.55*(turnRatio-1),0,.82):
     h===2?clamp(.6*(goRatio-1)+.25*(turnRatio-1),0,.65):0;
   const next=h<6?move[byCourse[h]]:null;
   const follow=next?clamp(.55+.55*(next.go/attacker.go-.8)+
     .36*(next.turn/attacker.turn-.8),0,1):0;
   const inside=Array.from({length:h-1},(_,j)=>{
     const m=move[byCourse[j]];
     const vulnerability=clamp(.65+.4*(attacker.go/m.go-1)-
       .32*(m.turn/Math.max(.35,attacker.turn)-1),.35,1.15);
     return {course:j+1,lane:v[byCourse[j]].lane,
       risk:+clamp(pressure*vulnerability,0,.9).toFixed(4)};
   });
   const tactic=h===1?'最短先マイを守る':h===2?(pressure>=.22?'差し・まくり両にらみ':'内の差し残り'):
     goRatio>=1.08&&turnRatio>=.92?'外からのまくり':
       turnRatio>=.98?'まくり差し・差し場探索':'外の残存・攻め待ち';
   return {head_course:h,head_lane:v[byCourse[i]].lane,tactic,
     pressure:+pressure.toFixed(4),follower_course:h<6?h+1:null,
     follower_lane:h<6?v[byCourse[h]].lane:null,
     follower_readiness:+follow.toFixed(4),inside};
 }):[];
 const denom=strength.reduce((a,b)=>a+b,0),shares=strength.map(v=>v/denom);
 // Condition second and third on WHICH first-turn maneuver succeeded. If c=3
 // attacks, nearby c2 and inside c1 can survive; if c1 escapes, c2/c3 can chase.
 // New forward-only v0.9: an inside winner ALSO leaves wake for 2M followers.
 // Bounded pre-race speed/turn proxy, NOT observed wave positions or speed loss.
 function followingWakeFactor(headCourse,followerCourse,phase){
  if(!wakeIntegrated)return 1;
  const leader=move[byCourse[headCourse-1]],chaser=move[byCourse[followerCourse-1]];
  if(!leader||!chaser)return 1;
  const goRatio=chaser.go/Math.max(.38,leader.go);
  const turnRatio=chaser.turn/Math.max(.35,leader.turn);
  const avoidance=clamp(.55*(goRatio-1)+.42*(turnRatio-1),-.32,.38);
  const exposure=clamp((phase==='second'?.10:.075)-avoidance*.31,.015,.21);
  return clamp(1-exposure+Math.max(0,avoidance)*.37,.79,1.17);
 }
 // v1.1: candidate ability first; no winner-neighbor lookup or stacked follow
 // bonuses. The small course prior is unconditional. A bounded relative-strength
 // adjustment represents competition, not an asserted maneuver or wake path.
 function openRoleWeight(h,s,c,phase){
  const own=move[byCourse[c-1]].overall;
  const leader=move[byCourse[(phase==='second'?h:s)-1]].overall;
  const prior=(phase==='second'?[1.10,1.10,1.06,1.02,.98,.94]:[1.04,1.04,1.03,1.02,1,.98])[c-1];
  const interaction=clamp(1+.05*(own/leader-1),.95,1.05);
  return prior*Math.pow(own,phase==='second'?1.15:.95)*interaction;
 }
 function secondWeight(headCourse,secondCourse){
  if(openChasers)return openRoleWeight(headCourse,null,secondCourse,'second');
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
  if(outerStudyTrial&&secondCourse>=4){
    const candidate=move[byCourse[secondCourse-1]];
    const lead=outsideEvidence[secondCourse-1],own=outsideEvidence[secondCourse];
    const following=lead?.following_supported&&lead?.follower_course===secondCourse;
    if(following&&headCourse===secondCourse-1)
      relation*=clamp(1+1.05*lead.confidence,1,1.70);
    else if(headCourse===1&&following&&candidate.go>=.9)
      relation*=clamp(1+.55*lead.confidence,1,1.38);
    else if(headCourse===2||headCourse===3)
      relation*=own?.attack&&candidate.turn>=.93?clamp(1+.3*own.confidence,1,1.2):1;
   }
   if(startTrial&&secondCourse>=4){
     const signal=startSignals[secondCourse-1];
     if(signal.second_evidence){
       // May finish 2nd despite a failed winning attack; head and 2nd
       // are scored INDEPENDENTLY, including course 6 without a follower.
       const lead=startSignals[headCourse-1];
       const follow=(headCourse>=3&&headCourse<secondCourse)?
         clamp(1+.30*(lead?.head_evidence?1:0),1,1.3):1;
       relation*=follow*(1+clamp(.46*(signal.nearest_gap_sec/.05)+
         .16*(signal.wall_hole?1:0),.08,.76));
     }
   }
   if(wakeTrial)relation*=clamp(1-.82*estimatedWakeRisk(headCourse,secondCourse),.39,1);
   if(wakeIntegrated){
    relation*=followingWakeFactor(headCourse,secondCourse,'second');
    const attack=coupling[headCourse-1],chaser=move[byCourse[secondCourse-1]];
    if(headCourse>=3&&secondCourse===attack.follower_course&&
       attack.pressure>=.12&&attack.follower_readiness>=.55&&chaser.turn>=.88)
      relation*=clamp(1+.26*attack.pressure*attack.follower_readiness,1,1.22);
   }
   if(coupledTrial){
     const attack=coupling[headCourse-1];
     if(headCourse>=3){
       // Consequence A: the boat directly outside a credible attacker can
       // FOLLOW its path, but cannot automatically outrank the inside survivor.
       if(secondCourse===attack.follower_course)
         relation*=1+.95*attack.pressure*attack.follower_readiness;
       // Consequence B: displaced inner boats might drop from 2nd to 3rd.
       const victim=attack.inside.find(x=>x.course===secondCourse);
       if(victim)relation*=clamp(1-.42*victim.risk,.62,1);
     }else if(headCourse===1&&secondCourse>=3){
       // Even when 1 survives, a strong outside attacker can chase to second.
       const follow=coupling[secondCourse-1];
       if(follow.pressure>.12)
         relation*=1+.23*follow.pressure*clamp(z.turn,.6,1.5);
     }
   }
  return Math.max(.01,relation*Math.pow(z.turn,.85)*Math.pow(z.go,.3));
 }
 function thirdWeight(h,s,c){
  if(openChasers)return openRoleWeight(h,s,c,'third');
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
  if(outerStudyTrial&&c>=4){
    const earlier=outsideEvidence[c-1];
    if(earlier?.following_supported&&earlier.follower_course===c&&h===c-1)
      consistency*=clamp(1+.7*earlier.confidence,1,1.5);
   }
   if(wakeTrial)consistency*=clamp(1-.75*estimatedWakeRisk(h,c),.43,1);
   if(wakeIntegrated){
    // 3rd may follow the 2nd boat into choppy water. Preserve survivors.
    consistency*=followingWakeFactor(s,c,'third');
    if(h>=3&&c<h&&s<h){
      const survivor=coupling[h-1].inside.find(z=>z.course===c);
      if(survivor&&survivor.risk>.25)
       consistency*=clamp(1-.18*survivor.risk,.85,1);
    }
   }
   if(coupledTrial){
     const attack=coupling[h-1];
     if(h>=3){
       const survivor=attack.inside.find(z=>z.course===c);
       // Conditional on the 2nd position: a displaced inner boat can
       // survive in 3rd while another follows the attacking boat.
       if(survivor&&s===attack.follower_course)
         consistency*=1+.35*survivor.risk*clamp(x.turn,.55,1.5);
       // If the inside boat kept 2nd, a strong following boat may get 3rd.
       if(c===attack.follower_course&&s<h)
         consistency*=1+.8*attack.pressure*attack.follower_readiness;
       // Two inner survivors behind a credible sweeping attack compete for
       // a crowded pocket; do not count both as independent clean turns.
       if(c<h&&s<h&&attack.pressure>.15)
         consistency*=clamp(1-.24*attack.pressure,.79,1);
     }
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
      scenario:openChasers?'攻め方未確定・全艇の残存評価':nameTactic[h],secondCourse:s,thirdCourse:t,headShare:shares[h-1]});
   }
  }
 }
 candidates.sort((a,b)=>b.pseudo-a.pseudo||a.combination.localeCompare(b.combination));
 // Marginal role strengths use all 120 combinations, BEFORE selecting tickets.
 // First-place rank alone is never a guarantee of second-place suitability.
 const roleShares={first:{},second:{},third:{}};
 for(let lane=1;lane<=6;lane++){
  roleShares.first[lane]=0;roleShares.second[lane]=0;roleShares.third[lane]=0;
 }
 for(const candidate of candidates){
  const [a,b,c]=candidate.combination.split('-').map(Number);
  roleShares.first[a]+=candidate.pseudo;
  roleShares.second[b]+=candidate.pseudo;
  roleShares.third[c]+=candidate.pseudo;
 }
 const dominant=Math.max(...shares),close=shares.filter(x=>x>=.12).length;
 const count=clamp(Math.round(6+5*close/4+4*(.58-dominant)),4,12);
 const coverage=headCoverage?headCoveragePicks(candidates,count,shares):null;
 let picks=coverage?coverage.picks:candidates.slice(0,count);
 const roleChanges=[];
 if(!openChasers){
 if(roleAwareTrial){
 function replaceWithEvidence(candidate,role,lane){
  if(!candidate||picks.some(p=>p.combination===candidate.combination))return false;
  if(picks.some(p=>p.combination.split('-')[role==='head'?0:1]===String(lane)))return false;
  // Do not remove the top combo or the last meaningful alternative winner.
  const removable=picks.map((p,i)=>({p,i})).filter(({p,i})=>i!==0&&
   (shares[p.headCourse-1]<.12||picks.filter(q=>q.headCourse===p.headCourse).length>1))
   .sort((a,b)=>a.p.pseudo-b.p.pseudo||b.i-a.i);
  if(!removable.length)return false;
  const slot=removable[0];
  if(candidate.pseudo<slot.p.pseudo*.55)return false;
  picks[slot.i]=candidate;
  roleChanges.push({role,lane,combination:candidate.combination,
   reason:role==='head'?'攻め成功を持つ頭の勝ち筋':'条件付き展開で支持される2着浮上'});
  return true;
 }
 const credibleHeads=shares.map((share,i)=>({course:i+1,share}))
  .filter(x=>x.share>=.12).sort((a,b)=>b.share-a.share);
 for(const {course} of credibleHeads){
  if(!picks.some(p=>p.headCourse===course))
   replaceWithEvidence(candidates.find(c=>c.headCourse===course),'head',v[byCourse[course-1]].lane);
 }
 if(outsideTrial){
  // Outside-head protection requires evidence of an actual attacking advantage.
  const strongOutside=outsideAttacks.filter(a=>a.multiplier>=1.14&&
   shares[a.course-1]>=.045).sort((a,b)=>shares[b.course-1]-shares[a.course-1]);
  for(const a of strongOutside.slice(0,2)){
   if(!picks.some(p=>p.headCourse===a.course))
    replaceWithEvidence(candidates.find(p=>p.headCourse===a.course),'head',v[byCourse[a.course-1]].lane);
  }
 }
 // A 2nd-place branch must pass a separate marginal check, be a credible
 // first-place contender, AND be a competitive full trifecta combination.
 const firstOrder=shares.map((share,i)=>({lane:v[byCourse[i]].lane,share}))
  .sort((a,b)=>b.share-a.share);
 for(const {lane,share} of firstOrder.slice(0,3)){
  if(share<.08||roleShares.second[lane]<.12||
     picks.some(p=>p.combination.split('-')[1]===String(lane)))continue;
  const candidate=candidates.find(p=>p.combination.split('-')[1]===String(lane));
  replaceWithEvidence(candidate,'second',lane);
 // Preserve a 4/5/6 2nd-place role ONLY when that boat can follow a
 // documented adjacent outer-course attack. No per-course ticket quota.
 if(outerStudyTrial){
  const supported=[4,5,6].map(course=>({
    course,lane:v[byCourse[course-1]].lane,
    second:roleShares.second[v[byCourse[course-1]].lane],
    following:outsideEvidence[course-1]?.following_supported===true
  })).filter(x=>x.following&&x.second>=.085).sort((a,b)=>b.second-a.second);
  for(const x of supported.slice(0,2)){
   if(!picks.some(p=>p.combination.split('-')[1]===String(x.lane))){
    const candidate=candidates.find(p=>p.combination.split('-')[1]===String(x.lane)&&
      p.headCourse===x.course-1);
    replaceWithEvidence(candidate,'second',x.lane);
   }
  }
 }
 }
 }else{
 // Preserve exact earlier selection for previously frozen v0.1/v0.2/v0.3.
 for(let head=2;head<=6;head++){
  if(shares[head-1]<.12||picks.some(x=>x.headCourse===head))continue;
  const alternative=candidates.find(x=>x.headCourse===head);
  if(!alternative)continue;
  const replace=picks.findLastIndex(x=>x.headCourse===1);
  if(replace!==-1)picks[replace]=alternative;
 }
 if(outsideTrial){
  const strongOutside=outsideAttacks.filter(a=>a.multiplier>=1.14&&
    shares[a.course-1]>=.045).sort((a,b)=>shares[b.course-1]-shares[a.course-1]);
  for(const a of strongOutside.slice(0,2)){
   if(picks.some(p=>p.headCourse===a.course))continue;
   const candidate=candidates.find(p=>p.headCourse===a.course);
   const replace=picks.findLastIndex(p=>p.headCourse===1);
   if(candidate&&replace>=0)picks[replace]=candidate;
  }
 }
 }
 // A 4/5/6 head or second can be missing from 4–12 picks even when its
 // pre-race start gap is credible. Add the best distinct scenario only if
 // it competes with the currently lowest-ticket evidence; NO seat quotas.
 if(startTrial){
   const ordered=startSignals.slice(3).filter(s=>s.head_evidence||s.second_evidence)
    .sort((a,b)=>(b.nearest_gap_sec||0)-(a.nearest_gap_sec||0));
   for(const signal of ordered){
     for(const role of ['head','second']){
       if(role==='head'&&!signal.head_evidence||role==='second'&&!signal.second_evidence)continue;
       const pos=role==='head'?0:1;
       const already=picks.some(p=>p.combination.split('-')[pos]===String(signal.lane));
       if(already)continue;
       const best=candidates.find(p=>p.combination.split('-')[pos]===String(signal.lane));
       if(!best||picks.some(p=>p.combination===best.combination))continue;
       const candidatesToReplace=picks.map((p,i)=>({p,i})).filter(({p,i})=>{
         if(i===0)return false;
         if(p.headCourse!==1&&picks.filter(q=>q.headCourse===p.headCourse).length===1)return false;
         return true;
       }).sort((a,b)=>a.p.pseudo-b.p.pseudo||b.i-a.i);
       const worst=candidatesToReplace[0];
       // Avoid an unconditional 4/5/6 ticket for very weak probabilities;
       // allow a controlled loss of ranking to cover a DISTINCT supported path.
       if(!worst||best.pseudo<worst.p.pseudo*.48)continue;
       picks[worst.i]=best;
       roleChanges.push({role,lane:signal.lane,combination:best.combination,
        reason:'スタート先行・内側凹みの根拠で'+signal.course+'コースの'+
          (role==='head'?'まくり／まくり差し頭':'展開2着')+'を試験採用'});
     }
   }
 }
 } // v1.1 keeps the top-ranked combinations; no legacy ticket rescue.
 const roleCoverage={};
 for(let lane=1;lane<=6;lane++){
  const combos=picks.map(p=>p.combination.split('-').map(Number));
  const presence=[1,2,3].map(n=>combos.filter(p=>p[n-1]===lane).length);
  const first=roleShares.first[lane],second=roleShares.second[lane],third=roleShares.third[lane];
  let note='展開条件別の役割評価';
  if(first>=.12&&!presence[0])note='高い1着評価に対して頭が抜ける（要再検討）';
  else if(first>=.08&&second>=.12&&!presence[1])note='1・2着とも候補だが2着筋は点数枠に残らず';
  else if(presence[2]&&!presence[0]&&!presence[1])note='3着のみ採用（1・2着は成立条件を再検討）';
  roleCoverage[lane]={first:+first.toFixed(4),second:+second.toFixed(4),
   third:+third.toFixed(4),headTickets:presence[0],secondTickets:presence[1],
   thirdTickets:presence[2],note};
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
  head_course:c.headCourse,scenario:c.scenario,
  conditional_reason:openChasers?
   c.headCourse+'コース頭の条件で残り5艇を能力評価 → '+c.secondCourse+'コース2着 → 残り4艇から'+c.thirdCourse+'コース3着（攻め方未確定）':startTrial?
   c.headCourse+'コース '+(startSignals[c.headCourse-1]?.tactic_candidates.join('／')||coupling[c.headCourse-1].tactic)+'（ST差の仮説） → '+c.secondCourse+'コース2着 → '+c.thirdCourse+'コース3着':
   coupledTrial?
   c.headCourse+'コース '+coupling[c.headCourse-1].tactic+'（仮説） → '+c.secondCourse+'コースが2着を確保 → '+c.thirdCourse+'コースが3着に残存':
   c.scenario+'が成立 → '+c.secondCourse+'コースが追走 → '+c.thirdCourse+'コース残存',
  relative_score:+c.pseudo.toFixed(6)}));
 if(new Set(bets.map(x=>x.combination)).size!==bets.length||bets.reduce((sum,b)=>sum+b.virtual_yen,0)!==50000)throw Error('Invalid experimental virtual allocation');
 // Conditional second-place evaluation is distinct from the global marginal.
 // A rise in a boat's FIRST share can lower its unconditional SECOND share.
 // Given inside-1 winning, expose each remaining boat's second-place weight.
 const headOneScores=startTrial?Array.from({length:5},(_,i)=>({
   course:i+2,lane:v[byCourse[i+1]].lane,weight:secondWeight(1,i+2)
 })):[];
 const headOneTotal=headOneScores.reduce((n,x)=>n+x.weight,0);
 return {
   model:headCoverage?'four-factor-v1.2-head-coverage-untrained':openChasers?'four-factor-v1.1-untrained':fourFactor?'four-factor-v1.0-untrained':wakeIntegrated?'tactical-outside-start-wake-v0.9-untrained':
      startTrial?'tactical-outside-start-gap-v0.7-untrained':
     coupledTrial?'tactical-six-boat-coupling-v0.6-untrained':
     outerStudyTrial?'tactical-outside-role-v0.5-untrained':
     roleAwareTrial?'tactical-role-consistency-v0.4-untrained':
     wakeTrial?'tactical-wake-attrition-v0.3-untrained':
     outsideTrial?'tactical-outside-makuri-v0.2-untrained':'tactical-1m-conditional-v0.1-untrained',
   basis:'保存済み発走前選手情報と場別参考値のみ。結果・払戻・オッズ不使用。',
   venue:input.venue,head_course_shares:shares.map((s,i)=>({course:i+1,lane:v[byCourse[i]].lane,relative_share:+s.toFixed(4),tactic:openChasers?'攻め方未確定':nameTactic[i+1]})),
   metadata:{...(fourFactor?{four_factor:{...factorModel,...(coverage?{ticket_policy:coverage.policy}:{}),...(openChasers?{chaser_policy:{
        version:'ability-first-v1.1',fixed_neighbor_bonus:false,legacy_ticket_rescue:false,
        interaction_bounds:[.95,1.05],calibrated:false,
        second_by_head:[1,2,3,4,5,6].map(h=>{
          const rows=[1,2,3,4,5,6].filter(c=>c!==h).map(c=>({course:c,lane:v[byCourse[c-1]].lane,weight:secondWeight(h,c)}));
          const total=rows.reduce((n,x)=>n+x.weight,0);
          return {head_course:h,candidates:rows.map(x=>({...x,relative_share:x.weight/total}))};
        }),
        third_by_pair:[1,2,3,4,5,6].flatMap(h=>[1,2,3,4,5,6].filter(s=>s!==h).map(s=>{
          const rows=[1,2,3,4,5,6].filter(c=>c!==h&&c!==s).map(c=>({course:c,lane:v[byCourse[c-1]].lane,weight:thirdWeight(h,s,c)}));
          const total=rows.reduce((n,x)=>n+x.weight,0);
          return {head_course:h,second_course:s,candidates:rows.map(x=>({...x,relative_share:x.weight/total}))};
        }))
      }}:{})}}:{}),venue_reference_rate:rate,wind_speed:wind,validMetrics,exhibition_used:validMetrics.length>0,
      ...(wakeIntegrated?{wake_v09:{
        pre_cutoff_only:true,...(openChasers?{applied_to_chaser_scores:false}:{}),calibrated:false,studied_phases:['1M','2M+'],
        applies_to_all_head_courses:true,
        note:'No measured wake crossings or speed loss. Bounded pre-race hypothetical scenario factors.',
        head_course_exposure:[1,2,3,4,5,6].map(course=>({
          course,one_mark_inner_risk:course>=3?
            Array.from({length:course-1},(_,i)=>({course:i+1,
              relative_risk:+estimatedWakeRisk(course,i+1).toFixed(4)})):[],
          second_chasers:[1,2,3,4,5,6].filter(c=>c!==course).map(c=>({
            course:c,relative_multiplier:+followingWakeFactor(course,c,'second').toFixed(4)
          }))
        }))
      }}:{}),
     ...(startTrial?{start_v07:{
       slit_signals:startSignals,
       second_given_inside_first:headOneScores.map(x=>({
         course:x.course,lane:x.lane,
         conditional_relative_weight:+(x.weight/headOneTotal).toFixed(5)
       })),
       description:'Pre-race average and legal exhibition ST estimates; relative nearest-course gap, inner wall and bounded role rescue',
       prediction_only:true,calibrated:false,
       disclaimer:'Not actual race ST, not guaranteed makuri / makuri-zashi. Exhibition F ignored.'
     }}:{}),
     ...(coupledTrial?{coupled_v06:{
       interaction_graph:coupling,...(openChasers?{applied_to_chaser_scores:false}:{}),
       branch_definition:'1M head attack -> inner displacement / outer follow -> conditional 2nd and 3rd',
       analysis_only:true,calibrated:false,
       disclaimer:'No actual hull coordinates or wake measurements; mechanism hypotheses only. Race results, payouts, odds not used.'
     }}:{}),
     ...(outerStudyTrial?{outside_v05:{
       reference_period:'2026-07-01/2026-09-30',
       reference_source:officialReference?.source||null,
       venue_specific_prior:!!officialReference,prior_blend:officialReference?refBlend:0,
       effective_course_prior:effectivePriors.map(x=>+x.toFixed(4)),
       conditional_outside_evidence:Object.values(outsideEvidence),
       proof_note:'Untrained relative model, not calibrated win probabilities. No blanket exterior picks.'
     }}:{}),
     ...(openChasers?{venue_surface_v1:venueSurface}:{}),
     source_at_utc:input.frozen_at_utc||null,
     ...(wakeTrial?{wake_research_only:true,wake_hypothesis:'inner boat may lose acceleration when crossed by outer makuri wash; not measured',
         wake_risk_by_attacker: [3,4,5,6].map(h=>({
            head_course:h,inner_courses:Array.from({length:h-1},(_,i)=>({
              course:i+1,estimated_exposure:+estimatedWakeRisk(h,i+1).toFixed(4)
            }))
         }))
       }:{ }),
     ...(outsideTrial?{research_only:true,outside_attack_signals:outsideAttacks.map(a=>({
       course:a.course,launch:+a.launch.toFixed(4),steering:+a.steering.toFixed(4),
       preceding:+a.preceding.toFixed(4),multiplier:+a.multiplier.toFixed(4)}))}:{})},
   role_coverage:roleCoverage,role_changes:roleChanges.filter(change=>
    bets.some(b=>b.combination===change.combination)),
  bets,top:bets[0]?.combination,
   differs_from_frozen:JSON.stringify(bets.map(x=>[x.combination,x.virtual_yen]))!==
     JSON.stringify((input.bets||[]).map(x=>[x.combination,x.virtual_yen])),
   is_frozen:false
 };
}
global.BoatTacticalModel={forecast,
 headCoveragePicks,
 forecastFourFactorCoverage:input=>forecast({...input,experimental_variant:'four-factor-v1.2'}),
 forecastFourFactorOpen:input=>forecast({...input,experimental_variant:'four-factor-v1.1'}),
 forecastFourFactor:input=>forecast({...input,experimental_variant:'four-factor-v1.0'}),
 forecastRoleAware:input=>forecast({...input,experimental_variant:'role-consistency-v0.4'}),
 forecastOutsideRole:input=>forecast({...input,experimental_variant:'outside-role-v0.5'}),
 forecastCoupled:input=>forecast({...input,experimental_variant:'six-boat-coupling-v0.6'}),
 forecastOutsideStart:input=>forecast({...input,experimental_variant:'outside-start-gap-v0.7'}),
 forecastWakeIntegrated:input=>forecast({...input,experimental_variant:'outside-start-wake-v0.9'}),
 forecastOutside:input=>forecast({...input,experimental_variant:'outside-makuri-v0.2'}),
 forecastWake:input=>forecast({...input,experimental_variant:'wake-attrition-v0.3'}),
 RATE_BY_VENUE,OUTSIDE_VENUE_COURSES,nameTactic,version:'trial-v0.9-wake-20261025'};
})(typeof window!=='undefined'?window:globalThis);
