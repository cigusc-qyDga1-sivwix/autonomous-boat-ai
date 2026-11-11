/* BOAT LAB prediction-first board.
 * Presentation only. Never recalculates predictions, changes the buy policy,
 * promotes provisional research, or edits frozen tickets/results.
 */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const validClock=v=>typeof v==='string'&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(v);
  const money=v=>Number(v||0).toLocaleString('ja-JP')+'円';
  const jstDay=now=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
  const jstClock=now=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit',hour12:false}).format(now);
  const POST_CUTOFF_WINDOW_MS=10*60*1000;
  let mode='formal';
  function setMode(next){mode=next==='research'?'research':'formal';return mode;}
  function getMode(){return mode;}
  function isFormal(r,data,policy,opts={}){
    return !!(data?.mode==='auto-live'&&!opts.imported&&r?.classification!=='SKIP'&&
      r?.phase==='exhibition'&&r?.entry_exhibition_gate?.final_eligible===true&&
      r?.exhibition_input_check?.verified_before_freeze===true&&
      policy?.classify?.(r,data.event_date)?.formal===true);
  }
  function summarize(data,now=new Date(),policy=root.BoatTicketPolicy,opts={}){
    const day=data?.event_date;
    const current=day===jstDay(now);
    const clock=jstClock(now);
    const races=(Array.isArray(data?.forecast_races)?data.forecast_races:[])
      .filter(r=>r&&typeof r.venue==='string'&&Number.isInteger(r.race)&&r.race>=1&&r.race<=12&&
        validClock(r.cutoff_jst)&&Array.isArray(r.bets)&&r.bets.length);
    const venue=typeof opts.venue==='string'&&opts.venue!=='全場'?opts.venue:null;
    const relevant=venue?races.filter(r=>r.venue===venue):races;
    const upcoming=current?relevant.filter(r=>
      Date.parse(day+'T'+r.cutoff_jst+':00+09:00')>now.getTime())
      .sort((a,b)=>a.cutoff_jst.localeCompare(b.cutoff_jst)||a.venue.localeCompare(b.venue,'ja')||a.race-b.race):[];
    // Keep previously frozen forecasts on screen from the cutoff itself for
    // precisely ten minutes; never re-score or make them look actionable.
    const postCutoff=current?relevant.filter(r=>{
      const elapsed=now.getTime()-Date.parse(day+'T'+r.cutoff_jst+':00+09:00');
      return r.classification!=='SKIP'&&elapsed>=0&&elapsed<POST_CUTOFF_WINDOW_MS;
    }).sort((a,b)=>b.cutoff_jst.localeCompare(a.cutoff_jst)||
      a.venue.localeCompare(b.venue,'ja')||a.race-b.race):[];
    const formal=upcoming.filter(r=>isFormal(r,data,policy,opts));
    const research=upcoming.filter(r=>!isFormal(r,data,policy,opts));
    return {day,current,formal,research,upcoming,postCutoff,venue,
      first:upcoming[0]||null,updated:data?.updated_at_utc||null};
  }
  function numbers(combo){
    const parts=String(combo||'').split('-');
    if(parts.length!==3||parts.some(p=>! /^[1-6]$/.test(p))||new Set(parts).size!==3)
      return '<strong class="bl-focus-combo-text">'+esc(combo)+'</strong>';
    return '<span class="bl-focus-combo">'+parts.map(n=>
      '<span class="bl-focus-lane lane-'+n+'">'+n+'</span>').join('<span class="bl-focus-arrow" aria-hidden="true">›</span>')+'</span>';
  }
  function ticket(r,i){
    const b=(r.bets||[])[i];
    return '<div class="bl-focus-ticket">'+numbers(b.combination)+
      '<strong class="bl-focus-amount">'+money(b.virtual_yen)+'</strong></div>';
  }
  function card(r,formal,minutesLeft=null,closed=false){
    const kind=formal?'formal':'pending';
    const label=formal?'展示反映・正式固定':r.classification==='SKIP'?
      'SKIP・研究記録':r.entry_exhibition_gate?.entry_watch?'前付け警戒・暫定':'展示未確認・暫定';
    const shown=r.bets.slice(0,3);
    const total=r.bets.reduce((n,b)=>n+(Number.isSafeInteger(b.virtual_yen)?b.virtual_yen:0),0);
    const classified=r.classification==='SKIP'?' / SKIP':r.classification==='BUY'?' / BUY分類':' / WATCH分類';
    const scenario=typeof r.scenario==='string'&&r.scenario.trim()?
      '<p class="bl-focus-scenario"><strong>保存時の展開仮説</strong>'+esc(r.scenario)+'</p>':'';
    return '<article class="bl-focus-card is-'+kind+(closed?' is-cutoff-soon':'')+'">'+
      '<div class="bl-focus-card-head"><div><strong>'+esc(r.venue)+' <span>'+r.race+'R</span></strong>'+
      '<small>締切予定 '+esc(r.cutoff_jst)+' JST'+esc(classified)+'</small></div>'+
      '<span class="bl-focus-status is-'+kind+'">'+label+'</span></div>'+
      (closed?'<p class="bl-focus-countdown is-closed" role="status">投票締切済み ・ 記録表示あと約'+esc(minutesLeft)+'分</p>':'')+
      '<div class="bl-focus-tickets">'+shown.map((b,i)=>ticket(r,i)).join('')+'</div>'+
      scenario+
      '<div class="bl-focus-card-bottom"><span>先頭'+shown.length+'点を表示 / 全'+r.bets.length+'点・仮想'+money(total)+'</span>'+
      '<button type="button" data-race="'+esc(r.venue)+'|'+r.race+'" aria-label="'+esc(r.venue+' '+r.race)+'Rの'+(formal?'正式':'暫定')+'予想詳細を開く">全買い目を見る <span aria-hidden="true">→</span></button></div>'+
      (closed?'<p class="bl-focus-note">締切後の保存済み予想です。新規投票不可・買い目変更なし。'+
        (formal?'展示反映済みの正式固定記録。':'展示未確認の暫定記録。')+'</p>':
        formal?'<p class="bl-focus-note">正式固定の確認済み。BUYの採算判断・オッズ確認とは別です。</p>':
        '<p class="bl-focus-note">参考表示のみ。展示後の正式買い目ではありません。</p>')+
      '</article>';
  }
  function render(data,now=new Date(),policy=root.BoatTicketPolicy,opts={}){
    if(!data||!Array.isArray(data.forecast_races))return '';
    const s=summarize(data,now,policy,opts);
    const chosen=mode==='research'?s.research:s.formal;
    const visible=chosen.slice(0,6);
    const updated=s.updated?new Date(s.updated):null;
    const updatedAt=updated&&!Number.isNaN(updated.getTime())?
      updated.toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'時刻未確認';
    const ageMinutes=updated&&!Number.isNaN(updated.getTime())?
      Math.max(0,Math.floor((now.getTime()-updated.getTime())/60000)):null;
    const delayed=s.current&&(ageMinutes===null||ageMinutes>20);
    const freshnessNote=delayed?'<p class="bl-focus-delay" role="status">⚠ 予想データの更新が遅れています（'+
      (ageMinutes===null?'最終取得時刻不明':esc(ageMinutes)+'分前')+
      '）。最新の展示・締切情報は未確認です。</p>':'';
    const count=s.formal.length+s.research.length;
    const title=s.venue?s.venue+'の予想を先に確認':'直近の予想を先に確認';
    return '<section class="bl-focus-board" aria-label="買い目を先に確認するクイックボード">'+
      '<div class="bl-focus-heading"><div><span class="bl-focus-eyebrow">PREDICTION FIRST / BOAT LAB</span>'+
      '<h2>'+esc(title)+'</h2><p>3連単・配分・展示反映を一覧で確認</p></div>'+
      '<div class="bl-focus-updated">データ更新 <strong>'+esc(updatedAt)+' JST</strong></div></div>'+
      (s.current?'<div class="bl-focus-metrics"><span><strong>'+s.formal.length+'</strong>正式予想</span>'+
      '<span><strong>'+s.research.length+'</strong>暫定・研究</span>'+
      '<span><strong>'+esc(s.first?.cutoff_jst||'—')+'</strong>次の締切予定</span></div>':
      '<div class="bl-focus-old" role="status">表示中の記録は'+esc(s.day||'日付不明')+
      '分です。今日の予想・締切として扱いません。</div>')+
      freshnessNote+
      (s.current&&s.postCutoff.length?'<div class="bl-focus-urgent" aria-label="締切後10分の保存済み予想">'+
        '<h3>締切後10分・固定予想の記録 <span>'+s.postCutoff.length+'R</span></h3>'+
        '<p>締切時刻から10分間、発走前に保存した買い目を表示します。投票締切済み・新規投票不可。</p>'+
        '<div class="bl-focus-grid">'+s.postCutoff.slice(0,6).map(r=>{
          const until=Date.parse(s.day+'T'+r.cutoff_jst+':00+09:00')+POST_CUTOFF_WINDOW_MS-now.getTime();
          return card(r,isFormal(r,data,policy,opts),Math.ceil(until/60000),true);
        }).join('')+'</div></div>':'')+
      '<div class="bl-focus-switch" role="group" aria-label="予想の種類">'+
      '<button type="button" data-focus-mode="formal" aria-pressed="'+(mode==='formal')+'"'+
      (mode==='formal'?' class="active"':'')+'>正式予想 <span>'+s.formal.length+'</span></button>'+
      '<button type="button" data-focus-mode="research" aria-pressed="'+(mode==='research')+'"'+
      (mode==='research'?' class="active"':'')+'>暫定・研究 <span>'+s.research.length+'</span></button></div>'+
      (s.current?
        '<div class="bl-focus-grid">'+(visible.length?visible.map(r=>card(r,mode==='formal')).join(''):
        '<p class="bl-focus-empty">'+(mode==='formal'?'展示情報と締切前固定を確認できた正式予想は、現在の締切予定にはありません。':
          '今後の締切予定に該当する暫定・研究予想はありません。')+'</p>')+'</div>'+
        (chosen.length>6?'<p class="bl-focus-overflow">直近6Rを表示中。残り'+(chosen.length-6)+'Rは下のレース一覧から確認してください。</p>':''):
        '<p class="bl-focus-empty">過去の固定予想は下の開催一覧・レース一覧から確認できます。</p>')+
      '<p class="bl-focus-guard">正式＝6艇展示入力を照合し、締切前に固定された買い目。BUY採算判定とは異なります。'+
      'SKIP・暫定・研究用は正式に含めません。仮想金額であり実投票ではありません。'+
      (count===0&&s.current?'予想が未取得の場合は表示しません。':'')+'</p></section>';
  }
  root.BoatPredictionFocus={render,summarize,isFormal,setMode,getMode};
  if(typeof module==='object'&&module.exports)module.exports=root.BoatPredictionFocus;
})(typeof window==='undefined'?globalThis:window);
