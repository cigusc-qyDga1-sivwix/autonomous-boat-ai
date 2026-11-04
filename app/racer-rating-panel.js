/* BOAT LAB six-racer overall summary.
 * Calculation remains in racer-rating.js; display only the two overall scores.
 * Source: saved pre-race data, no post-race outcomes or odds.
 */
(function(global){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shown=v=>v===null||v===undefined||!Number.isFinite(v)?'—':String(v);
function render(r){
 const rating=global.BoatRacerRating?.rate?.(r);
 if(!rating||!Array.isArray(rating.rows)||rating.rows.length!==6)
  return '<section class="card card-pad boat-overall-panel"><h2 class="section-title">📊 6艇の総合評価</h2><p>評価データを確認できません。</p></section>';
 const four=r?.model_version?.startsWith('four-factor-');
 const primary=rating.rows.every(x=>x.primary_aligned===true);
 const percent=v=>Number.isFinite(v)?(v*100).toFixed(1):'—';
 const scored=rating.rows.filter(x=>Number.isFinite(x.ability));
 const expected=rating.rows.filter(x=>Number.isFinite(x.race_expectation));
 const topAbility=scored.length===6?Math.max(...scored.map(x=>x.ability)):null;
 const topExpected=expected.length===6?Math.max(...expected.map(x=>x.race_expectation)):null;
 const names=items=>items.map(x=>x.lane+'号艇').join('・');
 const leaders=topAbility!==null&&topExpected!==null?
  (four?'選手基礎トップ：':'総合能力トップ：')+names(scored.filter(x=>x.ability===topAbility))+
  (primary?' ／ 正式メインの1着評価トップ：':' ／ このレースの活躍期待トップ：')+
  names(expected.filter(x=>x.race_expectation===topExpected)):
  (rating.status==='hold'?'展示進入確認待ちのため期待指数を保留':
   /^four-factor-v(?:1\.(?:8|9)|2\.[012])\b/.test(r?.model_version||'')?'旧保存予想に正式メインの着順別評価がないため表示保留':
   '未取得・進入未確認の項目は評価保留');
 const rows=rating.rows.map(x=>{
  const ability=shown(x.ability),expectation=shown(x.race_expectation);
  const bestAbility=topAbility!==null&&x.ability===topAbility;
  const bestExpected=topExpected!==null&&x.race_expectation===topExpected;
  return '<tr'+(bestExpected?' class="boat-overall-leading"':'')+'>'+
   '<th scope="row"><span class="boat-entry-lane boat-entry-'+x.lane+'">'+x.lane+'</span></th>'+
   '<td class="boat-overall-name">'+esc(x.name)+'</td>'+
   '<td class="boat-overall-score'+(bestAbility?' is-top':'')+'">'+ability+'</td>'+
   '<td class="boat-overall-score boat-overall-expect'+(bestExpected?' is-top':'')+'">'+expectation+'</td>'+
   (primary?'<td>'+['first','second','third'].map(k=>percent(x.role_weights?.[k])).join(' / ')+'</td>'+
     '<td>'+['first','second','third'].map(k=>shown(x.ticket_role_counts?.[k])).join(' / ')+'</td>':'')+
   '</tr>';
 }).join('');
 return '<section class="card card-pad boat-overall-panel" aria-label="6艇の総合能力とレース活躍期待指数">'+
  '<div class="boat-overall-heading"><h2 class="section-title">📊 6艇の総合評価</h2>'+
  '<span>0〜100点｜試験指数</span></div>'+
  '<div class="boat-entry-overflow"><table class="boat-overall-table"><thead>'+
  '<tr><th>艇</th><th>選手</th><th>'+(four?'選手基礎':'総合能力')+'</th><th>'+(primary?'メイン1着評価':'活躍期待')+'</th>'+
  (primary?'<th>モデル評価1/2/3着（％）</th><th>買い目採用1/2/3着（点）</th>':'')+'</tr>'+
  '</thead><tbody>'+rows+'</tbody></table></div>'+
  '<p class="boat-overall-leaders">'+esc(leaders)+'</p>'+
  '<p class="boat-overall-caveat">'+(four?'選手基礎は保存済みの選手実績のみを比較した指数。モーター・展示・気象は含めません。':'総合能力は選手・モーター・進入相性を合成。')+
  (primary?'メイン1着評価は正式予想と同じ120着順評価で最高値を100とした指数。モデル評価の1/2/3着は全120組の相対重みで、買い目採用点数は採択された3連単に各艇が何点登場するかを示します。<strong>相対重みと採用点数は必ずしも比例しません</strong>（1着の総重みが多くても、各3連単への分散が大きい場合があります）。':
  '活躍期待はこのレース内の相対評価で最高値を100とした指数。')+
  'いずれも<strong>未校正の試験値</strong>で、的中確率や舟券の金銭的期待値ではありません。過去の固定予想・買い目は変更しません。</p>'+
  '</section>';
}
global.BoatRacerRatingPanel={render};
})(typeof window!=='undefined'?window:globalThis);
