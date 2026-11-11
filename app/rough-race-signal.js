/* Post-exhibition rough-race warning: display only, never an odds/ROI claim.
 * Consumes immutable pre-cutoff diagnostics; never reads results or payouts.
 */
(function(root){
  'use strict';
  const CLOSE_HEADS=new Set(['STRONG_FIELD_CLOSE_HEADS','MODEL_CLOSE_HEADS_NOT_STRONG_FIELD']);
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
  root.BoatRoughRaceSignal={assess,render};
  if(typeof module==='object'&&module.exports)module.exports=root.BoatRoughRaceSignal;
})(typeof window==='undefined'?globalThis:window);
