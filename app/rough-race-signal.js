/* Post-exhibition rough-race warning: display only, never an odds/ROI claim.
 * Consumes immutable pre-cutoff diagnostics; never reads results or payouts.
 */
(function(root){
  'use strict';
  const CLOSE_HEADS=new Set(['STRONG_FIELD_CLOSE_HEADS','MODEL_CLOSE_HEADS_NOT_STRONG_FIELD']);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pathLabels={OUTER_ATTACK_FOLLOWER:'外攻め→追走',OUTER_ATTACK_INSIDE_SURVIVES:'外攻め→イン残り',ATTACK_OVERRUN_INNER_COUNTER:'攻め流れ→内の逆転'};
  function assess(r,context={}){
    if(!r||context.mode!=='auto-live'||context.formal!==true||
      r.model_role!=='main'||r.classification==='SKIP'||
      r.phase!=='exhibition'||r.entry_exhibition_gate?.final_eligible!==true||
      r.exhibition_input_check?.verified_before_freeze!==true||
      !/^[a-f0-9]{64}$/i.test(String(r.sha256||'')))return null;
    if(!/^20\d{2}-\d{2}-\d{2}$/.test(String(context.event_date||''))||
      !/^([01]\d|2[0-3]):[0-5]\d$/.test(String(r.cutoff_jst||'')))return null;
    const frozen=Date.parse(r.frozen_at_utc||'');
    const cutoff=Date.parse(context.event_date+'T'+r.cutoff_jst+':00+09:00');
    if(!Number.isFinite(frozen)||!Number.isFinite(cutoff)||frozen>=cutoff||
      frozen<cutoff-24*60*60*1000)return null;
    const d=r.strong_field_diagnostic;
    const reasons=[];
    const hidden=r.hidden_path_shadow;
    if(hidden?.model_role==='research_shadow'&&hidden.not_formal===true&&
      hidden.result_data_used===false&&hidden.frozen_at_utc===r.frozen_at_utc&&
      ['PRE_CUTOFF_SHADOW_SWAP_ONLY','MISSING_SCENARIO_CANDIDATE'].includes(hidden.status)&&
      Array.isArray(hidden.candidates)&&hidden.candidates.some(x=>x.already_in_formal===false))
      reasons.push('隠れ展開候補');
    if(CLOSE_HEADS.has(d?.status))reasons.push('1着混戦');
    if(r.formal_head_risk_v25?.inside_head_rebalance?.applied===true||
      r.formal_insight_v24?.inside_pressure?.applied===true)reasons.push('攻防変化');
    if(d?.coverage_diagnostics_read_only===true){
      if(d.head_coverage_outside_parity_warning===true||
        d.head_coverage_warning===true)reasons.push('頭候補注意');
      if(d.second_pair_coverage_status==='ASSESSED'&&
        d.second_pair_coverage_warning===true&&
        Array.isArray(d.missing_top_second_pairs)&&d.missing_top_second_pairs.length)
        reasons.push('2着候補注意');
    }
    if(!reasons.length)return null;
    return {label:'⚡ 荒れ注意',reasons:reasons.slice(0,2),
      meaning:'発走前の展開相対評価からの注意表示。荒れる確率・万舟確率は未校正。正式買い目と配分は変更しません。'};
  }
  function render(r,context={}){
    const info=assess(r,context);
    if(!info)return '';
    return '<span class="bl-rough-marker" title="'+info.meaning+'" aria-label="荒れ注意（未校正・展示反映後）">'+
      '<strong>⚡ 荒れ注意</strong><small>'+info.reasons.join('・')+'</small></span>';
  }
  function renderDetails(r,context={}){
    const info=assess(r,context),hidden=r?.hidden_path_shadow;
    if(!info||!info.reasons.includes('隠れ展開候補')||!hidden)return '';
    const missing=hidden.candidates.filter(x=>x.already_in_formal===false).slice(0,3);
    const rows=missing.map(x=>'<li><strong>'+esc(x.combination)+'</strong>：'+
      esc(pathLabels[x.scenario]||'1M別展開')+'</li>').join('');
    const swap=hidden.status==='PRE_CUTOFF_SHADOW_SWAP_ONLY'?
      '<p>同一点数・仮想5万円の研究用差替案：'+esc(hidden.replacement_candidate)+
      '（外す候補 '+esc(hidden.replacement_victim)+'）。正式買い目には追加・置換していません。</p>':
      '<p>採用根拠・点数上限を満たす差替案は未確定です。</p>';
    return '<section class="notice bl-hidden-path-note"><strong>🧠 発走前に検出した隠れ展開（研究用）</strong>'+
      '<ul>'+rows+'</ul>'+swap+
      '<p>すべて展示後の相対値に基づく未校正の仮説です。実際の牽制・進路は映像で未確認。万舟確率や購入推奨ではありません。</p></section>';
  }
  root.BoatRoughRaceSignal={assess,render,renderDetails};
  if(typeof module==='object'&&module.exports)module.exports=root.BoatRoughRaceSignal;
})(typeof window==='undefined'?globalThis:window);
