/* Four-factor base multipliers. Nominal log weights, NOT calibrated probabilities.
 * No fetches/results/odds. Missing measurements contribute neutral multiplier 1.
 */
(function(root){
'use strict';
const WEIGHTS=Object.freeze({athlete:.60,motor:.25,exhibition:.10,weather:.05});
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const val=(x,a,b)=>typeof x==='number'&&Number.isFinite(x)&&x>=a&&x<=b?x:null;
function relative(xs,scale,complete=false){
 const good=xs.filter(x=>x!==null);
 if(good.length<2||(complete&&good.length!==6))return xs.map(()=>0);
 const mean=good.reduce((a,b)=>a+b,0)/good.length;
 return xs.map(x=>x===null?0:clamp((x-mean)/scale,-1,1));
}
function evaluate(input){
 const rs=[...input.racers].sort((a,b)=>a.lane-b.lane);
 if(rs.length!==6||rs.some((r,i)=>r.lane!==i+1)||new Set(rs.map(r=>r.course)).size!==6||rs.some(r=>!Number.isInteger(r.course)||r.course<1||r.course>6))throw Error('Six unique actual courses required');
 const contexts=rs.map(r=>r.racer_context?.values||{});
 const win=rs.map(r=>val(r.national_win_rate,0,10));
 const top3=contexts.map(c=>val(c.national_top3,0,100));
 const local=contexts.map(c=>{const n=val(c.local_win,0,10);return n>0?n:null;});
 const frame=rs.map((r,i)=>r.course===r.lane&&win[i]!==null?(()=>{const n=val(contexts[i].frame_win,0,10);return n>0?n-win[i]:null;})():null);
 const avg=rs.map((r,i)=>{
  const a=val(r.average_start_timing,.01,.4),f=r.course===r.lane?val(contexts[i].frame_st,.01,.4):null;
  return a===null?f:f===null?a:.8*a+.2*f;
 });
 const mot2=rs.map(r=>val(r.motor_top_2_percent,0,100));
 const mot3=contexts.map(c=>val(c.motor_top3,0,100));
 const expo=input.phase==='exhibition';
 const et=rs.map(r=>expo?val(r.exhibition_time,5,10):null);
 const es=rs.map(r=>expo?val(r.exhibition_st,0,.5):null);
 const turn=rs.map(r=>expo?val(r.original_exhibition?.turn_time,4,15):null);
 const straight=rs.map(r=>expo?val(r.original_exhibition?.straight_time,5,12):null);
 const lap=rs.map(r=>expo?val(r.original_exhibition?.lap_time,30,50):null);
 const w=relative(win,2),t=relative(top3,30),l=relative(local,2),f=relative(frame,2),s=relative(avg,.06);
 const m=relative(mot2,25),m3=relative(mot3,25);
 const e=relative(et,.30,true),st=relative(es,.12),tr=relative(turn,.8,true),sr=relative(straight,.5,true),lp=relative(lap,2,true);
 const wind=val(input.weather_used?.wind_speed,0,65),wave=val(input.weather_used?.wave_height,0,100),gust=val(input.weather_used?.wind_gust,0,100);
 const rough=clamp(Math.max(wind===null?0:(wind-4)/6,wave===null?0:(wave-3)/12,gust===null?0:(gust-8)/12),0,1);
 const rows=rs.map((r,i)=>{
  const athlete=clamp(.40*w[i]+.20*t[i]+.10*l[i]-.15*s[i]+.15*f[i],-.8,.8);
  const motor=clamp(.80*m[i]+.20*m3[i],-.8,.8);
  const exhibition=expo?clamp(-.45*e[i]-.25*st[i]-.15*tr[i]-.10*sr[i]-.05*lp[i],-1,1):0;
  const base=WEIGHTS.athlete*athlete+WEIGHTS.motor*motor+WEIGHTS.exhibition*exhibition;
  // Shared weather must not multiply all boats equally and cancel. Roughness
  // conservatively flattens the base evaluation; no unverified wind direction bias.
  const weather=-rough*clamp(base/.60,-1,1);
  const logs={athlete,motor,exhibition,weather};
  const factors=Object.fromEntries(Object.entries(logs).map(([k,v])=>[k,{raw_multiplier:Math.exp(v),applied_multiplier:Math.exp(WEIGHTS[k]*v)}]));
  const combined=Math.exp(base+WEIGHTS.weather*weather);
  return {lane:r.lane,course:r.course,factors,combined_multiplier:combined,
   average_st_used:avg[i],frame_context_used:r.course===r.lane&&frame[i]!==null,
   available:{national_win:win[i]!==null,national_top3:top3[i]!==null,local_win:local[i]!==null,frame:frame[i]!==null,
    average_st:avg[i]!==null,motor_top2:mot2[i]!==null,motor_top3:mot3[i]!==null,
    exhibition_time:expo&&et.every(x=>x!==null),exhibition_st:es[i]!==null,
    weather:wind!==null||wave!==null||gust!==null},
   exhibition_f_ignored:expo&&typeof r.exhibition_st==='number'&&r.exhibition_st<0};
 });
 return {version:'four-factor-v1.0-untrained',weights:WEIGHTS,rows,roughness:rough,
  formula:'athlete^0.60 * motor^0.25 * exhibition^0.10 * weather^0.05',
  scope:'Base movement multipliers feed actual-course conditional 1M/2M scenarios; not final attribution percentages.',
  missing_policy:'Missing fields remain unavailable and contribute multiplier 1. No results, payouts, or odds used.',
  weather_method:'Bounded roughness flattening only; no calibrated directional course effect',
  calibrated:false};
}
function panel(r){
 const meta=r?.four_factor;
 if(!meta||!Array.isArray(meta.rows)||meta.rows.length!==6)return '';
 const keys=['athlete','motor','exhibition','weather'],labels=['選手','モーター','展示','気象'];
 const show=x=>typeof x==='number'&&Number.isFinite(x)&&x>0&&x<10?'×'+x.toFixed(3):'未取得';
 const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const chasers=meta.chaser_policy?.second_by_head;
 const chaserHTML=Array.isArray(chasers)&&chasers.length===6?
  '<h3>頭ごとの2着候補</h3><p>隣艇の自動加点は使わず、残り5艇を毎回評価。3着も残り4艇から評価します。選手別の2・3着実績率は未接続です。</p><table class="bets-table"><thead><tr><th>1着の条件</th><th>2着候補（評価順）</th></tr></thead><tbody>'+chasers.map(h=>'<tr><td>'+esc(h.head_course)+'コース</td><td>'+[...h.candidates].sort((a,b)=>b.relative_share-a.relative_share||a.lane-b.lane).map(x=>esc(x.lane)+'号艇').join(' → ')+'</td></tr>').join('')+'</tbody></table>':'';
 const rows=meta.rows.map(x=>'<tr><td>'+esc(x.lane)+'</td>'+keys.map(k=>'<td>'+show(x.factors?.[k]?.applied_multiplier)+'</td>').join('')+'<td>'+show(x.combined_multiplier)+'</td></tr>').join('');
 return '<section class="card card-pad four-factor-panel"><h3>4要素の基礎評価</h3><p>選手60・モーター25・展示10・気象5</p><div class="boat-entry-overflow"><table class="bets-table"><thead><tr><th>艇</th>'+labels.map(x=>'<th>'+x+'</th>').join('')+'<th>合成</th></tr></thead><tbody>'+rows+'</tbody></table></div><p class="help">表示は重み適用後の倍率。欠損は中立の×1とし、取得値を捏造しません。この基礎評価と実進入・艇間連動から買い目を作ります。比率は試験設定で、的中確率や金銭的期待値ではありません。</p>'+chaserHTML+'</section>';
}
root.BoatFourFactor={evaluate,panel,WEIGHTS};
if(typeof module!=='undefined')module.exports=root.BoatFourFactor;
})(typeof window==='undefined'?globalThis:window);
