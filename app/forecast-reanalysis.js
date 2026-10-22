/* Experimental scenario recalculation, separate from immutable pre-cutoff bets.
 * ONLY existing BOAT LAB records and optionally licensed independently-entered observations.
 * NO BOATERS scraping. No use of results or payouts in forecast computation.
 */
(function(){
'use strict';
const STAKES=[12000,10000,8000,6000,5000,4000,3000,2000], COURSE=[1.78,1.27,1.06,.91,.79,.71];
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
 const selected=all.slice(0,8),heads=new Set(selected.map(x=>x.head));
 if(heads.size===1){
  const alternative=[...weights].map((w,i)=>({head:i+1,w})).sort((a,b)=>b.w-a.w).find(x=>!heads.has(x.head));
  const best=alternative&&all.find(x=>x.head===alternative.head);
  if(best)selected[7]=best;
 }
 selected.sort((a,b)=>b.weight-a.weight||a.combination.localeCompare(b.combination));
 const bets=selected.map((x,i)=>({combination:x.combination,virtual_yen:STAKES[i]}));
 const lead=bets[0].combination.split('-').map(Number);
 const hc=Number(racers[lead[0]-1].course)||lead[0];
 const scenario=hc===1?'①を中心とする先マイ・押し切り仮説':hc===2?'②の差し・早仕掛け仮説':hc<=4?'センター勢のまくり・まくり差し仮説':'外枠からの仕掛け・展開突入仮説';
 return {model_version:'conditional-heuristic-experimental-0.1',bets,
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
 let out='<div class="recalc-result"><div class="recalc-result-heading"><b>🧠 展開を再評価した3連単8点</b><span>'+(afterCutoff?'締切後の参考試算':'発走前の参考試算')+'</span></div>';
 out+='<p class="recalc-scenario">'+esc(result.scenario)+'</p><p class="recalc-pair">'+esc(result.pair)+'</p>';
 out+='<p class="recalc-used"><b>使用した追加情報：</b>'+esc(result.used.join('・')||'なし（出走表のみ）')+'</p>';
 if(result.skipped.length)out+='<p class="recalc-alert">'+result.skipped.map(esc).join(' ／ ')+'</p>';
 out+='<table class="recalc-bets"><thead><tr><th>仮説</th><th>3連単</th><th>仮想金額</th></tr></thead><tbody>';
 for(let i=0;i<result.bets.length;i++){const b=result.bets[i];out+='<tr><td>'+(i<3?'本線':i<6?'対抗':'展開穴')+'</td><td>'+esc(b.combination)+'</td><td>'+b.virtual_yen.toLocaleString('ja-JP')+'円</td></tr>';}
 out+='</tbody></table><div class="recalc-total">仮想合計 <strong>50,000円</strong>（8点・試験値）</div>';
 out+='<div class="notice warn">'+(afterCutoff?'締切後の事後シミュレーションで、発走前の正式予想・成績に加えません。':'端末内の参考試算であり、発走前の正式予想には加えません。')+' '+esc(result.method)+'</div></div>';
 return out;
}
window.BoatReanalysis={model,normalizeExtra,inputForm,resultHTML};
})();
