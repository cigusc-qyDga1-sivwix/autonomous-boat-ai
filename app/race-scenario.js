/* Read-only race scenario viewer. No outcome data, no forecast mutation. */
(function(root){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const valid=s=>typeof s==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(s)&&new Set(s.split('-')).size===3;
function pathway(head,second){
 if(head===1)return {title:'イン先マイ・逃げ残り仮説',phase:'①が先マイを確保',risk:'進入変化・出遅れ・センター攻撃で崩れる可能性'};
 if(head===2)return {title:'差し抜け仮説',phase:'②が①のターンの内側を狙う',risk:'①の旋回が小さく差し場が閉じる可能性'};
 if(head===3)return {title:'センター攻撃仮説',phase:'③がまくり／まくり差しの進路を探る',risk:'内艇の抵抗・外艇との競り合い'};
 return {title:'ダッシュ・外攻め仮説',phase:head+'号艇がスタート優位と攻めの進路を狙う',risk:'内艇の抵抗や攻め不発、後続への展開利'};
}
function analyze(r){
 const rows=(Array.isArray(r?.bets)?r.bets:[]).filter(b=>valid(b.combination)).map(b=>({...b,lanes:b.combination.split('-').map(Number)}));
 const groups=new Map();
 rows.forEach(b=>{let h=b.lanes[0];if(!groups.has(h))groups.set(h,[]);groups.get(h).push(b);});
 const scenarios=[...groups].map(([head,bets])=>{
  const seconds=[...new Set(bets.map(b=>b.lanes[1]))],thirds=[...new Set(bets.map(b=>b.lanes[2]))];
  return {head,bets,seconds,thirds,...pathway(head,seconds[0])};
 });
 const racers=Array.isArray(r?.racers)?r.racers:[];
 const complete=racers.length===6&&new Set(racers.map(x=>Number(x.lane))).size===6;
 return {scenarios,complete,phase:r?.phase||'unknown',sha:r?.sha256||'',model:r?.model_version||'未記録'};
}
function render(r){
 const info=analyze(r);
 const scenario=esc(r?.scenario||'勝ち筋の説明なし');
 const items=info.scenarios.map((s,i)=>`<details class="scenario-path" ${i===0?'open':''}><summary><span class="scenario-lane">${s.head}</span><strong>${esc(s.title)}</strong><small>${s.bets.length}点・固定買い目由来</small></summary>
 <div class="scenario-stages"><div><b>スタート〜1M</b><p>${esc(s.phase)}</p></div><div><b>2着候補</b><p>${s.seconds.map(v=>v+'号艇').join(' / ')}</p></div><div><b>3着残存</b><p>${s.thirds.map(v=>v+'号艇').join(' / ')}</p></div></div>
 <p class="scenario-risk"><b>崩れる条件：</b>${esc(s.risk)}</p><p class="scenario-combos">対応する保存済み買い目：${s.bets.map(b=>esc(b.combination)).join(' ・ ')}</p></details>`).join('');
 const status=info.complete?'出走表6艇確認':'6艇の出走表が揃っていない';
 const exhibit=info.phase==='exhibition'?'展示反映として保存された予想':'展示前または展示状態未確認の保存予想';
 return `<section class="card card-pad scenario-panel" aria-label="研究用予想展開"><div class="scenario-title"><div><span class="scenario-kicker">RACE SCENARIO · READ ONLY</span><h2>🚤 予想展開・6艇の攻防</h2></div><span class="scenario-tag">研究表示 / 買い目不変</span></div>
 <p>保存済みの買い目を、1着の勝ち筋 → 2着の浮上 → 3着の残存条件として読み解きます。<strong>独立した展開予測や実測映像ではありません。</strong></p>
 <div class="scenario-meta"><span>${esc(status)}</span><span>${esc(exhibit)}</span><span>モデル：${esc(info.model)}</span></div>
 <div class="scenario-thesis"><b>保存時の中心シナリオ</b><p>${scenario}</p></div>
 ${items||'<p class="scenario-empty">表示可能な保存済み3連単がありません。予想展開は未判定です。</p>'}
 <p class="scenario-disclaimer">※ 進路・攻撃方法は艇番から作った説明用の仮説です。スタート優位、まくり成功、艇間距離、引き波、実際の決まり手を確認したものではありません。結果・払戻を参照せず、正式予想・SHA・資金・収支に一切反映しません。</p></section>`;
}
root.BoatRaceScenario={analyze,render};
if(typeof module==='object'&&module.exports)module.exports={analyze,render};
})(typeof window!=='undefined'?window:globalThis);
