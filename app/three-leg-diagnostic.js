/* BOAT LAB: exhibition-only, read-only three-leg evidence panel.
 * Descriptive SIX-BOAT ranks, not engine measurement, calibrated probability
 * or inputs to the formal v2.3 selection. Missing ≠ bad. No result/odds.
 * BOATRACE: https://www.boatrace.jp/owpc/pc/site/news/2025/07/44414/
 * Fukuoka: https://www.boatrace.jp/owsp/sp/extra/race/22_20161025/monthly/tenji_time.html
 * Hamanako: https://www.boatrace.jp/owpc/pc/extra/race/06_20180919/monthly/data.html
 */
(function(root){
'use strict';
const RANGES=Object.freeze({
 exhibition_time:[5,10],lap_time:[30,50],half_lap_time:[15,25],
 turn_time:[4,15],straight_time:[5,12]
});
const METRIC_NAMES=Object.freeze({
 exhibition_time:'展示タイム',lap_time:'一周',half_lap_time:'半周ラップ',
 turn_time:'まわり足',straight_time:'直線'
});
function expected(venue){
 if(venue==='江戸川')return ['exhibition_time'];
 if(venue==='桐生')return ['exhibition_time','half_lap_time','turn_time','straight_time'];
 if(['住之江','尼崎','徳山'].includes(venue))return ['exhibition_time','lap_time','turn_time'];
 return ['exhibition_time','lap_time','turn_time','straight_time'];
}
function rank(values,i){
 // 1 = top, 6 = bottom, tied lanes receive the shared midrank.
 const value=values[i],before=values.filter(x=>x<value-.005).length;
 const ties=values.filter(x=>Math.abs(x-value)<=.005).length;
 return 1+before+(ties-1)/2;
}
function evidence(racers,expectedKeys){
 const values={};
 for(const key of expectedKeys){
   const [min,max]=RANGES[key];
   const list=racers.map(r=>key==='exhibition_time'?r.exhibition_time:r.original_exhibition?.[key]);
   if(list.every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=min&&x<=max)){
     values[key]=list;
   }
 }
 return values;
}
function classification(ranks){
 if(!ranks.length)return {status:'判定保留',level:'none'};
 const worst=Math.max(...ranks),best=Math.min(...ranks);
 if(worst-best>2.5)return {status:'指標不一致',level:'conflict'};
 const avg=ranks.reduce((s,x)=>s+x,0)/ranks.length;
 return avg<=2.25?{status:'上位傾向',level:'above'}:
  avg>=4.75?{status:'下位傾向',level:'below'}:
  {status:'中位・拮抗',level:'neutral'};
}
function examine(venue,complete,types,i){
 const chosen=types.filter(key=>complete[key]);
 const ranks=chosen.map(key=>rank(complete[key],i));
 const status=classification(ranks);
 return {status:status.status,level:status.level,
   measured_keys:chosen,
   ranks:chosen.map((key,j)=>({key,rank:ranks[j]})),
   // This confidence is qualitative EVIDENCE COVERAGE, not probability.
   evidence_level:chosen.length>=2&&status.level!=='conflict'?'中':
                  chosen.length?'低':'判定不可'};
}
function evaluate(input){
 if(!input||input.phase!=='exhibition'||input.ticket_status!=='formal')
   return {version:'three-leg-exhibition-diagnostic-v0.1',status:'not_verified'};
 const racers=Array.isArray(input.racers)?[...input.racers].sort((a,b)=>a.lane-b.lane):[];
 if(racers.length!==6||racers.some((r,i)=>r.lane!==i+1))
   return {version:'three-leg-exhibition-diagnostic-v0.1',status:'invalid_six_boats'};
 const venue=input.venue||'';
 const measured=expected(venue),values=evidence(racers,measured);
 const specialIntermediate=venue==='浜名湖'||venue==='福岡';
 const stretchKeys=['exhibition_time'];
 // Hamamako/Fukuoka original straight measures more of turn-exit / middle leg.
 if(!specialIntermediate)stretchKeys.push('straight_time');
 const launchKeys=specialIntermediate?['straight_time']:[];
 const turnLap=venue==='桐生'?'half_lap_time':'lap_time';
 const pickupKeys=['turn_time',turnLap];
 const rows=racers.map((r,i)=>{
   const stretch=examine(venue,values,stretchKeys,i);
   const launch=examine(venue,values,launchKeys,i);
   const pickup=examine(venue,values,pickupKeys,i);
   // Turn and whole/half lap include steering skill, so cannot prove engine
   // turn-exit acceleration. Stop at low-confidence indirect observation.
   pickup.evidence_level=pickup.measured_keys.length?'低':'判定不可';
   // Quantitative independent launch readings are verified only at these
   // two venues. Else MUST say video needed, not infer from exhibition ST.
   launch.evidence_level=launch.measured_keys.length?'低':'判定不可';
   if(venue==='福岡'&&stretch.measured_keys.length)
     stretch.evidence_level='低'; // Fukuoka official 150m segment is different.
   return {lane:r.lane,course:r.course,
     pickup,launch,stretch};
 });
 return {
   version:'three-leg-exhibition-diagnostic-v0.1',status:'ready',
   model_role:'read_only_research',not_formal:true,
   calibrated:false,result_data_used:false,
   venue,expected_metrics:measured,
   complete_six_boat_metrics:Object.keys(values),
   missing_expected_metrics:measured.filter(key=>!values[key]),
   venue_measurement_note:venue==='福岡'?
      '展示タイムの計測位置が他場と異なる。直線はターン後の中間足・行き足の参考。':
      venue==='浜名湖'?
      'オリジナル直線は前半の出足・行き足の参考。展示タイムは後半の伸び。':
      '行き足の独立測定値は未確認。スタート展示映像が必要。',
   limitations:'出足は旋回/周回からの間接推定。行き足は特定場以外未診断。展示STは選手のタイミングを含むため機力の独立指標にしない。引き波/航路/操舵差は未補正。順位は的中確率ではない。',
   rows
 };
}
const escape=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
function panel(input){
 const d=evaluate(input);
 if(d.status!=='ready')return '';
 const render=x=>escape(x.status)+' <span class="help">('+escape(x.evidence_level)+')</span>';
 return '<section class="card card-pad"><h3>3種類の足・展示数値診断（研究用）</h3>'+
   '<p class="help">同一レース6艇のタイム順位による相対判定。出足・行き足・伸びの実測値でも、的中確率でもありません。</p>'+
   '<div class="boat-entry-overflow"><table class="bets-table"><thead><tr><th>艇</th>'+
   '<th>出足系（回り・周回）</th><th>行き足</th><th>伸び</th></tr></thead><tbody>'+
   d.rows.map(x=>'<tr><td>'+escape(x.lane)+'</td><td>'+render(x.pickup)+
     '</td><td>'+render(x.launch)+'</td><td>'+render(x.stretch)+'</td></tr>').join('')+
   '</tbody></table></div>'+
   '<p class="help">使用できた6艇完備データ：'+
     escape(d.complete_six_boat_metrics.map(x=>METRIC_NAMES[x]).join('・')||'なし')+
   '／欠測：'+escape(d.missing_expected_metrics.map(x=>METRIC_NAMES[x]).join('・')||'なし')+'</p>'+
   '<p class="help">'+escape(d.venue_measurement_note)+'</p>'+
   '<p class="help">'+escape(d.limitations)+'</p>'+
   '<p class="help"><strong>正式予想・正式収支は変更しません。</strong> 実映像の伸び・ターン出口加速が検証されるまで断定しません。</p></section>';
}
root.BoatThreeLegDiagnostic={evaluate,panel,expected};
if(typeof module!=='undefined')module.exports=root.BoatThreeLegDiagnostic;
})(typeof window==='undefined'?globalThis:window);
