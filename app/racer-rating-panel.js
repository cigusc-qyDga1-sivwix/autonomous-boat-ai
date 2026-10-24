/* BOAT LAB 6-boat pre-race ability & expectation overview. Read-only. */
(function(global){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(r){
 const rating=global.BoatRacerRating?.rate?.(r);
 if(!rating||rating.rows?.length!==6)
  return '<section class="card card-pad"><h2>📊 6艇の総合能力・期待指数</h2><p>能力計算に必要なモジュールがありません。</p></section>';
 const shown=x=>x===null||x===undefined||!Number.isFinite(x)?'—':String(x);
 const pct=x=>x===null||x===undefined||!Number.isFinite(x)?'—':(x*100).toFixed(1)+'%';
 const cards=rating.rows.map(x=>{
  const parts=[['選手力',x.athlete,'player'],['モーター',x.motor,'motor'],['進入相性',x.course_fit,'course']];
  const bars=parts.map(([name,value,type])=>'<div class="boat-ability-part"><span>'+esc(name)+'</span>'+
   '<div class="boat-ability-track"><span class="boat-ability-fill boat-ability-'+type+
   '" style="width:'+(value===null?0:Math.max(0,Math.min(100,value)))+'%"></span></div>'+
   '<strong>'+shown(value)+'</strong></div>').join('');
  const z=x.role_weights;
  const roles=z?
   '<div class="boat-ability-roles"><span>1着 '+pct(z.first)+'</span>'+
   '<span>2着 '+pct(z.second)+'</span><span>3着 '+pct(z.third)+'</span></div>':
   '<div class="boat-ability-roles is-pending">着順期待：'+
    (rating.status==='hold'?'展示進入確認待ち':'計算不可')+'</div>';
  const caution=x.confidence==='insufficient'?'選手・モーター・進入の必須情報が不足':
    x.confidence==='partial_reference'?'一部のST・展示情報が未取得／暫定':'';
  return '<article class="boat-ability-card" aria-label="'+x.lane+'号艇 能力値と期待指数">'+
   '<div class="boat-ability-card-head"><span class="boat-entry-lane boat-entry-'+x.lane+'">'+x.lane+'</span>'+
   '<div class="boat-ability-card-name"><strong>'+esc(x.name)+'</strong>'+
    '<small>'+ (x.course_confirmed?x.course+'コース':'実進入未確認')+'</small></div>'+
   '<div class="boat-ability-values"><div><span>総合能力値</span><strong>'+shown(x.ability)+'</strong><small>/100</small></div>'+
   '<div class="boat-ability-expect"><span>活躍期待指数</span><strong>'+shown(x.race_expectation)+'</strong><small>/100</small></div></div></div>'+
   bars+roles+(caution?'<p class="boat-ability-uncertain">※ '+esc(caution)+'</p>':'')+'</article>';
 }).join('');
 return '<section class="card card-pad boat-ability-study" aria-label="6艇の総合能力とレース別活躍期待指数">'+
  '<div class="boat-ability-heading"><h2 class="section-title">📊 6艇の能力値とレース期待指数</h2>'+
  '<span>発走前保存データによる試験計算</span></div>'+
  '<div class="boat-ability-grid">'+cards+'</div>'+
  '<p class="boat-ability-explain"><strong>総合能力値（0〜100）：</strong>選手力45%・モーター30%・進入相性25%で合成。進入相性は実進入コース、隣艇との平均ST差、保存済み展示タイム・回り足から試算。本人の過去コース別実績そのものではありません。</p>'+
  '<p class="boat-ability-explain"><strong>活躍期待指数（0〜100）：</strong>レース内の1着・2着・3着の相対モデル重みを55:30:15で合成し、最上位艇=100に換算。1着・2着・3着の各数値は未校正のモデル配分で実測入着確率ではありません。オッズがないため舟券の金銭期待値とは異なります。</p>'+
  '<p class="boat-ability-explain">使用モデル：'+esc(rating.model||'評価保留')+'。'+
  (rating.provisional?'進入未確認のためコース相性・総合能力は保留。':'保存されたコース進入を使用。')+
  ' 欠損値は補完せず「—」で表示。結果・払戻・オッズを予測計算に含めず、正式固定の買い目・SHA・収支は変更しません。</p>'+
  '</section>';
}
global.BoatRacerRatingPanel={render};
})(typeof window!=='undefined'?window:globalThis);
