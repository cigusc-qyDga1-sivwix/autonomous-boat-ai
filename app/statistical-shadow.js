/* Published, immutable learned comparisons only. Never generates formal tickets. */
(function(root){
 'use strict';
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let cache=null,pending=null,loaded=0;
 function placeholder(){return '<section class="card card-pad" data-statistical-shadow><h3>統計学習モデルの比較予想</h3><p>発走前に固定した比較記録を確認中…</p></section>';}
 function panel(doc,r,day){
  const row=doc?.event_date===day?doc?.races?.[r.venue+'-'+r.race]:null;
  if(!row||row.source_sha256!==r.sha256)return '<h3>統計学習モデルの比較予想</h3><p>この保存時点に対応する比較予想は未取得です。</p>';
  if(!Array.isArray(row.bets)||row.bets.length<4||row.bets.length>12||
      !row.bets.every(b=>/^[1-6]-[1-6]-[1-6]$/.test(b.combination)&&new Set(b.combination.split('-')).size===3&&Number.isInteger(b.virtual_yen)&&b.virtual_yen>=1000&&b.virtual_yen%1000===0)||
      row.bets.reduce((n,b)=>n+b.virtual_yen,0)!==50000)return '<p>比較記録を検証できませんでした。</p>';
  return '<h3>統計学習モデルの比較予想</h3><p><strong>検証用・正式買い目とは別</strong>。1着・条件付き2着・条件付き3着の係数を過去データから学習し、全120通りを評価しています。確率は未校正です。</p><p>学習対象：'+esc(row.trained_through)+'まで／'+esc(row.training_n??'未記録')+'R。比較固定：'+esc(row.frozen_at_utc)+'</p><table class="bets-table"><thead><tr><th>比較買い目</th><th>仮想配分</th></tr></thead><tbody>'+row.bets.map(b=>'<tr><td>'+esc(b.combination)+'</td><td>'+b.virtual_yen.toLocaleString('ja-JP')+'円</td></tr>').join('')+'</tbody></table><p>同じ点数・合計5万円で比較。自動で正式予想へ昇格しません。</p>';
 }
 async function mount(container,r,day){
  const slot=container?.querySelector?.('[data-statistical-shadow]');if(!slot)return;
  try{
   if(!cache||Date.now()-loaded>60000){
    if(!pending)pending=fetch('./data/experiments/statistical-latest.json',{cache:'no-store'}).then(res=>{if(!res.ok)throw Error('missing');return res.json()}).then(x=>{cache=x;loaded=Date.now();return x}).finally(()=>{pending=null});
    await pending;
   }
   if(slot.isConnected!==false)slot.innerHTML=panel(cache,r,day);
  }catch{if(slot.isConnected!==false)slot.innerHTML='<h3>統計学習モデルの比較予想</h3><p>比較記録は現在取得できません。</p>';}
 }
 root.BoatStatisticalShadow={placeholder,panel,mount};
 if(typeof module!=='undefined')module.exports=root.BoatStatisticalShadow;
})(typeof window==='undefined'?globalThis:window);
