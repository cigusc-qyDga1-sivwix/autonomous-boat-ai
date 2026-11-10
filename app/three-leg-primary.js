/* BOAT LAB v2.3: conservative three-leg redistribution of the EXISTING
 * 10%-weighted exhibition factor across 1M movement roles.
 *
 * No extra performance score, probability, or extra wagering. Each boat's
 * geometric mean go/turn/straight multiplier remains exactly the prior
 * four-factor movement score (up to floating point). NO double counting.
 * Stage attribution is an uncalibrated prospective hypothesis.
 */
(function(root){
'use strict';
const VERSION='three-leg-formal-redistribution-v0.1-untrained';
const MAX_LOG=.012;
const METRICS=Object.freeze({
 exhibition_time:{lo:5,hi:10,scale:.30},
 lap_time:{lo:30,hi:50,scale:2},
 half_lap_time:{lo:15,hi:25,scale:1},
 turn_time:{lo:4,hi:15,scale:.8},
 straight_time:{lo:5,hi:12,scale:.5}
});
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
function complete(racers,key){
 const spec=METRICS[key];
 if(!spec)return null;
 const values=racers.map(r=>key==='exhibition_time'?
   r.exhibition_time:r.original_exhibition?.[key]);
 if(!values.every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=spec.lo&&x<=spec.hi))
   return null;
 const mean=values.reduce((s,x)=>s+x,0)/6;
 return values.map(x=>clamp((mean-x)/spec.scale,-1,1));
}
function evaluate(input,fourFactor){
 const empty={version:VERSION,applied:false,calibrated:false,
  result_data_used:false,pre_cutoff_only:true,model_role:'formal_component',
  method:'bounded_log_stage_redistribution_without_extra_factor',
  max_abs_stage_log:MAX_LOG,rows:[]};
 if(input?.three_leg_primary_trial!==true||input?.linked_primary_trial!==true||
    input?.phase!=='exhibition'||input?.venue==='江戸川')
   return {...empty,status:'not_eligible'};
 const racers=Array.isArray(input.racers)?[...input.racers].sort((a,b)=>a.lane-b.lane):[];
 if(racers.length!==6||racers.some((r,i)=>r.lane!==i+1)||
    new Set(racers.map(r=>r.course)).size!==6||
    racers.some(r=>!Number.isInteger(r.course)||r.course<1||r.course>6))
   return {...empty,status:'invalid_six_boats'};
 if(!fourFactor||!Array.isArray(fourFactor.rows)||fourFactor.rows.length!==6)
   return {...empty,status:'missing_four_factor'};
 const exhibit=complete(racers,'exhibition_time');
 const turn=complete(racers,'turn_time');
 if(!exhibit||!turn)return {...empty,status:'incomplete_required_exhibition'};
 const venue=input.venue;
 const lapKey=venue==='桐生'?'half_lap_time':'lap_time';
 const lap=complete(racers,lapKey);
 const straight=(
   ['住之江','尼崎','徳山'].includes(venue)?null:complete(racers,'straight_time'));
 const special=venue==='浜名湖'||venue==='福岡';
 const sourceKeys=['exhibition_time','turn_time'];
 if(lap)sourceKeys.push(lapKey);
 if(straight)sourceKeys.push('straight_time');
 const rows=racers.map((r,i)=>{
   const turnSignal=lap?.8*turn[i]+.2*lap[i]:turn[i];
   const stretchSignal=special?exhibit[i]:
      straight?.25*exhibit[i]+.75*straight[i]:exhibit[i];
   let logGo=0,logTurn=0,logStraight=0,goObserved=false;
   // At ordinary venues a numerical independent "行き足" is NOT
   // available; leave go unchanged. Move existing information from
   // stretch to turn (and vice versa), never add it as a new bonus.
   if(special&&straight){
     goObserved=true;
     const goSignal=straight[i];
     const mean=(goSignal+turnSignal+stretchSignal)/3;
     const raw=[goSignal-mean,turnSignal-mean,stretchSignal-mean];
     const max=Math.max(1,...raw.map(Math.abs));
     const strength=MAX_LOG/max;
     [logGo,logTurn,logStraight]=raw.map(v=>v*strength);
   }else{
     const d=clamp(MAX_LOG*(turnSignal-stretchSignal)/2,-MAX_LOG,MAX_LOG);
     logTurn=d;
     logStraight=-d;
   }
   const combined=fourFactor.rows[i].combined_multiplier;
   if(typeof combined!=='number'||!Number.isFinite(combined)||combined<=0)
     throw Error('Missing canonical four-factor movement');
   const changes={go:Math.exp(logGo),turn:Math.exp(logTurn),
                 straight:Math.exp(logStraight)};
   const product=changes.go*changes.turn*changes.straight;
   if(Math.abs(product-1)>1e-12)throw Error('Exhibition factor conservation failed');
   return {lane:r.lane,course:r.course,
     source_metrics:sourceKeys,
     go_evidence:goObserved?'original_straight_segment':'not_separately_measured',
     turn_proxy:'turn_and_lap_or_half_lap',
     stretch_proxy:special?'normal_exhibition_only':'normal_exhibition_and_original_straight',
     relative_evidence:{go:goObserved?straight[i]:null,
       turn:turnSignal,straight:stretchSignal},
     multipliers:changes,
     geometric_mean_conserved:true,
     previous_total_movement:combined};
 });
 const applied=rows.some(row=>Object.values(row.multipliers)
   .some(mult=>Math.abs(mult-1)>1e-10));
 return {...empty,status:applied?'applied':'neutral_same_scores',applied,
   venue,source_metric_keys:sourceKeys,
   missing_optional_metrics:[
     ...(lap?[]:[lapKey]),...(straight?[]:['straight_time'])],
   source_exhibition_weight_unchanged:true,
   no_extra_stake:true,
   rows};
}
root.BoatThreeLegPrimary={evaluate,VERSION,MAX_LOG};
if(typeof module!=='undefined')module.exports=root.BoatThreeLegPrimary;
})(typeof window==='undefined'?globalThis:window);
