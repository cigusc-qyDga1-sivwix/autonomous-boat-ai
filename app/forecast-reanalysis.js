/* Experimental scenario recalculation, separate from immutable pre-cutoff bets.
 * ONLY existing BOAT LAB records and optionally licensed independently-entered observations.
 * NO BOATERS scraping. No use of results or payouts in forecast computation.
 */
(function(){
'use strict';
const COURSE=[1.78,1.27,1.06,.91,.79,.71];
const BUDGET_UNITS=50,MIN_POINTS=4,MAX_POINTS=12;
const METRICS=['lap_time','turn_time','straight_time'];
const LABEL={lap_time:'1周',turn_time:'回り足',straight_time:'直線'};
const LIMITS={lap_time:[30,50],turn_time:[4,15],straight_time:[5,12]};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>(v===null||v===undefined||v==='')?null:(Number.isFinite(Number(v))?Number(v):null);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
function normalizeExtra(extra){
 const out={};
 for(let lane=1;lane<=6;lane++){
  out[lane]={};
  for(const k of METRICS){
   const raw=extra?.[lane]?.[k];
   if(raw===null||raw===undefined||raw==='')continue;
   const v=num(raw);
   if(v===null||v<LIMITS[k][0]||v>LIMITS[k][1])throw Error(lane+'号艇の'+LABEL[k]+'は'+LIMITS[k][0]+'〜'+LIMITS[k][1]+'秒で入力してね');
   out[lane][k]=v;
  }
 }
 return out;
}
function pointCount(weights){
 if(!Array.isArray(weights)||weights.length!==6||weights.some(x=>!Number.isFinite(x)||x<=0))
  throw Error('6艇の相対評価が取得できません');
 const sorted=[...weights].sort((a,b)=>b-a),total=sorted.reduce((a,b)=>a+b,0);
 const share=sorted[0]/total,margin=(sorted[0]-sorted[1])/total;
 const thresholds=[[.40,.14,4],[.36,.10,5],[.33,.07,6],[.30,.05,7],
  [.28,.04,8],[.26,.025,9],[.245,.015,10],[.23,.010,11]];
 const found=thresholds.find(([min,lead])=>share>=min&&margin>=lead);
 const count=found?found[2]:MAX_POINTS;
 const label=count<=6?'主導権が比較的明確・買い目を集中':
  count<=9?'対抗ラインと2・3着の分岐を重視':'先頭争いが接近・展開分岐を広めに検証';
 return {count,share,margin,
  reason:label+'（頭評価の相対重み '+(share*100).toFixed(1)+'%・次点差 '+(margin*100).toFixed(1)+'%、未校正）'};
}
function allocateBets(selected){
 const count=selected.length;
 if(count<MIN_POINTS||count>MAX_POINTS)throw Error('買い目は4〜12点で作成');
 if(new Set(selected.map(x=>x.combination)).size!==count)throw Error('3連単が重複しています');
 const remaining=BUDGET_UNITS-count;
 const relative=selected.map(x=>Math.pow(Math.max(0,x.weight),.8));
 const total=relative.reduce((a,b)=>a+b,0);
 if(total<=0)throw Error('組合せの相対重みが不正です');
 const quotas=relative.map(x=>remaining*x/total);
 const amounts=quotas.map(x=>Math.floor(x));
 let leftover=remaining-amounts.reduce((a,b)=>a+b,0);
 const order=[...amounts.keys()].sort((a,b)=>
  ((quotas[b]-amounts[b])-(quotas[a]-amounts[a]))||(a-b));
 for(const i of order.slice(0,leftover))amounts[i]++;
 const bets=selected.map((x,i)=>({combination:x.combination,virtual_yen:1000*(1+amounts[i])}));
 if(bets.reduce((a,b)=>a+b.virtual_yen,0)!==50000)throw Error('仮想配分が50,000円になりません');
 return bets;
}
function model(r,rawExtra){
 if(!Array.isArray(r?.racers)||r.racers.length!==6)throw Error('6艇分の選手情報が揃っていないため再評価できません');
 const racers=[...r.racers].sort((a,b)=>Number(a.lane)-Number(b.lane));
 if(racers.some((x,i)=>Number(x.lane)!==i+1))throw Error('枠番の欠損・重複があります');
 const extras=normalizeExtra(rawExtra||{}),used=[],skipped=[],obs={};
 for(const metric of METRICS){
  const values=racers.map(x=>num(extras[x.lane]?.[metric]));
  if(values.every(v=>v!==null)){obs[metric]=values;used.push(LABEL[metric]+'タイム');}
  else if(values.some(v=>v!==null))skipped.push(LABEL[metric]+'は6艇分未入力なので補正なし');
 }
 const exhibition=racers.map(x=>num(x.exhibition_time));
 const exhibitionReady=exhibition.every(x=>x!==null&&x>=5&&x<=10);
 if(exhibitionReady)used.push('展示タイム');
 const exhibitionST=racers.map(x=>num(x.exhibition_st));
 const stReady=exhibitionST.every(x=>x!==null&&x>=0&&x<=.5);
 if(stReady)used.push('展示ST');
 else if(exhibitionST.some(x=>x!==null&&x<0))skipped.push('展示Fは通常のST加点に使用しない');
 const weights=racers.map((x,i)=>{
  const course=clamp(Math.round(num(x.course)??(i+1)),1,6);
  const win=clamp(num(x.national_win_rate)??4.5,0,10),motor=clamp(num(x.motor_top_2_percent)??30,0,100),avg=clamp(num(x.average_start_timing)??.17,0,.5);
  let w=COURSE[course-1]*clamp(1+.105*(win-4.5)+.003*(motor-30)-.65*(avg-.17),.58,1.7);
  if(exhibitionReady){const mean=exhibition.reduce((s,v)=>s+v,0)/6;w*=clamp(1+.64*(mean-exhibition[i]),.86,1.14);}
  if(stReady){const mean=exhibitionST.reduce((s,v)=>s+v,0)/6;w*=clamp(1+.23*(mean-exhibitionST[i]),.92,1.08);}
  for(const [metric,values] of Object.entries(obs)){
   const mean=values.reduce((s,v)=>s+v,0)/6,rate=metric==='lap_time'?.09:metric==='turn_time'?.14:.12;
   w*=clamp(1+rate*(mean-values[i]),.83,1.17);
  }
  return clamp(w,.06,6);
 });
 function factor(a,b,rank,second){
  const c1=Number(a.course)||Number(a.lane),c2=Number(b.course)||Number(b.lane);
  let f=1;
  if(rank===2){
   if(c1===1&&c2===2)f*=1.12;
   if(c1>=3&&c2===1)f*=1.11;
   if(c1>=3&&c2===2)f*=1.04;
   if(Math.abs(c1-c2)===1)f*=1.04;
  }else{
   const cs=Number(second.course)||Number(second.lane);
   if(c2===1&&c1!==1&&cs!==1)f*=1.13;
   if(c2===2&&c1===1)f*=1.08;
   if(c2===cs+1)f*=1.07;
   if(c1>=4&&c2===3)f*=1.05;
  }
  return f;
 }
 const all=[],sum=weights.reduce((a,b)=>a+b,0);
 for(let a=0;a<6;a++)for(let b=0;b<6;b++)if(b!==a)for(let c=0;c<6;c++)if(c!==a&&c!==b){
  const x2=weights.map((w,i)=>i===a?0:w*factor(racers[a],racers[i],2));
  const x3=weights.map((w,i)=>i===a||i===b?0:w*factor(racers[a],racers[i],3,racers[b]));
  all.push({combination:(a+1)+'-'+(b+1)+'-'+(c+1),head:a+1,weight:(weights[a]/sum)*(x2[b]/x2.reduce((s,v)=>s+v,0))*(x3[c]/x3.reduce((s,v)=>s+v,0))});
 }
 all.sort((a,b)=>b.weight-a.weight||a.combination.localeCompare(b.combination));
 const sizing=pointCount(weights);
 const selected=all.slice(0,sizing.count),heads=new Set(selected.map(x=>x.head));
 if(heads.size===1){
  const alternative=[...weights].map((w,i)=>({head:i+1,w})).sort((a,b)=>b.w-a.w).find(x=>!heads.has(x.head));
  const best=alternative&&all.find(x=>x.head===alternative.head);
  if(best && alternative.w >= .62*Math.max(...weights))selected[selected.length-1]=best;
 }
 selected.sort((a,b)=>b.weight-a.weight||a.combination.localeCompare(b.combination));
 const bets=allocateBets(selected);
 const lead=bets[0].combination.split('-').map(Number);
 const hc=Number(racers[lead[0]-1].course)||lead[0];
 const scenario=hc===1?'①を中心とする先マイ・押し切り仮説':hc===2?'②の差し・早仕掛け仮説':hc<=4?'センター勢のまくり・まくり差し仮説':'外枠からの仕掛け・展開突入仮説';
 return {model_version:'conditional-heuristic-experimental-0.2-flex4to12',bets,
  point_count:sizing.count,point_reason:sizing.reason,
  scenario,pair:lead[0]+'→'+lead[1]+'→'+lead[2]+' を中心に3着残存を評価',
  used,skipped,extras,method:'未訓練・未校正の条件付き重みモデル。展示動画・オッズ・結果情報は不使用。'};
}
function inputForm(r,extra){
 if(!Array.isArray(r?.racers)||r.racers.length!==6)return '<div class="notice warn">6艇分の選手情報が足りないため再評価できません。</div>';
 const fields=[['lap_time','1周'],['turn_time','回り足'],['straight_time','直線']];
 let out='<div class="recalc-form"><div class="recalc-form-head"><strong>追加展示データ（任意）</strong><span>6艇分そろった項目のみ使用</span></div>';
 out+='<div class="recalc-form-scroll"><table class="recalc-data-table"><thead><tr><th>艇</th>';
 for(const [key,name] of fields)out+='<th>'+name+'</th>';
 out+='</tr></thead><tbody>';
 for(let i=1;i<=6;i++){
  out+='<tr><th>'+i+'号艇</th>';
  for(const [key,name] of fields){
   const value=extra?.[i]?.[key];
   out+='<td><input type="number" inputmode="decimal" min="'+LIMITS[key][0]+'" max="'+LIMITS[key][1]+'" step=".01" placeholder="—" aria-label="'+i+'号艇'+name+'" data-recalc-lane="'+i+'" data-recalc-metric="'+key+'" value="'+(value==null?'':esc(value))+'"></td>';
  }
  out+='</tr>';
 }
 out+='</tbody></table></div><p>追加値は利用条件を確認した競艇場公式等、<strong>使用許可のある独立したデータ元</strong>からのみ入力してください。BOATERSの自動取得・転記を行う機能ではありません。</p></div>';
 return out;
}
function resultHTML(result,afterCutoff){
 let out='<div class="recalc-result"><div class="recalc-result-heading"><b>🧠 展開を再評価した3連単'+result.bets.length+'点</b><span>'+(afterCutoff?'締切後の参考試算':'発走前の参考試算')+'</span></div>';
 out+='<p class="recalc-scenario">'+esc(result.scenario)+'</p><p class="recalc-pair">'+esc(result.pair)+'</p>';
 out+='<p class="recalc-used"><b>点数選定：</b>'+esc(result.point_reason||'未記録')+'</p>';
 out+='<p class="recalc-used"><b>使用した追加情報：</b>'+esc(result.used.join('・')||'なし（出走表のみ）')+'</p>';
 if(result.skipped.length)out+='<p class="recalc-alert">'+result.skipped.map(esc).join(' ／ ')+'</p>';
 out+='<table class="recalc-bets"><thead><tr><th>仮説</th><th>3連単</th><th>仮想金額</th></tr></thead><tbody>';
 for(let i=0;i<result.bets.length;i++){const b=result.bets[i];out+='<tr><td>'+(i<3?'本線':i<6?'対抗':'展開穴')+'</td><td>'+esc(b.combination)+'</td><td>'+b.virtual_yen.toLocaleString('ja-JP')+'円</td></tr>';}
 out+='</tbody></table><div class="recalc-total">仮想合計 <strong>50,000円</strong>（'+result.bets.length+'点・試験値）</div>';
 out+='<div class="notice warn">'+(afterCutoff?'締切後の事後シミュレーションで、発走前の正式予想・成績に加えません。':'端末内の参考試算であり、発走前の正式予想には加えません。')+' '+esc(result.method)+'</div></div>';
 return out;
}
window.BoatReanalysis={model,pointCount,allocateBets,normalizeExtra,inputForm,resultHTML};
})();
