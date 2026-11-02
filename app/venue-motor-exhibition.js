/* BOAT LAB: 23-venue motor x exhibition interaction. Shadow only.
 * Descriptive venue hypotheses, not fitted effects or predicted probabilities.
 * All metrics are pre-cutoff; no odds, result, payout, actual race ST or video.
 * Normal exhibition time is a straight-line indicator, NOT an automatic head pick.
 * 江戸川 excluded by user scope. Missing/partial 6-boat metrics are neutral.
 * https://www.boatrace.jp/owsp/sp/site/news/2025/07/44414/
 */
(function(root){
'use strict';
// Venue-specific (launch, turn, stretch) priorities are pre-registered trial
// hypotheses, not empirically calibrated effect sizes or course win rates.
const FOCUS=Object.freeze({
 '桐生':[1.30,0.90,0.90],'戸田':[1.25,1.15,0.90],
 '江戸川':null,'平和島':[1.15,1.15,1.00],
 '多摩川':[0.90,1.20,1.10],'浜名湖':[1.10,0.90,1.20],
 '蒲郡':[1.00,1.10,1.20],'常滑':[1.05,1.00,1.25],
 '津':[1.15,1.20,0.90],'三国':[1.25,1.10,0.90],
 'びわこ':[1.15,1.20,0.95],'住之江':[0.95,1.30,1.05],
 '尼崎':[0.95,1.30,1.00],'鳴門':[1.25,1.15,0.90],
 '丸亀':[1.05,1.20,1.10],'児島':[1.00,1.05,1.30],
 '宮島':[1.00,1.25,1.10],'徳山':[1.05,1.25,1.00],
 '下関':[1.10,1.25,0.95],'若松':[1.00,1.15,1.25],
 '芦屋':[1.00,1.25,1.05],'福岡':[1.30,1.10,0.90],
 '唐津':[1.20,1.00,1.10],'大村':[1.10,1.25,0.95]
});
const METRICS=Object.freeze({
 exhibition_time:{min:5,max:10,scale:.30},
 lap_time:{min:30,max:50,scale:2.0},
 turn_time:{min:4,max:15,scale:.8},
 straight_time:{min:5,max:12,scale:.5}
});
const MIX=Object.freeze({
 go:{exhibition_time:.55,lap_time:.45},
 turn:{turn_time:.80,lap_time:.20},
 straight:{straight_time:.75,exhibition_time:.25}
});
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
const valid=(v,lo,hi)=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
function evaluate(input){
 const venue=input?.venue,profile=input?.venue_profile;
 const racers=Array.isArray(input?.racers)?[...input.racers].sort((a,b)=>a.lane-b.lane):[];
 if(racers.length!==6||racers.some((r,i)=>r.lane!==i+1)||
   new Set(racers.map(r=>r.course)).size!==6||
   racers.some(r=>!Number.isInteger(r.course)||r.course<1||r.course>6))
   throw Error('motor/exhibition shadow requires six unique actual entry courses');
 const excluded=venue==='江戸川';
 const documented=Object.prototype.hasOwnProperty.call(FOCUS,venue);
 const eligible=!!(documented&&!excluded&&FOCUS[venue]&&profile&&
   profile.name===venue&&profile.code!=='03'&&input.phase==='exhibition');
 const motorValues=racers.map(r=>r.motor_top_2_percent);
 const motorComplete=motorValues.every(n=>valid(n,0.001,100));
 const means={};
 const arrays={};
 for(const [key,rule] of Object.entries(METRICS)){
   const values=racers.map(r=>key==='exhibition_time'?r.exhibition_time:r.original_exhibition?.[key]);
   if(values.every(n=>valid(n,rule.min,rule.max))){
     arrays[key]=values;
     means[key]=values.reduce((sum,n)=>sum+n,0)/6;
   }
 }
 const completeMetrics=Object.keys(arrays);
 const active=!!(eligible&&motorComplete&&completeMetrics.length);
 const motorMean=motorComplete?motorValues.reduce((sum,n)=>sum+n,0)/6:null;
 // Nearby forecast wind only flattens a hypothesis; it is NOT a surface
 // observation, wind bearing, tide direction or an assumed attack advantage.
 const wind=input.weather_used?.wind_speed;
 const caution=valid(wind,5,65);
 const scale=caution?.65:1;
 const rows=racers.map((r,i)=>{
   const motorEdge=motorComplete?clamp((motorValues[i]-motorMean)/25,-1,1):null;
   const metricEdges={};
   const agreement={};
   for(const key of completeMetrics){
     const rule=METRICS[key];
     const e=clamp((means[key]-arrays[key][i])/rule.scale,-1,1);
     metricEdges[key]=+e.toFixed(4);
     // Reward only jointly strong motor + observed metric; penalize jointly
     // weak. Opposing signals -> no added effect, explicitly unconfirmed.
     agreement[key]=motorEdge>0&&e>0?Math.min(motorEdge,e):
       motorEdge<0&&e<0?-Math.min(-motorEdge,-e):0;
   }
   const adjustment={go:1,turn:1,straight:1,overall:1};
   if(active){
     const priorities=FOCUS[venue];
     ['go','turn','straight'].forEach((stage,j)=>{
       // Missing components do NOT receive reallocated weights.
       const signal=Object.entries(MIX[stage]).reduce((sum,[key,w])=>
         sum+(agreement[key]||0)*w,0);
       const log=clamp(.028*priorities[j]*signal*scale,-.035,.035);
       adjustment[stage]=+Math.exp(log).toFixed(6);
     });
     adjustment.overall=+Math.exp((
       Math.log(adjustment.go)+Math.log(adjustment.turn)+
       Math.log(adjustment.straight))/3).toFixed(6);
   }
   return {lane:r.lane,course:r.course,
     motor_top2_pct:motorComplete?motorValues[i]:null,
     motor_relative:motorEdge===null?null:+motorEdge.toFixed(4),
     metric_edges:metricEdges,
     observed_agreement:Object.fromEntries(Object.entries(agreement).map(([k,v])=>[k,+v.toFixed(4)])),
     multipliers:adjustment};
 });
 return {
   version:'venue-motor-exhibition-shadow-v0.1',venue,excluded,
   eligible,applied:active&&rows.some(r=>Object.values(r.multipliers).some(m=>m!==1)),
   status:active?'ready':excluded?'excluded':!eligible?'not_eligible':!motorComplete?'motor_missing':'exhibition_metrics_incomplete',
   model_role:'shadow_validation',calibrated:false,pre_cutoff_only:true,result_data_used:false,
   venue_focus:FOCUS[venue]?{go:FOCUS[venue][0],turn:FOCUS[venue][1],straight:FOCUS[venue][2]}:null,
   metric_coverage:completeMetrics,
   metric_coverage_count:completeMetrics.length,
   six_boat_motor_complete:motorComplete,
   wind_caution_from_nearby_forecast:caution,
   tide_unobserved:!!profile?.tide_sensitive,
   motor_history_maintenance_unavailable:true,
   source_notes:'motor top-2 rates / exhibition supplied through existing pre-cutoff validated race feed; no verified motor sample size, replacement, repair, tide or measured water flow',
   claim:'Relative 6-boat concordance trial only; no independent proof, no calibrated probabilities',
   rows
 };
}
root.BoatVenueMotorExhibition={evaluate,FOCUS,METRICS};
if(typeof module!=='undefined')module.exports=root.BoatVenueMotorExhibition;
})(typeof window==='undefined'?globalThis:window);
