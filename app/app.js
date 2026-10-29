/* BOAT LAB v1.0: offline-first, manual-result, prediction inspection UI.
 * This file never places bets, never sends notifications and never fetches results.
 */
(() => {
  'use strict';
  const STORE_RESULTS = 'boatlab-results-v1';
  const STORE_BATCH_OFFICIAL = 'boatlab-batch-official-v1';
  const STORE_DATA = 'boatlab-imported-dataset-v1';
  const STORE_FAVORITES = 'boatlab-favorite-venues-v1';
  const dateDisplay = s => /^\d{4}-\d{2}-\d{2}$/.test(s) ? s.replace(/-/g, '/') : s;
  const money = n => `${Number(n || 0).toLocaleString('ja-JP')}円`;
  const pct = v => `${(v * 100).toFixed(1)}%`;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const isCombo = s => /^[1-6]-[1-6]-[1-6]$/.test(s) && new Set(s.split('-')).size === 3;
  const raceKey = r => `${data.event_date}|${r.venue}|${r.race}`;
  const el = id => document.getElementById(id);
  const titles = {overview:'ダッシュボード',races:'レース・買い目',results:'結果照合',analysis:'成績分析',settings:'データ管理'};
  const state = {view:'overview',venue:'全場',classification:'ALL',boardFilter:'all',boardSort:'official',raceDetail:null,resultQuickFilter:'recent',resultQuickExpanded:false,showExternalAnalysis:false,reanalysisResult:null,reanalysisExtras:{},reanalysisNotice:'',resultVenue:'鳴門',resultRace:1,origin:'GitHubで発走前固定した予想のローカル写し'};
  let data = null;
  let results = {};
  let autoResults = {};
  let batchOfficial = {};
  let lastLiveUpdate = '';
  let resultsRefreshBusy = false;
  let officialPollBusy = false;
  let resultsRefreshNotice = '';
  let resultsRefreshIsError = false;
  let favorites = [];
  let toastTimer = null;

  const navigationHistory=[];
  function snapshotNavigation(){
    return {view:state.view,venue:state.venue,classification:state.classification,
      detailVenue:state.raceDetail?.venue||null,detailRace:state.raceDetail?.race||null,
      resultVenue:state.resultVenue,resultRace:state.resultRace};
  }
  function rememberNavigation(){
    const current=snapshotNavigation(),last=navigationHistory.at(-1);
    if(!last||JSON.stringify(last)!==JSON.stringify(current)){
      navigationHistory.push(current);
      if(navigationHistory.length>35)navigationHistory.shift();
    }
  }
  function resetRaceWork(){
    state.showExternalAnalysis=false;state.reanalysisResult=null;
    state.reanalysisExtras={};state.reanalysisNotice='';
  }
  function restoreNavigation(previous){
    state.view=previous.view;state.venue=previous.venue;
    state.classification=previous.classification;
    state.resultVenue=previous.resultVenue;state.resultRace=previous.resultRace;
    state.raceDetail=previous.detailVenue?
      findRace(previous.detailVenue,previous.detailRace)||null:null;
    resetRaceWork();render();window.scrollTo(0,0);
  }
  function goBack(){
    if(navigationHistory.length){restoreNavigation(navigationHistory.pop());return true;}
    if(state.view==='races'&&state.raceDetail){
      state.raceDetail=null;resetRaceWork();render();window.scrollTo(0,0);return true;
    }
    if(state.view==='races'&&state.venue!=='全場'){
      state.venue='全場';state.view='overview';render();window.scrollTo(0,0);return true;
    }
    if(state.view!=='overview'){
      state.view='overview';state.raceDetail=null;resetRaceWork();render();
      window.scrollTo(0,0);return true;
    }
    return false;
  }
  function showRace(r){
    if(!r)return;
    rememberNavigation();
    state.raceDetail=r;state.view='races';resetRaceWork();
    render();window.scrollTo(0,0);
  }


  function readJSON(key, fallback) {
    try { const s = localStorage.getItem(key); return s ? JSON.parse(s) : fallback; }
    catch { return fallback; }
  }
  function persistResults() {
    try { localStorage.setItem(STORE_RESULTS, JSON.stringify(results)); return true; }
    catch { toast('このブラウザでは結果を保存できません'); return false; }
  }
  function normalizeData(payload) {
    if (!payload || typeof payload !== 'object' || !/^\d{4}-\d{2}-\d{2}$/.test(payload.event_date) || !Array.isArray(payload.forecast_races) || (!payload.forecast_races.length && payload.mode!=='auto-live') || payload.forecast_races.length > 300) throw Error('予想データの形式が正しくありません');
    const seen = new Set();
    for (const r of payload.forecast_races) {
      if (typeof r.venue !== 'string' || !r.venue.trim() || !Number.isInteger(r.race) || r.race < 1 || r.race > 12 || typeof r.cutoff_jst !== 'string' || !/^\d{2}:\d{2}$/.test(r.cutoff_jst) || !['BUY','WATCH','SKIP'].includes(r.classification) || !Array.isArray(r.bets) || !r.bets.length || r.bets.length > 120) throw Error('レースデータが不正です');
      const key = `${r.venue}|${r.race}`;
      if (seen.has(key)) throw Error('同じレースが重複しています');
      seen.add(key);
      if (r.bets.some(b => !isCombo(b.combination) || !Number.isSafeInteger(b.virtual_yen) || b.virtual_yen < 0 || b.virtual_yen % 100 !== 0)) throw Error('買い目または金額が不正です');
      if (new Set(r.bets.map(b => b.combination)).size !== r.bets.length) throw Error('買い目が重複しています');
      if (r.bets.reduce((s,b)=>s+b.virtual_yen,0) > 100000000) throw Error('配分額の上限を超えています');
    }
    return payload;
  }
  function allRaces() { return [...data.forecast_races].sort((a,b)=>a.venue.localeCompare(b.venue,'ja') || a.race-b.race); }
  function getVenues() { return [...new Set(allRaces().map(r=>r.venue))]; }
  function findRace(venue,race) {return allRaces().find(r=>r.venue===venue && r.race===Number(race));}
  function officialFor(r) {
    const k=raceKey(r),published=autoResults[k],imported=batchOfficial[k];
    if(!data||data.mode!=='auto-live')return null;
    if(published&&imported&&(published.finish!==imported.finish||
      published.payout_per_100!==imported.payout_per_100))return null;
    const v=published||imported;
    if(!v||v.source!=='boatrace_official_pay'||v.verified!==true)return null;
    if(v.snapshot_sha256&&(!r.sha256||v.snapshot_sha256!==r.sha256))return null;
    if(!isCombo(v.finish)||!Number.isSafeInteger(v.payout_per_100)||
      v.payout_per_100<100||v.payout_per_100>10000000||v.payout_per_100%10)return null;
    return v;
  }
  function resultIssue(r) {
    const k=raceKey(r),published=autoResults[k],imported=batchOfficial[k];
    if(data?.settlement_alerts?.[k])return data.settlement_alerts[k];
    if(published&&imported&&(published.finish!==imported.finish||
      published.payout_per_100!==imported.payout_per_100))
      return {status:'conflict',reason:'公式確認済みの値が保存済みデータと一致しません'};
    return null;
  }
  function recordFor(r) {return resultIssue(r)?null:(officialFor(r)||results[raceKey(r)]||null);}
  function officialStats(races) {
    const verified=races.filter(r=>!!officialFor(r)&&!resultIssue(r));
    let hits=0,invested=0,paid=0,heads=0,firstSeconds=0,thirdMiss=0;
    for(const r of verified){
      const c=compute(r);if(!c.record)continue;
      hits+=Number(c.hit);invested+=c.stake;paid+=c.payout;
      heads+=Number(c.headCaptured);firstSeconds+=Number(c.firstSecond);
      if(c.firstSecond&&!c.hit)thirdMiss++;
    }
    return {count:verified.length,hits,invested,paid,profit:paid-invested,
      hitRate:verified.length?hits/verified.length:0,
      returnRate:invested?paid/invested:null,heads,firstSeconds,thirdMiss};
  }
  function compute(r) {
    const record=recordFor(r),stake=r.bets.reduce((s,b)=>s+b.virtual_yen,0);
    if (!record) return {record:null,stake,payout:null,hit:null,profit:null};
    const match=r.bets.find(b=>b.combination===record.finish);
    const hit=!!match;
    const payout=hit?Math.round(match.virtual_yen*record.payout_per_100/100):0;
    return {record,stake,payout,hit,profit:payout-stake,headCaptured:r.bets.some(b=>b.combination[0]===record.finish[0]),firstSecond:r.bets.some(b=>b.combination.slice(0,3)===record.finish.slice(0,3))};
  }
  function stats(races) {
    let examined=0, hits=0, invested=0, paid=0, heads=0, firstSeconds=0, thirdMiss=0;
    for (const r of races) {
      const c=compute(r);
      if (!c.record) continue;
      examined++; hits+=Number(c.hit); invested+=c.stake; paid+=c.payout; heads+=Number(c.headCaptured); firstSeconds+=Number(c.firstSecond);
      if(c.firstSecond && !c.hit) thirdMiss++;
    }
    return {count:races.length,examined,hits,invested,paid,profit:paid-invested,hitRate:examined?hits/examined:0,returnRate:invested?paid/invested:null,heads,firstSeconds,thirdMiss};
  }
  function pill(text,cls) {return `<span class="pill ${cls||String(text).toLowerCase()}">${escape(text)}</span>`;}
  function finishPill(r) {
    const issue=resultIssue(r);
    if(issue)return pill(issue.status==='cancelled'?'レース中止':'公式・要確認','pending');
    const c=compute(r);
    if(!c.record)return pill('未照合','pending');
    return pill((officialFor(r)?'公式 ':'')+(c.hit?'的中':'不的中'),c.hit?'hit':'miss');
  }
  function head(title,subtitle,actions='') {return `<div class="page-heading"><div><div class="page-eyebrow">BOAT LAB / ${escape(data.event_date)}</div><h1>${escape(title)}</h1><p>${escape(subtitle)}</p></div>${actions?`<div class="right-controls">${actions}</div>`:''}</div>`;}
  function metric(label,value,sub,mark='',cls='') {return `<div class="card metric"><div class="metric-top"><span>${escape(label)}</span><span class="metric-mark">${escape(mark)}</span></div><strong class="metric-value ${cls}">${escape(value)}</strong><span class="metric-sub">${escape(sub)}</span></div>`;}
  function venueSelect(selected,attr='data-filter-venue') {return `<select class="select" ${attr} aria-label="競艇場を選択"><option value="全場" ${selected==='全場'?'selected':''}>全競艇場</option>${getVenues().map(v=>`<option value="${escape(v)}" ${selected===v?'selected':''}>${escape(v)}</option>`).join('')}</select>`;}
  function weatherFor(venue,time) {
    const bands=(data.weather||[]).find(x=>x.venue===venue)?.bands||[];
    return bands.find(b=>time>=b.from && time<b.to)||bands.at(-1)||null;
  }
  function weatherHTML(venue) {
    const bands=(data.weather||[]).find(w=>w.venue===venue)?.bands||[];
    if (!bands.length) return '<p class="muted text-sm">気象データ未登録。補正なし。</p>';
    return bands.map(b=>`<div class="weather-box"><div class="weather-symbol">≋</div><div class="weather-body"><strong>${escape(b.from)}–${escape(b.to)} ・ ${escape(b.wind)}</strong><p>${escape(b.note)}</p></div></div>`).join('');
  }
  function raceRow(r) {return `<button type="button" class="race-row" data-race="${escape(r.venue)}|${r.race}"><span class="race-no">${r.race}R</span><span class="race-info"><strong>${escape(r.venue)}・${escape(r.scenario)}</strong><small>${escape(r.bets.slice(0,2).map(b=>b.combination).join(' / '))}</small></span><span class="race-time">${escape(r.cutoff_jst)}</span>${pill(r.classification)}</button>`;}
  function boardOptions() {
    const current = new Date();
    const jp = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit',hour12:false});
    const parts = new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(current);
    const extract = part => parts.find(p=>p.type===part)?.value || '';
    return {now:jp.format(current),today:extract('year')+'-'+extract('month')+'-'+extract('day'),favorites,filter:state.boardFilter,sort:state.boardSort};
  }
  function overview() {
    if(window.BoatVenueBoard) return (window.BoatRaceTimeline?.render(data)||'')+window.BoatVenueBoard.renderHome(data,boardOptions());
    const all=allRaces();const recorded=stats(all);const countWatch=all.filter(r=>r.classification==='WATCH').length;const countSkip=all.filter(r=>r.classification==='SKIP').length;const isLive=data.mode==='auto-live';const dayJst=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());const stale=isLive&&dayJst!==data.event_date;const updated=isLive&&data.updated_at_utc?new Date(data.updated_at_utc).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}):'未確認';
    const nowJst=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date());const soon=all.filter(r=>r.classification==='WATCH' && (data.mode!=='auto-live'||r.cutoff_jst>nowJst)).sort((a,b)=>a.cutoff_jst.localeCompare(b.cutoff_jst)).slice(0,6);
    return `${head('AI予想ダッシュボード',`${dateDisplay(data.event_date)} ・ ${getVenues().length}場 / ${data.mode==='auto-live'?'全国開催・自動取得（非公式）':'展示前の固定予想'}` ,`<button class="btn btn-white" data-action="export-results">↧ 結果CSV</button>`)}
    <section class="hero"><div class="hero-inner"><div class="hero-kicker"><span class="pulse"></span> PRE-RACE RESEARCH · ${data.mode==='auto-live'?'自動更新 v1.1':'v1.0'}</div><h2>感覚ではなく、<br>展開とデータで検証する。</h2><p>スタートから1マーク、2・3着連動まで。発走前の予想を残して、結果で改善を積み重ねる。</p></div><div class="hero-motif" aria-hidden="true">≋</div></section>
    <div class="metrics">${metric('固定予想',`${all.length} R`,data.mode==='auto-live'?`${data.venues_with_races||0}場中・締切前固定済み`:'発走前の記録','↗')}${metric('WATCH',`${countWatch} R`,isLive?'展示前・展示反映を含む／オッズ未確認':'展示・オッズ未反映','◷')}${metric('結果照合',`${recorded.examined} / ${all.length}`,isLive?'非公式結果の自動取得＋手入力':'手入力で記録','✓')}${metric('的中率',recorded.examined?pct(recorded.hitRate):'—','照合済みレースのみ','▥',recorded.examined&&recorded.hits?'positive':'')}</div>
    ${isLive?`<div class="notice ${stale?'warn':''}">自動取得（非公式）最終更新：${escape(updated)} JST ／ 公開出走表 ${escape(data.listed_races||0)}R・締切前予想 ${all.length}R・未固定 ${escape((data.unforecast_races||[]).length)}R。${stale?'<strong>前日以前の記録です。今日の予想ではありません。</strong>':'予想は結果を見ずに作成・固定。'} 定期実行は遅延する場合があります。</div>`:''}
    <div class="columns-2"><section class="card card-pad"><div class="section-head"><h2 class="section-title">注目レース</h2><button class="link-btn" data-action="go-races">全レースを見る →</button></div><div class="race-list">${soon.map(raceRow).join('')}</div><div class="notice">締切は取得時点の予定。<strong>非公式APIは数分遅れることがあります。</strong></div></section>
    <section class="card card-pad"><div class="section-head"><h2 class="section-title">${isLive?'展示時の場内気象':'時間帯別・気象見通し'}</h2>${pill(isLive?'実測由来・非公式':'予報値','pending')}</div>${isLive?all.filter(r=>r.weather_observed).slice(-6).map(r=>`<div class="weather-box"><div class="weather-symbol">≋</div><div class="weather-body"><strong>${escape(r.venue)} ${r.race}R・風 ${escape(r.weather_observed.wind_speed)}m/s・波高 ${escape(r.weather_observed.wave_height)}cm</strong><p>展示データ取得時点の観測情報（非公式）</p></div></div>`).join('')||'<p class="muted text-sm">展示時の気象はまだ取得できていません。</p>':`<div class="mini-caption">鳴門</div>${weatherHTML('鳴門')}<div class="mini-caption" style="margin-top:18px;margin-bottom:8px">徳山</div>${weatherHTML('徳山')}`}<div class="notice warn">${isLive?'展示前は場内気象未取得。時間別の気象予報と潮位予測は未接続。':'周辺気象の参考値。展示ST・波高・場内風速の実測は未反映。'}</div></section></div>
    <p class="footer-disclaimer">${escape(data.disclaimer||'仮想予想・研究用。自動購入や的中の保証はありません。')} SKIPを含む買い目は比較用の記録で、購入推奨ではありません。</p>`;
  }
  function isFormalTicket(r){
    if(readJSON(STORE_DATA,null))return false;
    return window.BoatTicketPolicy?.classify(r,data.event_date).formal===true;
  }
  function ticketBanner(r){
    const formal=isFormalTicket(r);
    return '<div class="ticket-status '+(formal?'ticket-status-formal':'ticket-status-pending')+'" role="status"><strong>'+(formal?'✅ 正式買い目':'⏳ 暫定・購入判断保留')+'</strong><p>'+(formal?'展示情報を反映して締切前に固定。この下の買い目を正式版として採用しています。':'正式な買い目はまだありません。展示を確認して締切前に固定できるまで保留します。')+'</p></div>';
  }
  function ticketLabel(r){
    if(readJSON(STORE_DATA,null))return "暫定買い目（インポート・固定未検証）";
    return window.BoatTicketPolicy?.classify(r,data.event_date).label||
      (r.phase==='exhibition'&&r.entry_exhibition_gate?.final_eligible?'正式買い目（展示反映・締切前固定）':'暫定買い目（展示未確認・正式化保留）');
  }
  function formalTicketPanel(){
    if(!window.BoatTicketPolicy||data.mode!=='auto-live'||readJSON(STORE_DATA,null))return '';
    const formal=allRaces().filter(r=>window.BoatTicketPolicy.classify(r,data.event_date).formal);
    const s=officialStats(formal);
    return '<section class="card card-pad" aria-label="展示後の正式買い目成績"><h2>展示後の正式買い目成績</h2><p>正式 '+formal.length+'R ／ 公式照合 '+s.count+'R ／ 的中 '+s.hits+'R ／ 仮想収支 '+money(s.profit)+' ／ 回収率 '+(s.invested?pct(s.returnRate):'—')+'</p><p>6艇の進入・ST・展示タイムを反映し締切前に固定した最新版だけ。展示前の暫定予想は研究成績に分けます。正式買い目とBUY判断は別です。</p></section>';
  }
  function entryGateWarning(r) {
    const g=r?.entry_exhibition_gate;
    if(!g && data?.mode!=='auto-live')return '';
    if(g?.final_eligible)
      return '<div class="notice">✅ 正式買い目：展示進入6艇の発走前確認済み：'+
        escape((g.exhibition_course_order||[]).join('-'))+
        '（艇番順）。ただし本番の確定進入とは異なる場合があります。オッズ未確認のためBUYはしません。</div>';
    const risk=g?.entry_watch?'⚠ 前付け警戒レース':'⚠ 展示未確認';
    const explanation=g?.reason||'6艇の実進入・展示ST・展示タイムを検証できていません';
    return '<div class="notice warn"><strong>'+risk+'：最終予想保留・BUY禁止</strong>'+
      '<p>'+escape(explanation)+'。表示される固定買い目は展示前の研究記録です。'+
      '発走前の展示確認なしに最終買い目として扱わないでください。</p></div>';
  }
  function tacticalSummary(r){
    if(r?.model_role==='main')return null; // v0.7/v0.9 is already frozen as primary.
    if(r?.entry_exhibition_gate?.entry_watch && !r.entry_exhibition_gate.final_eligible)return null;
    try{
      const x=window.BoatTacticalModel?.forecast(r);
      return x?{top:x.top,points:x.bets.length,different:x.differs_from_frozen}:null;
    }catch{return null}
  }
  function tile(r) {
    const trial=tacticalSummary(r);
    return '<button type="button" class="race-tile" data-race="'+escape(r.venue)+'|'+r.race+'">'+
      '<div class="tile-top"><span class="tile-r">'+escape(r.venue)+' '+r.race+'R</span>'+pill(r.classification)+'</div>'+
      '<div class="ticket-list-status '+(isFormalTicket(r)?'ticket-status-formal':'ticket-status-pending')+'">'+(isFormalTicket(r)?'✅ 正式買い目':'⏳ 暫定・購入判断保留')+'</div>'+
      '<div class="tile-time">締切予定 '+escape(r.cutoff_jst)+' · 固定 '+r.bets.length+'点 · '+(r.phase==='exhibition'?'展示反映':'展示前')+'</div>'+
      '<div class="tile-bets">'+(r.model_role==='main'?'✅ '+(r.model_version==='four-factor-v1.5-point-free-untrained'?'点数枠なしv1.5':r.model_version==='four-factor-v1.4-venue-aware-23-untrained'?'場別23場v1.4':r.model_version==='four-factor-v1.3-conditional-scenarios-untrained'?'四要素v1.3':r.model_version==='four-factor-v1.2-head-coverage-untrained'?'四要素v1.2・頭候補保持':r.model_version==='four-factor-v1.1-untrained'?'四要素v1.1':r.model_version==='four-factor-v1.0-untrained'?'四要素v1.0':r.model_version?.includes('v0.9')?'v0.9':'v0.7')+'メイン固定：':'🔒 旧モデル固定：')+
      (isFormalTicket(r)?escape(r.bets.slice(0,2).map(b=>b.combination).join(' / ')):'正式買い目は未確定')+'</div>'+
      (r.legacy_control||trial?'<div class="tile-tactical">🔬 比較用モデルあり・正式買い目とは別</div>':'')+
      (r.entry_exhibition_gate?.entry_watch&&!r.entry_exhibition_gate.final_eligible?
       '<div class="notice warn">⚠ 前付け警戒・展示進入未確認／最終予想保留</div>':
       r.entry_exhibition_gate&&!r.entry_exhibition_gate.final_eligible?
       '<div class="notice warn">展示確認待ち・最終判断保留</div>':'')+
      '<div class="tile-scenario">'+escape(r.scenario)+'</div>'+
      '<div class="tile-foot"><span>'+finishPill(r)+'</span><strong>比較を見る ↗</strong></div></button>';
  }
  function races() {
    if(state.raceDetail) return detail(state.raceDetail);
    if(state.venue!=='全場' && window.BoatVenueBoard) return window.BoatVenueBoard.renderVenue(data,state.venue,boardOptions());
    const filtered=allRaces().filter(r=>(state.venue==='全場'||r.venue===state.venue)&&(state.classification==='ALL'||r.classification===state.classification));
    return `${head('レース・買い目',`${dateDisplay(data.event_date)} / ${data.mode==='auto-live'?'全国の発走前固定済み予想':'保存済み予想'} / 各Rの仮想5万円配分`)}<div class="filter-bar"><div class="segmented">${['ALL','WATCH','SKIP'].map(v=>`<button data-filter-status="${v}" class="${state.classification===v?'active':''}">${v==='ALL'?'すべて':v}</button>`).join('')}</div>${venueSelect(state.venue)}</div><div class="race-grid">${filtered.map(tile).join('')||'<div class="no-data">該当するレースはありません</div>'}</div>${data.mode==='auto-live'&&data.unforecast_races?.length?`<div class="notice warn">${data.unforecast_races.length}Rは締切前の予想を固定できなかったため、買い目を表示しません。結果を見てから予想を追加することもありません。</div>`:''}<p class="footer-disclaimer">BUYが0件なのは、オッズによる採算チェックを完了していないため。SKIPレースも研究目的で予想を保持しています。</p>`;
  }
  function raceWeatherHTML(r) {
    const actual=r.weather_used||(r.weather_observed?.wind_speed!=null?
      {...r.weather_observed,source:'boatrace_preview',site_observed:true,
       source_label:'展示時の場内観測（非公式API経由）'}:null);
    const selected=actual||(data.venue_weather||{})[r.venue];
    if(!selected)return '<p class="muted text-sm">気象情報未取得。風・波による補正は行っていません。</p>';
    const frozen=!!actual;
    const observed=!!selected.site_observed;
    const source=observed?'場内展示時の観測（非公式API経由）':
      frozen?'発走前に取得した周辺気象予報':'最新取得分の周辺気象予報（発走前予想には未反映）';
    const wind=selected.wind_speed!=null?escape(selected.wind_speed)+'m/s':'未取得';
    const dir=selected.wind_direction_degrees!=null?escape(selected.wind_direction_degrees)+'°':selected.wind_direction_number!=null?'方向コード'+escape(selected.wind_direction_number):'未取得';
    const gust=selected.wind_gust!=null?escape(selected.wind_gust)+'m/s':'—';
    const wave=selected.wave_height!=null?escape(selected.wave_height)+'cm':'未取得';
    const temp=selected.air_temperature!=null?escape(selected.air_temperature)+'℃':'—';
    const rain=selected.precipitation_mm!=null?escape(selected.precipitation_mm)+'mm/h':'—';
    const adjusted=r.weather_adjustment;
    const status=!frozen?'この気象データは既存の固定予想を変えていません。':
      adjusted?.applied?'気象による不確実性補正を試験的に適用しました。':'通常条件または旧モデルのため、気象による重みの変更はありません。';
    const issued=selected.issued_at_utc?formatJst(selected.issued_at_utc):'';
    const time=selected.forecast_hour_jst?selected.forecast_hour_jst.slice(11,16)+' JST':'';
    return `<div class="race-weather-detail">
      <div class="race-weather-kind"><strong>🌦 ${escape(source)}</strong><span>${escape(time)}</span></div>
      <div class="race-weather-values">
        <span><b>🌬 ${wind}</b><small>風速</small></span>
        <span><b>${dir}</b><small>風向</small></span>
        <span><b>${gust}</b><small>突風</small></span>
        <span><b>🌊 ${wave}</b><small>波高</small></span>
        <span><b>${temp}</b><small>気温</small></span>
        <span><b>${rain}</b><small>降水量</small></span>
      </div>
      <p>${escape(status)} ${escape(adjusted?.why||'')} ${issued?'（予報取得 '+escape(issued)+'）':''}</p>
      <p class="race-weather-caution">${observed?'場内観測は展示時点の値であり、レース本番時の実測を保証しません。':'周辺予報は会場水面の現地実測ではありません。風向とコース有利不利の関係は未校正です。'}
      ${selected.source==='open-meteo'?'<a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Weather data by Open-Meteo.com (CC BY 4.0) ↗</a>':''}</p>
    </div>`;
  }
  function venuePanel(r) {
    const p=r?.venue_profile,adj=r?.venue_adjustment,surface=r?.venue_surface_v1;
    if(!p)return '';
    const rate=p.course1_reference_rate!=null?
      (Number(p.course1_reference_rate)*100).toFixed(1)+'%':'未取得';
    return '<section class="card card-pad bottom-margin" aria-label="会場別展開ロジック">'+
      '<div class="section-head"><h2 class="section-title">🏁 '+escape(r.venue)+'専用・水面補正</h2>'+
      '<a href="./venue-profiles.html">全国24場を見る ↗</a></div>'+
      '<p><b>水質：</b>'+escape(p.water_type)+'　<b>風の注意：</b>'+escape(p.wind_exposure)+
      '　<b>潮・流れ：</b>'+(p.tide_sensitive?'実測不足なら数値補正なし':'対象外')+'</p>'+
      '<p><b>水面・進入：</b>'+escape(p.layout_focus)+'</p>'+ 
      (surface?'<p><b>水面展開v1：</b>'+(surface.excluded?'江戸川は今回対象外（従来方式を維持）':surface.applied?'公式水面特性＋発走前ST・舟足根拠でセンター攻めを試験補正':surface.eligible?'23場対象／追加攻防補正の発動条件なし':'適用対象外')+'</p>':'')+
      (surface?.center_attack_evidence?.length?'<p><b>補正根拠：</b>'+surface.center_attack_evidence.map(s=>escape(s.course+'コース ×'+Number(s.multiplier).toFixed(3)+'／内隣ST差 '+s.st_gap_sec+'秒')).join('、')+'</p>':'')+
      '<p><b>攻防の着眼点：</b>'+escape(p.tactical_focus)+'</p>'+
      '<p><b>1コース相対重みの試験補正：</b>×'+
          escape(adj?.course1_relative_multiplier??'1.0000')+
      '（参考過去1着率 '+escape(rate)+'を弱く反映）</p>'+
      (adj?.wind_risk?'<p>⚠ '+escape(adj.wind_risk)+'</p>':'')+
      '<p class="muted text-sm">過去率＝このレースの1号艇勝率ではありません。選手・モーター・展示と実測を優先。'+
      '戦法別の数値モデル、潮流補正、整備による性能変化は今後の検証課題です。</p></section>';
  }
  // Cross-model read-only report. Trial scores/marks and frozen picks are NOT
  // produced by one model. Show exactly which rank appears in which role.
  function roleConsistencyPanel(r,trial){
    const scores=trial?.head_course_shares,cover=trial?.role_coverage;
    if(!Array.isArray(scores)||scores.length!==6||!cover)return '';
    const ranking=[...scores].sort((a,b)=>b.relative_share-a.relative_share||a.lane-b.lane);
    const rankByLane=Object.fromEntries(ranking.map((x,i)=>[x.lane,i+1]));
    const tally=(bets,lane)=>[0,1,2].map(k=>(bets||[]).filter(b=>
      b.combination?.split('-')[k]===String(lane)).length);
    const mark=['◎','○','▲','△','☆','－'];
    const rows=ranking.map(x=>{
      const lane=Number(x.lane),role=cover[lane]||{},original=tally(r.bets,lane),
        trialUse=tally(trial.bets,lane),rank=rankByLane[lane];
      const headScore=Number(role.first||0),secondScore=Number(role.second||0),
        thirdScore=Number(role.third||0);
      const fixedGap=rank<=3&&original[0]===0&&original[1]===0;
      const trialGap=rank<=3&&trialUse[0]===0&&trialUse[1]===0;
      const flag=fixedGap||trialGap;
      return '<tr'+(flag?' class="role-alignment-gap"':'')+'><th scope="row"><strong>'+
        escape(mark[rank-1])+' '+escape(lane)+'号艇</strong><small> '+rank+'位</small></th>'+
        '<td>'+[headScore,secondScore,thirdScore].map(v=>(v*100).toFixed(1)).join(' / ')+'</td>'+
        '<td>'+original.join(' / ')+'</td><td>'+trialUse.join(' / ')+'</td>'+
        '<td>'+(flag?'<b>要確認</b>':role.note?.includes('3着のみ')?'3着中心':'—')+'</td></tr>';
    }).join('');
    const warning=ranking.some(x=>{
      const lane=x.lane;return rankByLane[lane]<=3&&
        tally(r.bets,lane)[0]===0&&tally(r.bets,lane)[1]===0;
    });
    return '<div class="role-alignment-panel" aria-label="選手優位順位と買い目の整合性監査">'+
      '<h3>🔎 選手評価 × 1・2・3着の整合性チェック</h3>'+
      '<p>出走表の印は<strong>試験モデルの1着候補順位</strong>。正式固定の買い目は<strong>別モデル</strong>だから、順位が高くても着順が一致するとは限りません。</p>'+
      '<div class="boat-entry-overflow"><table class="bets-table role-alignment-table"><thead><tr>'+
      '<th>艇・1着順位</th><th>試験相対評価<br>1着/2着/3着</th><th>固定買い目<br>1着/2着/3着</th>'+
      '<th>戦法試験買い目<br>1着/2着/3着</th><th>点検</th></tr></thead><tbody>'+
      rows+'</tbody></table></div>'+
      (warning?'<div class="notice warn">⚠ 1着上位3艇の中に、正式固定の買い目では1・2着の両方に登場しない艇があります。別モデル間の不整合候補として記録し、無条件の追加はしません。</div>':'')+
      '<p class="help">相対評価は120通りの条件付き展開を着順ごとに合算した未校正のモデル重みで、実測的中確率ではありません。10/29以降の上限は20点（4〜20点）、過去の従来版は4〜12点、10/28のv1.5は点数枠なし。2着候補は別途攻め・追走・差しの成立条件を要します。固定買い目や正式収支は変更しません。</p>'+
      '</div>';
  }
  // Read-only research-only exterior conditional model, separate from official tickets.
  function outsideRoleTrialPanel(r,baseline){
    let study;
    try{study=window.BoatTacticalModel?.forecastOutsideRole(r)}
    catch(e){return '<div class="notice warn">外枠研究モデルの評価失敗：'+escape(e.message)+'</div>';}
    if(!study)return '<p class="muted text-sm">外枠研究v0.5は未読込です。アプリを再読込してください。</p>';
    const info=study.metadata?.outside_v05||{};
    const evidence=info.conditional_outside_evidence||[];
    const oldFirst=baseline?.head_course_shares||[];
    const mark=(c)=>c>=4?'外枠 '+c+'コース':'内側 '+c+'コース';
    const outsideRows=evidence.map((a)=>{
      const lane=study.head_course_shares.find(x=>x.course===a.course)?.lane;
      const before=oldFirst.find(x=>x.course===a.course)?.relative_share;
      const after=study.head_course_shares.find(x=>x.course===a.course)?.relative_share;
      const coverage=study.role_coverage?.[lane]||{};
      const attack=a.attack&&a.confidence>=.10;
      return '<tr><th>'+escape(lane||a.course)+'号艇<br><small>'+escape(mark(a.course))+'</small></th>'+
       '<td>'+(attack?'<b class="outer-evidence-good">攻め条件あり</b>':'攻め根拠不足')+'</td>'+
       '<td>'+(a.following_supported?'外の追走あり':'連動未確認')+'</td>'+
       '<td>'+((before??0)*100).toFixed(1)+' → '+((after??0)*100).toFixed(1)+'</td>'+
       '<td>'+escape(coverage.headTickets??0)+' / '+escape(coverage.secondTickets??0)+' / '+escape(coverage.thirdTickets??0)+'</td></tr>';
    }).join('');
    const oldSet=(baseline?.bets||[]).map(x=>x.combination);
    const added=study.bets.map(x=>x.combination).filter(x=>!oldSet.includes(x));
    const removed=oldSet.filter(x=>!study.bets.some(b=>b.combination===x));
    const stats=info.venue_specific_prior?'この会場の公式コース統計（2026年7〜9月）を35%だけ参照':
      'この会場の6コース別公式統計は未設定。従来の全国仮説値を暫定使用';
    return '<section class="outer-role-study" aria-label="外枠を条件付きで評価した別モデル">'+
      '<h3>🌊 外枠の過小評価を再検証｜v0.5</h3>'+
      '<p>全艇同じ条件で比較。④⑤⑥の能力・展示・進入と<strong>攻め成立／外の追走</strong>を別々に判定。外枠だからという理由だけで買い目に追加しません。</p>'+
      '<div class="outer-study-meta"><span>'+escape(stats)+'</span>'+
      '<span>従来v0.4 '+escape(baseline?.top||'—')+' → 外枠v0.5 '+escape(study.top||'—')+'</span></div>'+
      '<div class="boat-entry-overflow"><table class="bets-table outer-study-table"><thead><tr>'+
      '<th>艇・進入</th><th>攻め</th><th>隣艇連動</th><th>1着相対評価<br>v0.4 → v0.5</th><th>v0.5採用点数<br>1/2/3着</th>'+
      '</tr></thead><tbody>'+outsideRows+'</tbody></table></div>'+
      '<p class="outer-study-summary">変更候補：追加 '+escape(added.join('、')||'なし')+
      ' ／ 除外 '+escape(removed.join('、')||'なし')+'</p>'+
      '<p class="outer-study-foot">これは未訓練・確率未校正の試験。新モデルの正式BUY成績には未計上。外枠は不利ゼロではありません。判断に使った数値は発走前に保存された出走・展示情報のみ。結果や払戻では予想を後から変えません。</p>'+
      '</section>';
  }
  // New v0.6 is a visible shadow calculation, NEVER an edit to frozen bets.
  function coupledTrialPanel(r,closed){
    let model;
    try{model=window.BoatTacticalModel?.forecastCoupled?.(r);}
    catch(e){return '<div class="notice warn">6艇連動の試験計算を保留：'+escape(e.message)+'</div>';}
    if(!model)return '';
    const graph=model.metadata?.coupled_v06?.interaction_graph||[];
    const rows=graph.filter(x=>x.head_course>=3).map(x=>{
      const inside=x.inside.filter(v=>v.risk>.1).map(v=>v.lane+'号艇').join('、')||'明確な押し下げは未推定';
      const follow=x.follower_course&&x.pressure>.1&&x.follower_readiness>.4?
        x.follower_lane+'号艇（'+x.follower_course+'コース）':'連動根拠が弱い';
      return '<tr><td><b>'+escape(x.head_lane)+'号艇</b>（'+x.head_course+'コース）</td>'+
        '<td>'+escape(x.tactic)+'</td>'+
        '<td>'+inside+'</td><td>'+escape(follow)+'</td></tr>';
    }).join('');
    const picks=model.bets.map(b=>
      '<tr><td><b>'+escape(b.combination)+'</b></td><td>'+escape(b.conditional_reason)+'</td>'+
      '<td>'+money(b.virtual_yen)+'</td></tr>').join('');
    return '<details class="card card-pad boat-coupled-study" style="margin:12px 0">'+
      '<summary style="cursor:pointer;font-weight:900">🚤 6艇の攻防・追走・着残り｜連動モデル v0.6（試験）</summary>'+
      '<p class="muted text-sm">進入 → スタート → 1Mの攻め → 内艇の失速・残存 → 外艇の追走 → 2・3着の成立条件をつなげる仮説。数値は実測進路・学習済み確率ではありません。</p>'+
      (closed?'<div class="notice warn"><b>締切後の事後参考計算。発走前固定済み予想には加えません。</b></div>':
        '<div class="notice">この画面での計算は未固定の参考試算。正式記録と分離しています。</div>')+
      '<div class="boat-entry-overflow"><table class="bets-table"><thead><tr>'+
      '<th>仕掛け艇</th><th>攻め方の仮説</th><th>影響を受ける内艇</th><th>追走候補</th>'+
      '</tr></thead><tbody>'+rows+'</tbody></table></div>'+
      '<p><b>v0.6の想定3連単：'+escape(model.bets.length)+'点・仮想50,000円</b>（結果・配当は入力しません）</p>'+
      '<div class="boat-entry-overflow"><table class="bets-table"><thead><tr><th>3連単</th><th>艇の連動・着順条件</th><th>仮想配分</th>'+
      '</tr></thead><tbody>'+picks+'</tbody></table></div>'+
      '<p class="muted text-sm">比較用v0.5と同じ事前情報で検証する研究モデル。結果判明後に同じ日の買い目を更新しません。前付けの可能性があれば展示進入の確認が先です。</p>'+
      '</details>';
  }
  // Shadow-v0.7: actual lane/course and pre-race ST estimates, never outcomes.
  function startGapTrialPanel(r,closed){
    let trial;
    try{trial=window.BoatTacticalModel?.forecastOutsideStart?.(r);}
    catch(error){return '<div class="notice warn">ST連動v0.7の評価を保留：'+escape(error.message)+'</div>';}
    if(!trial)return '';
    const signals=trial.metadata?.start_v07?.slit_signals||[];
    const rows=signals.filter(s=>s.course>=4).map(s=>{
      const role=trial.role_coverage?.[s.lane]||{};
      const gap=s.nearest_gap_sec;
      const state=!Number.isFinite(gap)?'根拠不足':gap>=.03?'内側より先行傾向':gap<=-.03?'内側より出遅れ傾向':'大差なし';
      const predicted=s.head_evidence?'1着攻め候補':s.second_evidence?'2着残存候補':'STによる加点なし';
      const second=trial.metadata.start_v07.second_given_inside_first
        .find(x=>x.course===s.course)?.conditional_relative_weight;
      return '<tr><td>'+escape(s.lane)+'号艇 <small>（'+s.course+'コース）</small></td>'+
        '<td>'+escape(s.estimated_st==null?'未取得':s.estimated_st.toFixed(3))+'</td>'+
        '<td>'+escape(gap==null?'比較不可':(gap>=0?'+':'')+gap.toFixed(3)+'秒')+'</td>'+
        '<td>'+escape(state)+' / '+escape(predicted)+'</td>'+
        '<td>'+escape(second==null?'—':(second*100).toFixed(1)+'%')+'</td>'+
        '<td>'+escape(role.headTickets??0)+' / '+escape(role.secondTickets??0)+'</td></tr>';
    }).join('');
    const changed=trial.bets.map(b=>
      '<tr><td><b>'+escape(b.combination)+'</b></td>'+
      '<td>'+escape(b.conditional_reason)+'</td><td>'+money(b.virtual_yen)+'</td></tr>').join('');
    return '<details class="card card-pad boat-start-gap-study" style="margin:12px 0">'+
      '<summary style="cursor:pointer;font-weight:900">⚡ ④⑤⑥の1・2着｜ST・まくり／まくり差し v0.7（試験）</summary>'+
      '<p class="muted text-sm">展示ST・平均STから想定スリット隊形を推定。正の差は外艇の事前先行仮説（実際の本番STではない）。展示Fを速いSTとして扱わず、進入コース順で比較します。展示前は進入も暫定です。</p>'+
      (closed?'<div class="notice warn">締切後の表示は参考試算。正式発走前予想と区別します。</div>':
        '<div class="notice">発走前でも画面内は未固定試験計算。正式BUYと分けます。</div>')+
      '<div class="boat-entry-overflow"><table class="bets-table"><thead><tr>'+
      '<th>艇・進入コース</th><th>推定ST秒</th><th>直内艇との差</th><th>スタート攻め評価</th><th>①逃げ時の2着相対重み</th><th>買い目採用<br>1着 / 2着</th>'+
      '</tr></thead><tbody>'+rows+'</tbody></table></div>'+
      '<p><b>v0.7の参考3連単：'+trial.bets.length+'点／仮想50,000円</b></p>'+
      '<div class="boat-entry-overflow"><table class="bets-table"><thead><tr>'+
      '<th>3連単</th><th>スタート → 1M → 着順の仮説</th><th>仮想配分</th>'+
      '</tr></thead><tbody>'+changed+'</tbody></table></div>'+
      '<p class="muted text-sm">①逃げ時の2着相対重みは1コースの艇が勝つと仮定した場合の未校正値。④⑤⑥が頭になる評価とは別に算出。条件の合わない外艇は自動採用しません。まくり・まくり差しの成立確率は未校正。本番STや実際の進路を観測したものではありません。</p>'+
      '</details>';
  }
  // The frozen same-time old Python model, NOT a recalculation after the result.
  function legacyControlPanel(r){
    const old=r?.legacy_control;
    if(r.model_role!=='main'||!old?.bets?.length)return '';
    const frozen=r.bets[0]?.combination||'—';
    const previous=old.bets[0]?.combination||'—';
    const settlement=recordFor(r);
    const oldHit=settlement&&old.bets.some(b=>b.combination===settlement.finish);
    const oldMatch=settlement&&old.bets.find(b=>b.combination===settlement.finish);
    const oldPaid=oldMatch?.virtual_yen*settlement?.payout_per_100/100||0;
    return '<details class="card card-pad legacy-model-compare" style="margin:12px 0">'+
      '<summary style="cursor:pointer;font-weight:900">🔬 旧モデルの検証用買い目（比較用・正式買い目ではありません）</summary>'+
      '<p>メイン '+escape(r.model_version||'不明')+'：<b>'+escape(frozen)+'</b> ／ 旧モデル：<b>'+escape(previous)+'</b>。旧式は正式な払戻・BUY収支には加算しません。</p>'+
      '<p class="muted text-sm">旧モデル：'+escape(old.model_version||'不明')+
      ' ／ 固定時刻 '+escape(old.frozen_at_utc||'不明')+
      ' ／ 照合SHA '+escape((old.sha256||'').slice(0,16))+'…</p>'+
      '<div class="boat-entry-overflow"><table class="bets-table"><thead><tr><th>旧買い目</th><th>仮想配分</th></tr></thead><tbody>'+
      old.bets.map(b=>'<tr><td>'+escape(b.combination)+'</td><td>'+money(b.virtual_yen)+'</td></tr>').join('')+
      '</tbody></table></div>'+
      (settlement?'<div class="notice">'+(oldHit?'旧モデルも的中':'旧モデルは不的中')+
       ' ／ 旧仮想払戻 '+money(oldPaid)+'（比較用で二重計上しません）</div>':
       '<p class="muted text-sm">公式照合待ち。結果が出たあとも保存済みの買い目は変更しません。</p>')+
      '</details>';
  }
  function tacticalTrialPanel(r){
    if(r?.entry_exhibition_gate?.entry_watch && !r.entry_exhibition_gate.final_eligible)
      return '<div class="notice warn">⚠ 前付け警戒：6艇の展示進入が確認できるまで、戦法再計算の買い目は最終候補として表示しません。</div>';
    let trial=null;
    try{trial=window.BoatTacticalModel?.forecastRoleAware(r)}catch(err){
      return '<div class="notice warn">展開試験版を計算できません：'+escape(err.message)+'</div>';
    }
    if(!trial)return '<div class="notice warn">展開試験版の読み込みがありません。アプリを更新してください。</div>';
    const dated=(data?.event_date||'')+'T'+r.cutoff_jst+':00+09:00';
    const closed=Date.now()>=new Date(dated).getTime()-120000;
    const original=r.bets.map(b=>b.combination).join(', ');
    const newTop=trial.top,oldTop=r.bets[0]?.combination;
    const changed=trial.differs_from_frozen;
    const heads=trial.head_course_shares
      .filter(h=>h.relative_share>=.07)
      .sort((a,b)=>b.relative_share-a.relative_share).slice(0,5);
    return '<section class="card card-pad boat-tactical-trial" aria-label="着順別の評価整合性を検証する試験買い目">'+
      '<div class="section-head"><div><h2 class="section-title">🧠 試験｜着順役割整合型 v0.4</h2>'+
      '<p class="boat-sim-mini">能力×モーター×展示×場別条件 → 逃げ/差し/まくり差し分岐 → 2・3着残存</p></div>'+
      '<span class="boat-sim-tag">新しい別モデル</span></div>'+
      '<div class="tactical-warning">'+
      (closed?'<b>締切後の研究計算です。事前に固定した予想ではありません。</b>':
              '<b>現時点の試験再計算です。正式な発走前固定予想とは別です。</b>')+
      '<p>事前保存の選手・機体・展示データだけを使い、結果・払戻・オッズは不使用。実測的中確率ではありません。正式のBUY収支にも加えません。</p></div>'+
      '<div class="tactical-compare"><div><small>従来の固定本線</small><strong>'+escape(oldTop)+'</strong></div>'+
      '<span>→</span><div><small>役割整合型v0.4研究本線</small><strong>'+escape(newTop)+'</strong></div>'+
      '<span class="tactical-change">'+(changed?'買い目・配分に違いあり':'比較結果：同じ配分')+'</span></div>'+
      '<div class="tactical-heads"><strong>1着戦法の相対評価（未校正）</strong>'+
      heads.map(h=>'<span>'+escape(h.lane)+'号艇：'+escape(h.tactic)+' '+(h.relative_share*100).toFixed(1)+'%</span>').join('')+
      '</div>'+roleConsistencyPanel(r,trial)+outsideRoleTrialPanel(r,trial)+coupledTrialPanel(r,closed)+startGapTrialPanel(r,closed)+'<div class="boat-entry-overflow"><table class="bets-table tactical-bets"><thead><tr><th>3連単</th><th>頭の勝ち筋</th><th>仮想配分</th></tr></thead><tbody>'+
      trial.bets.map(b=>'<tr><td><strong>'+escape(b.combination)+'</strong></td>'+
      '<td>'+escape(b.scenario)+'</td><td>'+money(b.virtual_yen)+'</td></tr>').join('')+
      '</tbody></table></div><p class="tactical-foot">試験 '+trial.bets.length+'点／仮想5万円。'+
      '元の固定 '+r.bets.length+'点／仮想5万円は下部に残して比較可能。'+
      'アニメでは「1M研究候補」を選ぶと展開を表示できる。'+
      '選手×モーターの相性や調整後の改善度は取得不足のため、独立補正としては未反映。</p></section>';
  }
  function detail(r) {
    const w=weatherFor(r.venue,r.cutoff_jst),c=compute(r);
    const external=window.BoatExternalReference;
    const externalUrl=external?external.linkFor(r.venue,data.event_date,r.race):'https://boaters-boatrace.com/race';
    const predictionUrl=external?external.predictionLinkFor(r.venue,data.event_date,r.race):'https://boaters-boatrace.com/race';
    const recalc=window.BoatReanalysis;
    const directStatus=window.BoatOriginalExhibitionDirect?.status(r,data.event_date)||{state:'idle'};
    const autoMetrics=recalc?.autoExtra?.(r,window.BoatExhibitionAudit?.metricsFor?.(r),
      window.BoatOriginalExhibitionDirect?.get?.(r,data.event_date));
    const filledMetrics=recalc?.mergeInput?.(autoMetrics?.values,state.reanalysisExtras)||state.reanalysisExtras;
    const originalRefreshLabel=directStatus.state==='ready'?'直接取得済み':directStatus.state==='loading'?'直前CSVを確認中':directStatus.state==='unpublished'?'直前CSV未公開':directStatus.state==='error'?'直接取得失敗':directStatus.state==='cutoff'?'締切後・新規取得停止':'直接取得未確認';
    const exhibitionUrl=external?.exhibitionLinkFor(r.venue,data.event_date,r.race)||externalUrl;
    const modelKey=data.event_date+'|'+r.venue+'|'+r.race+'|'+(r.sha256||'sample');
    const stored=state.reanalysisResult?.key===modelKey?state.reanalysisResult:null;

    const compare=r.exhibition_change;
    const provenance=r.exhibition_origin;
    const exhibitionDetail = r.phase==='exhibition' ? (
      '<section class="card card-pad bottom-margin" aria-label="展示による買い目再計算">'+
      '<h3>🔄 展示情報を反映した再計算</h3>'+
      '<p><strong>展示の取得元：</strong>'+escape(provenance?.source||'従来の非公式API')+
      '　<strong>展示の公開記録：</strong>'+escape(provenance?.observed_at_jst||'時刻未取得')+'</p>'+
      (compare ? '<div class="notice '+(compare.bets_changed?'':'warn')+'">'+
       '<strong>'+(compare.bets_changed?'買い目・配分に変更あり':'再計算済み：買い目・配分は維持')+'</strong>'+
       '<p>前回 '+escape(compare.previous_top)+' → 展示後 '+escape(compare.new_top)+
       '　/　'+escape(compare.previous_point_count)+'点 → '+escape(compare.new_point_count)+'点</p>'+
       '<p>追加：'+escape(compare.added.join('、')||'なし')+'　除外：'+escape(compare.removed.join('、')||'なし')+'</p>'+
       '<p>配分変更：'+(compare.allocation_changed?'あり':'なし')+'。'+
       (compare.bets_changed?'展示で変化した相対評価に基づく暫定変更です。':
        '展示値を反映しても上位の組み合わせが維持されたため、無理に変更していません。')+'</p></div>' :
       '<p>旧版の展示予想のため、買い目比較記録はありません。</p>')+
      '<div class="tablewrap"><table class="bets-table"><thead><tr><th>艇</th><th>展示ST</th><th>展示タイム</th><th>進入</th><th>一周・回り足・直線</th><th>相対評価</th></tr></thead><tbody>'+
      (r.racers||[]).map(x=>'<tr><td>'+escape(x.lane)+'</td><td>'+escape(x.exhibition_st??'—')+'</td>'+
       '<td>'+escape(x.exhibition_time??'—')+'</td><td>'+escape(x.course??'—')+'</td>'+
       '<td>'+escape(Object.entries(x.original_exhibition||{}).map(([key,val])=>key+': '+val).join(' / ')||'未取得')+'</td>'+
       '<td>'+escape(x.relative_weight??'—')+'</td></tr>').join('')+
      '</tbody></table></div><p class="muted text-sm">数値は未学習・未校正の試験評価。結果・払戻は予想計算に不使用。</p></section>'
    ) : '<div class="notice warn">展示前の固定予想です。展示情報が締切前に揃えば、別バージョンとして再計算・保存します。取得が遅れた場合、締切後に買い目を書き換えません。</div>';

    const referencePanel=`<section class="external-reference-card" aria-label="予想情報の確認と展開再評価">
      <div class="external-header"><div><span class="external-eyebrow">EXHIBITION · RACE INTELLIGENCE</span><h2>🚤 展示情報を見て予想を強化</h2></div><span class="external-status">試験モデル</span></div>
      <p>出走表・モーター・ST・展示タイムを使って<strong>1着の勝ち筋 → 2着の浮上 → 3着残存</strong>の順番で3連単を組み直します。外部サイトを無断で読み取ることはしません。</p>
      <div class="external-action-row">
        <a class="external-btn external-btn-primary" href="${escape(exhibitionUrl)}" target="_blank" rel="noopener noreferrer">↗ BOATERSの展示項目を見る</a>
        <a class="external-btn external-btn-white" href="${escape(externalUrl)}" target="_blank" rel="noopener noreferrer">↗ 出走表・モーターを確認</a>
        <button type="button" class="external-btn external-btn-white" data-action="analyze-saved-race" aria-expanded="${state.showExternalAnalysis?'true':'false'}">${state.showExternalAnalysis?'✕ 再評価画面を閉じる':'🧠 展開を再評価する'}</button>
      </div>
      ${state.showExternalAnalysis ? `<div class="recalc-workbench">
        <div class="recalc-data-status"><span>勝率・モーター・平均ST：${r.racers?.length===6?'取得済み':'未取得'}</span><span>展示タイム：${r.phase==='exhibition'?'取得済み':'未取得'}</span><span>1周・回り足・直線：自動入力 ${Object.values(autoMetrics?.complete||{}).filter(Boolean).length}/3項目（6艇揃い）</span></div>
        <div class="recalc-direct-status" role="status" aria-live="polite"><div><strong>📡 オリジナル展示：${escape(originalRefreshLabel)}</strong><p>${escape(directStatus.message||'画面を開くと対象レースの展示CSVを直接確認します。')}${directStatus.data?.source_observed_jst?' ／ データ元の記録 '+escape(directStatus.data.source_observed_jst):''}</p></div><button type="button" class="external-btn external-btn-white" data-action="refresh-original-exhibition" ${directStatus.state==='loading'?'disabled':''}>↻ 今すぐ取得</button></div>
        ${recalc?recalc.inputForm(r,filledMetrics,autoMetrics):'<p>再評価モジュールを読み込めませんでした。</p>'}
        <button type="button" class="external-btn external-btn-primary recalc-run" data-action="run-reanalysis">🧠 取得済みデータで取得済みデータで再予想を実行（参考・旧方式4〜12点）</button>
        <p class="recalc-execute-notice" role="status" aria-live="polite">${escape(state.reanalysisNotice||'タップすると表示中の6艇データを使って、この端末で試算します。')}</p>
        ${stored && recalc?recalc.resultHTML(stored.result,stored.afterCutoff):''}
      </div>` : ''}
      <p class="external-footnote">BOATERSが掲載する独自展示指標は、元の競艇場公式でも公開されることがあります。データ利用条件を確認し、許可された提供元から取り込む方針です。<strong>この機能はBOATERSから自動取得したものではありません。</strong>この端末内の手動再評価では、固定済み買い目を変更しません。</p>
    </section>`;
    const mainTicketSection = `<section class="card card-pad"><div class="section-head"><h2 class="section-title">${escape(ticketLabel(r))}／3連単フォーメーション</h2>${pill(`${r.bets.length}点 / 仮想`,'pending')}</div><div class="feature-card"><span class="feature-label">SCENARIO / 展開の中心</span><strong>${escape(r.scenario)}</strong><p>着順連動型の仮説。1着の勝ち筋と2・3着の残り方を検証する。</p></div><table class="bets-table"><thead><tr><th>評価</th><th>3連単</th><th>仮想金額</th></tr></thead><tbody>${r.bets.map((b,i)=>`<tr class="${i<3?'top-bet':''}"><td>${i<3?'本線':i<6?'対抗':'穴'}</td><td>${escape(b.combination)}</td><td class="amount">${money(b.virtual_yen)}</td></tr>`).join('')}</tbody></table><div class="detail-total"><span>合計 / ${r.bets.length}点</span><strong>${money(c.stake)}</strong></div><div class="notice warn">実際の購入は0円。${r.phase==='exhibition'?'展示は取得時点の値を反映。':'展示は未反映。'} オッズは未反映。この金額は精度比較用の仮想配分です。</div></section>`;
    const ticketBlock=isFormalTicket(r)?mainTicketSection:`<details class="ticket-provisional"><summary>暫定買い目を参考表示する（正式買い目ではありません）</summary>${mainTicketSection}</details>`;
    return `<button class="back-btn" data-action="back-races">← レース一覧へ戻る</button>
     ${window.BoatMobileRaceNav?.racePicker(r.venue,r.race,data.forecast_races,data.unforecast_races)||''}
     <div class="detail-header"><div><div class="page-eyebrow">FORECAST DETAILS / ${escape(data.event_date)}</div><h1 class="detail-title">${escape(r.venue)} ${r.race}R <span style="font-size:17px;vertical-align:middle">${pill(r.classification)}</span></h1><div class="detail-sub">締切予定 ${escape(r.cutoff_jst)} JST　 ·　 ${r.phase==='exhibition'?'展示数値反映':r.phase==='baseline'?'展示前':'保存済み'}・結果未使用</div></div><button class="btn btn-primary" data-action="copy-bets" data-race="${escape(r.venue)}|${r.race}">${isFormalTicket(r)?'⎘ 正式買い目をコピー':'⎘ 暫定買い目をコピー'}</button></div>
    ${ticketBanner(r)}
    ${window.BoatFourFactor?.panel(r)||''}
    ${window.BoatHeadShareChart?.render(r)||''}
    ${ticketBlock}
    ${r.model_version==='four-factor-v1.5-point-free-untrained'&&r.point_free_control?.generated_pre_cutoff&&r.point_free_control.frozen_at_utc===r.frozen_at_utc?'<section class="card card-pad"><details><summary>同じ入力の従来版と比較（検証用）</summary><p>点数枠なし '+r.bets.length+'点 ／ 従来版 '+r.point_free_control.bets.length+'点。各方式の仮想総額は5万円。以下は比較用で、追加の正式投資ではありません。</p><table class="bets-table"><thead><tr><th>従来版の買い目</th><th>仮想配分</th></tr></thead><tbody>'+r.point_free_control.bets.map(b=>'<tr><td>'+escape(b.combination)+'</td><td>'+b.virtual_yen.toLocaleString('ja-JP')+'円</td></tr>').join('')+'</tbody></table></details></section>':''}
    ${window.BoatStatisticalShadow?.placeholder(r)||''}
    ${r.model_role==='main'?'<div class="notice"><strong>採用モデル '+(r.model_version==='four-factor-v1.5-point-free-untrained'?'点数枠なしv1.5：組合せ評価 → 採否 → 点数 → 配分（試験）':r.model_version==='four-factor-v1.4-venue-aware-23-untrained'?'場別23場v1.4：決まり手傾向＋選手能力・合法ST・展示／2・3着連動を試験':r.model_version==='four-factor-v1.3-conditional-scenarios-untrained'?'四要素v1.3：展示による外攻め・内残り分岐を試験':r.model_version==='four-factor-v1.2-head-coverage-untrained'?'四要素v1.2：頭候補を保持／選手60 × モーター25 × 展示10 × 気象5':r.model_version==='four-factor-v1.1-untrained'?'四要素v1.1：選手60 × モーター25 × 展示10 × 気象5／2・3着は全艇評価':r.model_version==='four-factor-v1.0-untrained'?'四要素v1.0：選手60 × モーター25 × 展示10 × 気象5':r.model_version?.includes('v0.9')?'v0.9：ST差 × 6艇連動 × 1M・2M引き波評価':'v0.7：スタート差 × 6艇連動')+'</strong>。正式・暫定の区分は上の表示を確認してください。旧方式は比較用です。</div>':
      '<div class="notice warn">過去に固定した旧モデルの予想（当時の買い目・SHAを維持）。新モデルへ事後書き換えしません。</div>'}
    ${r.phase?`<div class="notice">${escape(r.evidence||'')} ・ 発走前保存 ${escape(r.frozen_at_utc||'未記録')} ・ SHA256 ${escape((r.sha256||'').slice(0,18))}…${r.weather_observed?`<br>場内風速 ${escape(r.weather_observed.wind_speed)}m/s ／ 波高 ${escape(r.weather_observed.wave_height)}cm（非公式・取得時点）`:''}<br>予想モデル：未学習・確率未校正。展示動画とオッズは未反映。</div>`:''}
    ${entryGateWarning(r)}
    ${venuePanel(r)}
    ${window.BoatExhibitionAudit?.panel(r)||''}
    ${exhibitionDetail}
    ${window.BoatRaceVisual?window.BoatRaceVisual.entryHTML(r):''}
     ${window.BoatRacerRatingPanel?.render(r)||''}
    ${r.model_role==='main'?legacyControlPanel(r):tacticalTrialPanel(r)}
    ${window.BoatRaceVisual?window.BoatRaceVisual.animationHTML(r):''}
    ${referencePanel}
    ${r.point_reason?`<div class="notice"><strong>点数を選んだ理由：</strong>${escape(r.point_reason)} ／ ${r.bets.length}点。これは未校正の相対指標で、実測的中確率ではありません。</div>`:''}
    <div class="detail-grid">
    <div><section class="card card-pad bottom-margin"><h3>レース情報</h3><div class="meta-list"><div class="meta"><span>開催</span><b>${escape(r.venue)}</b></div><div class="meta"><span>対象日</span><b>${dateDisplay(data.event_date)}</b></div><div class="meta"><span>締切予定</span><b>${escape(r.cutoff_jst)} JST</b></div><div class="meta"><span>予想区分</span><b>${escape(r.classification)}</b></div><div class="meta"><span>展示データ</span><b>${r.phase==='exhibition'?'反映済み（非公式）':'未反映'}</b></div><div class="meta"><span>オッズ</span><b>未反映</b></div></div></section>
    <section class="card card-pad bottom-margin"><h3>🌦 レース気象と試験補正</h3>${data.mode==='auto-live'?raceWeatherHTML(r):(w?`<div class="weather-box"><div class="weather-symbol">≋</div><div class="weather-body"><strong>${escape(w.wind)}</strong><p>${escape(w.note)}</p></div></div>`:'<p class="muted text-sm">気象見通し未登録</p>')}</section>
    <section class="card card-pad"><h3>結果照合</h3><div class="meta-list"><div class="meta"><span>現在の状態</span>${finishPill(r)}</div>${c.record?`<div class="meta"><span>${officialFor(r)?'公式確定着順':'手入力着順'}</span><b>${escape(c.record.finish)}</b></div><div class="meta"><span>仮想払戻</span><b>${money(c.payout)}</b></div>`:''}</div><button class="btn btn-soft" style="width:100%;margin-top:15px" data-action="settle-this" data-race="${escape(r.venue)}|${r.race}">照合する →</button></section></div></div>`;
  }
  function formatJst(iso) {
    if(!iso)return '未確認';
    const d=new Date(iso);
    if(Number.isNaN(d.getTime()))return '未確認';
    return d.toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',month:'numeric',day:'numeric',
      hour:'2-digit',minute:'2-digit',hour12:false})+' JST';
  }
  function resultsRefreshControl() {
    const imported=!!readJSON(STORE_DATA,null);
    const published=data?.updated_at_utc?formatJst(data.updated_at_utc):'未取得';
    const official=data?.official_pay_info;
    const officialAt=official?.retrieved_at_utc?formatJst(official.retrieved_at_utc):'未確認';
    const failed=official?.source_status==='FETCH_FAILED';
    const checked=Date.parse(official?.retrieved_at_utc||'');
    const stale=data?.mode==='auto-live'&&!imported&&
      (!Number.isFinite(checked)||Date.now()-checked>30*60*1000);
    const message=resultsRefreshNotice||(imported?
      '手動インポート中です。自動照合に戻すにはデータ管理で「元の予想に戻す」を選んでね。':
      stale?'公式結果の自動更新が遅れています。表示中の確認時刻以降の結果は未確認です。':
      '公式結果は自動で確認しています。ボタンでも最新の公開済みデータを再読み込みできます。');
    return `<div class="results-refresh" aria-label="公式結果の更新">
      <div class="results-refresh-main">
        <div class="results-refresh-copy"><strong>🔄 公式結果をチェック</strong>
          <span>公開データ更新 ${escape(published)} ／ 公式ページ確認 ${escape(officialAt)}</span></div>
        <button type="button" class="btn btn-primary results-refresh-button"
          data-action="refresh-official-results" ${resultsRefreshBusy?'disabled aria-busy="true"':''}>
          ${resultsRefreshBusy?'⏳ 更新を確認中…':'↻ 結果を更新'}
        </button>
      </div>
      <p class="results-refresh-status ${resultsRefreshIsError||stale?'is-error':''}" role="status" aria-live="polite">${escape(resultsRefreshBusy?'最新の公開データを取得しています…':message)}</p>
      ${failed?'<p class="results-refresh-hint">直近の自動収集では公式サイトへのアクセスに失敗しています。未確認レースは的中・不的中として計上しません。</p>':''}
      <p class="results-refresh-hint">全国予想の公開データと、公式払戻の検証済み日別データを別々に再取得します。公式サイトへ直接アクセスする機能ではありません。</p>
    </div>`;
  }
  function batchContext() {
    return {date:data.event_date,races:allRaces(),
      officialResults:{...batchOfficial,...autoResults},
      alerts:data.settlement_alerts||{}};
  }
  function persistBatchOfficial() {
    try{localStorage.setItem(STORE_BATCH_OFFICIAL,JSON.stringify(batchOfficial));return true;}
    catch{toast('公式一括照合の端末内保存に失敗しました');return false;}
  }
  function currentReaderContext(){
    const r=findRace(state.resultVenue,state.resultRace)||allRaces()[0];
    return r?{date:data.event_date,venue:r.venue,race:r.race,sha256:r.sha256}:null;
  }
  function quickResultBoard(races){
    return window.BoatResultQuickboard?.render(races,{
      date:data.event_date,officialFor,resultIssue,compute,
      officialUpdatedAt:data.official_pay_info?.retrieved_at_utc||data.updated_at_utc
    },{
      filter:state.resultQuickFilter,
      expanded:state.resultQuickExpanded,
      venue:state.resultVenue,
      race:state.resultRace
    })||'';
  }
  function resultsPage() {
    const races=allRaces();
    if(!races.length)return head('結果照合','公式払戻の一括確認ができます')+resultsRefreshControl()+(window.BoatCumulative?.render()||'')+
      (window.BoatBatchReader?.render(batchContext())||'')+
      '<div class="no-data">まだ発走前に固定した予想がないため、照合できる買い目はありません。公式一覧の掲載レースを確認することはできます。</div>';
    const r=findRace(state.resultVenue,state.resultRace)||races[0];
    const c=compute(r),settled=races.filter(x=>!!recordFor(x));
    const live=data.mode==='auto-live', verified=officialStats(races);
    const issue=resultIssue(r), hasOfficial=!!officialFor(r);
    const issues=Object.keys(data.settlement_alerts||{}).length;
    const reader=window.BoatResultReader;
    const readPanel=reader?reader.render({date:data.event_date,venue:r.venue,race:r.race,sha256:r.sha256}):'';
    const batchPanel=window.BoatBatchReader?.render({
      date:data.event_date,races,officialResults:{...batchOfficial,...autoResults},alerts:data.settlement_alerts||{}
    })||'';
    const officialUrl='https://www.boatrace.jp/owpc/pc/race/pay?hd='+data.event_date.replaceAll('-','');
    const header=live?`<div class="metrics" style="margin-bottom:16px">${metric('公式照合',verified.count+'R','公式払戻で検証済み','✓')}${metric('3連単的中',verified.hits+'R',verified.count?pct(verified.hitRate):'未確認','◎')}${metric('仮想回収率',verified.returnRate===null?'—':pct(verified.returnRate),'公式照合済みのみ','↗',verified.returnRate>=1?'positive':'')}${metric('仮想収支',verified.count?(verified.profit>=0?'+':'')+money(verified.profit):'—','正式BUYとは別','¥',verified.profit>=0?'positive':'negative')}</div><div class="notice">公式払戻：<a href="${escape(officialUrl)}" target="_blank" rel="noopener noreferrer">BOATRACE 本日の払戻金一覧 ↗</a> ／ ${issues}R 要確認。未公表・返還・レース中止は収支対象外。手入力は正式成績には算入しません。</div>`:'';
    const recent=settled.length?`<div class="result-list">${settled.slice().reverse().map(x=>{
      const result=compute(x),isOfficial=!!officialFor(x);
      return `<div class="result-item"><div><span class="text-xs muted">${escape(x.venue)} ${x.race}R ・ ${isOfficial?'公式確認':'手入力'}</span><div class="combo">${escape(result.record.finish)}</div><div class="sub">${money(result.record.payout_per_100)} / 100円</div></div><div class="status-end">${finishPill(x)}<strong class="${result.profit>=0?'positive':'negative'}">${result.profit>=0?'+':''}${money(result.profit)}</strong></div></div>`;
    }).join('')}</div>`:'<div class="no-data">未照合です。公式払戻が掲載されると自動反映されます。</div>';
    const selected=state.resultVenue, raceSelect=state.resultRace;
    const form=`<form id="result-form" class="result-form"><div class="form-row"><div class="field"><label for="result-venue">競艇場</label><select id="result-venue" class="select input">${getVenues().map(v=>`<option value="${escape(v)}" ${selected===v?'selected':''}>${escape(v)}</option>`).join('')}</select></div><div class="field"><label for="result-race">レース</label><select id="result-race" class="select input">${races.filter(x=>x.venue===selected).map(x=>`<option value="${x.race}" ${raceSelect===x.race?'selected':''}>${x.race}R</option>`).join('')}</select></div></div><div class="feature-card"><span class="feature-label">保存済み予想 / ${escape(r.classification)}</span><strong>${escape(r.bets.slice(0,3).map(b=>b.combination).join(' / '))}</strong><p>${escape(r.scenario)}</p></div><div class="field"><label for="finish">3連単（確定着順）</label><div class="form-row" style="gap:8px">${[0,1,2].map(i=>`<select id="finish-${i}" class="select input" style="width:calc(33.3% - 6px);min-width:0" aria-label="${i+1}着"><option value="">${i+1}着</option>${[1,2,3,4,5,6].map(n=>`<option value="${n}" ${c.record?.finish?.split('-')[i]===String(n)?'selected':''}>${n}号艇</option>`).join('')}</select>`).join('')}</div></div><div class="field"><label for="payout">3連単払戻（100円あたり）</label><input id="payout" class="input" inputmode="numeric" type="number" min="100" max="10000000" step="10" required placeholder="例：2430" value="${c.record?c.record.payout_per_100:''}"></div><p class="help">${hasOfficial?'公式結果を取得済み。手入力で変更はできません。':issue?'返還・中止・不一致があるため、手入力で収支を確定できません。':'公式結果未取得の場合だけ暫定的に手入力できます。公式照合済み成績には含みません。'}</p><button type="submit" class="btn btn-primary" ${hasOfficial||issue?'disabled':''}>${live?'暫定結果を保存':'結果を照合・保存'}</button>${results[raceKey(r)]&&!hasOfficial?'<button type="button" data-action="delete-result" class="btn btn-danger">手入力を取り消す</button>':''}</form>`;
    return `${head('結果照合',live?'BOATRACE公式払戻から自動照合・発走前予想は変更しません':'手入力の仮想照合',pill(live?verified.count+'R 公式確認':settled.length+'R 入力済み','local'))}${resultsRefreshControl()}${formalTicketPanel()}<p class="help">以下は全研究予想の参考成績（展示前の暫定を含む）です。</p>${header}${window.BoatCumulative?.render()||''}${quickResultBoard(races)}${batchPanel}<details class="individual-legacy"><summary>1Rずつの入力・読み取り（必要なときだけ）</summary>${readPanel}</details><div class="results-layout"><section class="card card-pad"><div class="section-head"><h2 class="section-title">${live?'レース結果の確認':'結果を入力'}</h2>${pill(hasOfficial?'公式確認済み':issue?'要確認':'未確認','local')}</div>${issue?`<div class="notice warn">このレースは${escape(issue.reason||'追加確認')}。自動の仮想収支には含めません。</div>`:''}${form}</section><section class="card card-pad"><div class="section-head"><h2 class="section-title">照合履歴</h2><span class="text-xs muted">${settled.length}R</span></div>${recent}</section></div>`;
  }
  function weaknessDiagnosis() {
    if(data.mode!=='auto-live')return '';
    const races=allRaces();
    const verified=races.filter(r=>!!officialFor(r)&&!resultIssue(r));
    const count=verified.length;
    const stages={hit:0,head_miss:0,second_miss:0,third_miss:0};
    let firstHeadOne=0,actualHeadOne=0;
    for(const r of verified){
      const result=officialFor(r),stat=compute(r);
      if(r.bets[0]?.combination[0]==='1')firstHeadOne++;
      if(result.finish[0]==='1')actualHeadOne++;
      const stage=stat.hit?'hit':!stat.headCaptured?'head_miss':
        !stat.firstSecond?'second_miss':'third_miss';
      stages[stage]++;
    }
    const coverage=races.length;
    const exhibition=races.filter(r=>r.phase==='exhibition').length;
    const newModel=races.filter(r=>r.model_version!=='heuristic-0.2-untrained').length;
    const counts=[
      ['頭抜け',stages.head_miss,'head'],
      ['2着の組合せ抜け',stages.second_miss,'second'],
      ['1・2着一致→3着抜け',stages.third_miss,'third'],
      ['3連単的中',stages.hit,'hit'],
    ];
    return `<section class="card card-pad weakness-panel">
      <div class="section-head"><h2 class="section-title">🔍 予想AIの弱点診断</h2>${pill(count+'R 公式照合済み','local')}</div>
      ${count?`<div class="weakness-grid">${counts.map(([label,n,kind])=>`<div class="weakness-tile weakness-${kind}">
        <span>${label}</span><strong>${n}R</strong><small>${(n/count*100).toFixed(1)}%</small></div>`).join('')}</div>
      <div class="weakness-keyline"><b>買い目筆頭が①頭 ${firstHeadOne}/${count}R</b><span>実際に①が勝ったのは ${actualHeadOne}/${count}R</span></div>
      <p class="help">頭候補に入っていても、2・3着が展開と合わず外れているレースを区別。買い目筆頭と実際の1着の比較は<strong>コース補正の偏りを発見するための指標</strong>で、他の頭を買い目から除いているという意味ではありません。</p>`:
      '<div class="notice">まだ公式照合済みレースがありません。予想の的中・不的中を推測して診断しません。</div>'}
      <div class="weakness-coverage">
        <span>発走前固定 <b>${coverage}/${data.listed_races||'—'}R</b></span>
        <span>展示まで反映 <b>${exhibition}/${coverage}R</b></span>
        <span>旧8点以外のモデル <b>${newModel}/${coverage}R</b></span>
      </div>
      <p class="help">仮想50,000円の研究用成績。発走前の固定買い目とBOATRACE公式で確認済みの結果のみ集計。新旧モデルは同じ条件で比較できる件数がまだ少ないため、精度改善は未確認です。</p>
    </section>`;
  }
  function analysis() {
    const live=data.mode==='auto-live';
    const metricStats=races=> {
      if(!live)return stats(races);
      const verified=officialStats(races);
      return {...verified,count:races.length,examined:verified.count};
    };
    const groups=getVenues().map(venue=>({
      venue,
      watch:metricStats(allRaces().filter(r=>r.venue===venue&&r.classification==='WATCH')),
      skip:metricStats(allRaces().filter(r=>r.venue===venue&&r.classification==='SKIP')),
      all:metricStats(allRaces().filter(r=>r.venue===venue))
    }));
    const total=metricStats(allRaces());
    const watchTotal=metricStats(allRaces().filter(r=>r.classification==='WATCH'));
    const skipTotal=metricStats(allRaces().filter(r=>r.classification==='SKIP'));
    const weatherTest=(data.weather_backtest||{}), weatherN=weatherTest.races||0;
    const ab=data.main_vs_legacy||{}, abN=ab.verified_comparisons||0;
    const legacyAnalysis='<section class="card card-pad" style="margin-bottom:16px">'+
      '<h2 class="section-title">⚔️ 当日のメインモデル 対 同時固定の旧モデル（検証専用）</h2>'+
      (abN?'<p>公式照合 <b>'+abN+'R</b> ／ メイン的中 <b>'+ab.main_hits+
       'R</b> ／ 旧モデル的中 <b>'+ab.legacy_hits+'R</b></p>'+
       '<p>メイン仮想回収率 <b>'+(100*ab.main_virtual_payout/ab.virtual_stake_per_model).toFixed(1)+
       '%</b> ／ 旧モデル仮想回収率 <b>'+(100*ab.legacy_virtual_payout/ab.virtual_stake_per_model).toFixed(1)+
       '%</b></p>':
       '<p class="muted">切替後の同時固定予想で、公式結果を照合できるレースはまだありません。</p>')+
      '<p class="help">旧モデルの払戻は比較専用で、メインの仮想収支へ二重計上しません。過去の固定記録を遡って再評価しません。未訓練・未校正です。</p></section>';
    const weatherCoverage=Number(data.weather_venue_count||Object.keys(data.venue_weather||{}).length);
    const weatherTestHtml=live?'<section class="card card-pad weather-test-analysis"><div class="section-head"><h2 class="section-title">🌦 気象補正あり・なしの発走前比較</h2></div>'+
      '<p class="help">開催場の周辺予報取得 '+weatherCoverage+'/'+(data.venues_with_races||'—')+'場。実際に気象を固定予想へ記録できたのは '+(data.weather_fixed_race_count??'集計前')+'Rです。過去の固定予想は後から変更していません。</p>'+
      (weatherN?'<div class="weather-ab-metrics"><span>公式照合 <b>'+weatherN+'R</b></span><span>気象あり的中 <b>'+weatherTest.weather_hits+'R</b></span><span>気象なし的中 <b>'+weatherTest.control_hits+'R</b></span></div>'+
       '<p class="help">仮想回収率：気象あり '+(100*weatherTest.weather_payout/weatherTest.virtual_stake_per_model).toFixed(1)+'% ／ 気象なし '+(100*weatherTest.control_payout/weatherTest.virtual_stake_per_model).toFixed(1)+'%（同一レース、事前固定買い目のみ）</p>':
       '<div class="notice">気象あり・なしを同条件で公式照合できたレースはまだありません。効果は未検証です。</div>')+
      '<p class="help">この比較は未校正の試験モデル。気象補正が的中率や回収率を改善する保証はありません。</p></section>':'';
    const metrics=total.examined?`${metric('検証済み',`${total.examined} R`,live?'公式払戻で確認済み':'手入力の結果のみ','✓')}${metric('3連単的中',`${total.hits} R`,pct(total.hitRate),'◎')}${metric('仮想回収率',pct(total.returnRate),'照合済みだけ','↗',total.returnRate>=1?'positive':'negative')}${metric('仮想収支',`${total.profit>=0?'+':''}${money(total.profit)}`,'正式BUYは別管理','¥',total.profit>=0?'positive':'negative')}`:`${metric('検証済み','0 R','まず結果照合を入力','✓')}${metric('3連単的中','—','未検証','◎')}${metric('仮想回収率','—','未検証','↗')}${metric('仮想収支','—','未検証','¥')}`;
    return `${head('成績分析',`${getVenues().length}場を比較 / 仮想5万円 × 保存済み${allRaces().length}R`)}${formalTicketPanel()}${window.BoatCumulative?.render()||''}<p class="help">以下は全研究予想の参考成績（展示前の暫定を含む）です。</p><div class="metrics">${metrics}</div>${legacyAnalysis}${weaknessDiagnosis()}${weatherTestHtml}<div class="columns-2"><section class="card card-pad"><div class="section-head"><h2 class="section-title">競艇場別の的中率</h2>${pill('検証済みのみ','local')}</div><div class="chart-grid">${groups.map(g=>`<div class="chart-item"><strong>${escape(g.venue)}</strong><div class="bar-back"><span class="bar-value" style="width:${g.all.examined?(100*g.all.hitRate).toFixed(1):0}%"></span></div><b>${g.all.examined?pct(g.all.hitRate):'—'}</b></div>`).join('')}</div><p class="charts-note">予想点数は保存モデル別（10/29以降4〜20点・過去の従来4〜12点・10/28のv1.5は点数枠なし）。仮想5万円で比較。的中率は${live?'BOATRACE公式確認済み':'結果入力済み'}レースのみが分母。</p><div class="notice">${total.examined?`頭候補捕捉 ${total.heads}/${total.examined}R、1・2着順一致 ${total.firstSeconds}/${total.examined}R、3着紐抜け ${total.thirdMiss}R。`:'まだ結果がないため、モデルの実力を判定できません。'}</div></section>
    <section class="card card-pad"><div class="section-head"><h2 class="section-title">WATCHとSKIPの比較</h2></div>${[['WATCH',watchTotal],['SKIP',skipTotal]].map(([name,s])=>`<div class="feature-card"><span class="feature-label">${name} · ${s.examined}/${s.count}R</span><strong>的中 ${s.hits}R${s.examined?' / '+pct(s.hitRate):''}</strong><p>仮想回収率 ${s.returnRate===null?'未算出':pct(s.returnRate)} ・ 収支 ${s.examined?money(s.profit):'未算出'}</p></div>`).join('')}<div class="notice warn">SKIPの仮想配分はベンチマーク用。実際に買ったと仮定した場合の数字で、正式な投資収支ではありません。</div></section></div>
    <div class="card card-pad" style="margin-top:18px"><div class="section-head"><h2 class="section-title">場別・モデル検証サマリー</h2></div><table class="bets-table"><thead><tr><th>場</th><th>照合</th><th>的中</th><th>仮想回収</th></tr></thead><tbody>${groups.map(g=>`<tr><td>${escape(g.venue)}</td><td>${g.all.examined}/${g.all.count}</td><td>${g.all.hits}R</td><td>${g.all.returnRate===null?'—':pct(g.all.returnRate)}</td></tr>`).join('')}</tbody></table></div><p class="footer-disclaimer">検証値には事後作成の予想を混ぜない。データの入手時刻と発走前固定を確認できる予想のみを、正式なモデル評価に使用します。</p>`;
  }
  function settings() {
    return `${head('データ管理',`予想データと結果を管理 / この端末のブラウザに保存`)}<div class="settings-grid"><section class="card settings-card"><span class="mini-caption">PREDICTION SOURCE</span><h2 class="section-title" style="margin:12px 0">発走前の固定データ</h2><p>${escape(state.origin)}。${data.mode==='auto-live'?'出走表・展示は非公式データ、結果・払戻はBOATRACE公式ページを参照。発走前に固定できたレースだけ照合しています。':'新しい予想の自動取得はまだありません。'}</p><div class="meta-list"><div class="meta"><span>対象日</span><b>${dateDisplay(data.event_date)}</b></div><div class="meta"><span>予想件数</span><b>${data.forecast_races.length}R</b></div><div class="meta"><span>モデル</span><b>${data.mode==='auto-live'?(data.forecast_races.some(x=>x.model_role==='main')?(data.forecast_races.some(x=>x.four_factor)?'保存時点の四要素モデル／v0.9比較用':'保存時点の主モデル／同時固定の旧モデル比較用'):'旧モデルの発走前記録（変更なし）'):'展示前・参考気象補正'}</b></div><div class="meta"><span>オッズ / 動画解析</span><b>未接続</b></div></div><div class="notice"><span class="mini-caption">GIT COMMIT</span><br><span class="code-ref">${escape(data.freeze_reference||'外部固定記録なし')}</span></div><div class="settings-btns" style="margin-top:14px"><a class="btn btn-soft" href="https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai" target="_blank" rel="noopener noreferrer">↗ GitHubを見る</a><button data-action="export-predictions" class="btn btn-white">↧ 予想JSON保存</button></div></section>
    <section class="card settings-card"><span class="mini-caption">LOCAL DATA</span><h2 class="section-title" style="margin:12px 0">結果をバックアップ</h2><p>入力した確定結果はブラウザ内だけに保存。機種変更やブラウザのデータ削除に備えてJSONで保存できるよ。</p><div class="settings-btns"><button data-action="export-results" class="btn btn-primary">↧ 結果CSVを書き出す</button><button data-action="export-backup" class="btn btn-white">↧ 結果JSON</button></div><p class="help" style="margin-top:16px">※ バックアップなしでブラウザを消去すると、結果入力も消える可能性があります。</p><div style="margin-top:24px"><label class="mini-caption" for="upload-dataset">将来の予想データを読み込む</label><input type="file" id="upload-dataset" class="input" accept="application/json,.json" style="margin-top:10px"><p class="help">BOAT LAB形式のJSONのみ。インポートしたデータは発走前固定の証明を伴わないため、正式成績としては扱えません。</p></div><div class="settings-btns" style="margin-top:15px"><button data-action="reset-dataset" class="btn btn-white">元の予想に戻す</button><button data-action="clear-results" class="btn btn-danger">入力した結果を全削除</button></div></section></div>
    <div class="card card-pad" style="margin-top:18px"><h2 class="section-title">開発ロードマップ</h2><div class="status-pills" style="margin-top:17px"><span class="tag">✓ レース・買い目一覧</span><span class="tag">✓ 仮想配分</span><span class="tag">✓ 結果照合</span><span class="tag">✓ 収支集計</span><span class="tag">✓ iPhone用画面</span></div><p class="footer-disclaimer">自動取得：出走表、展示ST・タイム・場内気象、非公式結果。未実装：動画AI、潮流実測補正、直前オッズ、正式BUY判断。実行・配信遅延で未予想のレースもあります。</p></div>`;
  }
  function render() {
    if (!data) return;
    const main=el('main');
    el('breadcrumb-label').textContent=titles[state.view];
    document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===state.view);if(b.dataset.view===state.view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    main.innerHTML=(window.BoatExhibitionAudit?.banner(data)||'')+
      ({overview,races,results:resultsPage,analysis,settings})[state.view]();
    if(['results','analysis'].includes(state.view)&&window.BoatCumulative?.needsRefresh?.()){
      void window.BoatCumulative.load().then(()=>{if(['results','analysis'].includes(state.view))render()}).catch(()=>{});
    }
    if(state.view==='races'&&state.raceDetail){
      window.BoatRaceVisual?.mount(main,state.raceDetail);
      void window.BoatStatisticalShadow?.mount(main,state.raceDetail,data.event_date);
    }
    else window.BoatRaceVisual?.dispose();
  }
  function refreshTimelineClock(){
    if(state.view!=='overview'||!data||document.hidden||!window.BoatRaceTimeline)return;
    const node=document.querySelector('.race-timeline');
    if(!node||node.contains(document.activeElement))return;
    // Refresh only the timeline. Never refetch, mutate a frozen prediction, or reset scroll.
    node.outerHTML=window.BoatRaceTimeline.render(data);
  }
  function go(view) {
    rememberNavigation();state.view=view;state.raceDetail=null;resetRaceWork();
    render();window.scrollTo({top:0,behavior:'instant'});
  }
  function toast(message){const node=el('toast');node.textContent=message;node.classList.add('show');if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('show'),3200);}
  function download(name,content,type='text/plain;charset=utf-8') {const blob=new Blob([content],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
  function exportResultsCSV(){const header=['date','venue','race','classification','cutoff_jst','finish','payout_per_100','is_hit','stake_yen','virtual_payout_yen','virtual_profit_yen','recorded_at','source'];const body=allRaces().map(r=>{let c=compute(r);return [data.event_date,r.venue,r.race,r.classification,r.cutoff_jst,c.record?.finish||'',c.record?.payout_per_100??'',c.record?Number(c.hit):'',c.record?c.stake:'',c.payout??'',c.profit??'',c.record?.recorded_at||'',c.record?(c.record.source||'manual'):''];});const csv=[header,...body].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n');download(`boatlab-results-${data.event_date}.csv`,'\uFEFF'+csv,'text/csv;charset=utf-8');toast('結果CSVを書き出したよ');}
  function copyBets(r){const s=`${data.event_date} ${r.venue} ${r.race}R ${r.cutoff_jst} [${r.classification}] ${ticketLabel(r)}（${r.bets.length}点）\n${r.scenario}\n${r.bets.map((b,i)=>`${i+1}. ${b.combination} ${money(b.virtual_yen)}`).join('\n')}\n合計 ${money(r.bets.reduce((s,b)=>s+b.virtual_yen,0))} / 研究用・仮想`;if(navigator.clipboard?.writeText)navigator.clipboard.writeText(s).then(()=>toast('買い目をコピーしたよ'),()=>toast('コピーできませんでした'));else {const t=document.createElement('textarea');t.value=s;document.body.append(t);t.select();document.execCommand('copy');t.remove();toast('買い目をコピーしたよ');}}
  document.addEventListener('click',e=>{
    const timelineFilter=e.target.closest('[data-timeline-filter]');
    if(timelineFilter&&window.BoatRaceTimeline){
      window.BoatRaceTimeline.setFilter(timelineFilter.dataset.timelineFilter);
      const node=document.querySelector('.race-timeline');
      if(node)node.outerHTML=window.BoatRaceTimeline.render(data);
      return;
    }
    const nav=e.target.closest('[data-view]');if(nav){
      rememberNavigation();
      if(nav.dataset.view==='races')state.venue='全場';
      state.view=nav.dataset.view;state.raceDetail=null;resetRaceWork();
      render();window.scrollTo(0,0);return;
    }
    const choice=e.target.closest('[data-select-race]');
    if(choice){
      if(choice.disabled)return;
      const token=choice.dataset.selectRace||'';
      const at=token.lastIndexOf('|'),venue=token.slice(0,at),number=Number(token.slice(at+1));
      const found=at>0&&Number.isInteger(number)?findRace(venue,number):null;
      if(found&&(!state.raceDetail||state.raceDetail.venue!==venue||state.raceDetail.race!==number))
        showRace(found);
      return;
    }
    const venueOpen=e.target.closest('[data-open-venue]');if(venueOpen){if(venueOpen.disabled)return;rememberNavigation();
      state.venue=venueOpen.dataset.openVenue;state.raceDetail=null;resetRaceWork();
      state.view='races';render();window.scrollTo(0,0);return;}
    const fav=e.target.closest('[data-favorite-venue]');if(fav){const name=fav.dataset.favoriteVenue;favorites=favorites.includes(name)?favorites.filter(x=>x!==name):favorites.concat([name]);try{localStorage.setItem(STORE_FAVORITES,JSON.stringify(favorites));}catch{}render();return;}
    const boardFilter=e.target.closest('[data-venue-filter]');if(boardFilter){state.boardFilter=boardFilter.dataset.venueFilter;render();return;}
    const quickFilter=e.target.closest('[data-result-filter]');
    if(quickFilter){
      state.resultQuickFilter=quickFilter.dataset.resultFilter||'recent';
      state.resultQuickExpanded=false;render();return;
    }
    const quickMore=e.target.closest('[data-result-more]');
    if(quickMore){
      state.resultQuickExpanded=quickMore.dataset.resultMore==='true';render();return;
    }
    const quickSelect=e.target.closest('[data-result-quick]')||e.target.closest('[data-result-next]');
    if(quickSelect){
      const token=quickSelect.dataset.resultQuick||quickSelect.dataset.resultNext||'';
      const last=token.lastIndexOf('|');
      if(last>0){
        const venue=token.slice(0,last),race=Number(token.slice(last+1));
        if(findRace(venue,race)){
          rememberNavigation();
          state.resultVenue=venue;state.resultRace=race;
          state.view='results';state.raceDetail=null;resetRaceWork();render();
        }
      }
      return;
    }
    const row=e.target.closest('[data-race]');if(row){const [v,n]=row.dataset.race.split('|');let r=findRace(v,n);if(!r)return;if(row.dataset.action==='settle-this'){state.resultVenue=v;state.resultRace=Number(n);go('results');return;}if(row.dataset.action==='copy-bets'){copyBets(r);return;}showRace(r);return;}
    const btn=e.target.closest('[data-action]');if(!btn)return;
    switch(btn.dataset.action){
      case 'batch-image-read':{
        const ctx=batchContext(),reader=window.BoatBatchReader;
        if(reader)void reader.readImage(ctx,()=>{if(state.view==='results')render()});
        break;
      }
      case 'batch-url-read':{
        const reader=window.BoatBatchReader;
        if(reader)void reader.readURL(el('batch-url')?.value||'',batchContext(),()=>{if(state.view==='results')render()});
        break;
      }
      case 'batch-text-read':{
        try{
          const text=el('batch-ocr-text')?.value||'';
          window.BoatBatchReader?.parseText(text,batchContext());render();
        }catch(e){toast(e.message||'テキストを読み取れませんでした');}
        break;
      }
      case 'batch-apply':{
        const reader=window.BoatBatchReader;
        if(!reader)break;
        try{
          const ctx=batchContext(),updates=reader.selectedUpdates(ctx,el('main'));
          const official=updates.filter(x=>x.kind==='url').length;
          const draft=updates.filter(x=>x.kind==='image').length;
          const ask=official?
            updates.length+'Rの公式確認済み結果を、この端末に一括反映する？':
            updates.length+'Rを画像からの暫定結果として保存する？ 公式の確定成績には加えないよ。';
          if(typeof confirm==='function'&&!confirm(ask))break;
          const at=new Date().toISOString();
          for(const item of updates){
            if(item.kind==='url'){
              batchOfficial[item.key]={finish:item.finish,payout_per_100:item.payout_per_100,
                source:'boatrace_official_pay',verified:true,snapshot_sha256:item.snapshot_sha256,
                source_url:item.source_url,recorded_at:item.source_timestamp||at,
                imported_from:'published_daily_official_pay_snapshot'};
            }else{
              results[item.key]={finish:item.finish,payout_per_100:item.payout_per_100,
                recorded_at:at,source:'image_ocr_unverified'};
            }
          }
          if(official)persistBatchOfficial();
          if(draft)persistResults();
          reader.clearResults(ctx);
          render();
          toast(official?official+'Rの公式結果を反映したよ':draft+'Rを暫定照合として保存したよ');
        }catch(e){toast(e.message||'一括照合できませんでした');}
        break;
      }
      case 'batch-clear':{
        window.BoatBatchReader?.clearResults(batchContext());render();break;
      }
      case 'read-result-image':{
        const reader=window.BoatResultReader,ctx=currentReaderContext();
        if(reader&&ctx)void reader.readImage(ctx,()=>render());
        break;
      }
      case 'read-result-url':{
        const reader=window.BoatResultReader,ctx=currentReaderContext();
        if(!reader||!ctx)break;
        reader.useUrl(el('result-official-url')?.value||'',ctx,autoResults,data.settlement_alerts||{});
        render();
        break;
      }
      case 'apply-result-read':{
        const reader=window.BoatResultReader,ctx=currentReaderContext();
        if(!reader||!ctx)break;
        const r=findRace(ctx.venue,ctx.race);
        if(!r||officialFor(r)||resultIssue(r)){toast('公式照合済み・要確認レースは上書きできません');break;}
        try{
          const v=reader.apply(ctx);
          if(!v){toast('読み取り結果を確認してね');break;}
          render();
          const digits=v.finish.split('-');
          for(let i=0;i<3;i++)if(el('finish-'+i))el('finish-'+i).value=digits[i];
          if(el('payout'))el('payout').value=String(v.payout_per_100);
          toast('候補を入力したよ。元画像と見比べて保存してね');
        }catch(error){toast(error.message||'読み取り候補を反映できませんでした');}
        break;
      }
      case 'refresh-official-results':void refreshOfficialResults();break;
      case 'reload-cumulative-results':{
        if(window.BoatCumulative){
          const job=window.BoatCumulative.load(true);
          render();
          void job.then(()=>{if(state.view==='results')render()}).catch(()=>{});
        }
        break;
      }
      case 'analyze-saved-race':state.showExternalAnalysis=!state.showExternalAnalysis;render();if(state.showExternalAnalysis)void refreshOriginalExhibition(false);break;
      case 'refresh-original-exhibition':void refreshOriginalExhibition(true);break;
      case 'run-reanalysis':{
        const r=state.raceDetail,engine=window.BoatReanalysis;
        if(!r||!engine){toast('再評価データがありません');break;}
        try{
          const extras={};
          for(const input of document.querySelectorAll('[data-recalc-lane][data-recalc-metric]')){
            const lane=Number(input.dataset.recalcLane),metric=input.dataset.recalcMetric;
            if(!Number.isInteger(lane)||lane<1||lane>6||!['lap_time','turn_time','straight_time'].includes(metric))continue;
            if(!extras[lane])extras[lane]={};
            if(input.value!==''&&input.value!=null)extras[lane][metric]=input.value;
          }
          const clean=engine.normalizeExtra(extras),estimate=engine.model(r,clean);
          const cutoff=Date.parse(data.event_date+'T'+r.cutoff_jst+':00+09:00');
          const afterCutoff=!Number.isFinite(cutoff)||Date.now()>=cutoff;
          state.reanalysisExtras=clean;
          state.reanalysisResult={key:data.event_date+'|'+r.venue+'|'+r.race+'|'+(r.sha256||'sample'),result:estimate,afterCutoff};
          state.reanalysisNotice=estimate.bets.length+'点の再予想を実行しました。仮想配分合計50,000円。下に計算結果を表示しています。';
          state.showExternalAnalysis=true;render();
          toast(afterCutoff?'締切後の参考試算を生成したよ':'展開を再評価したよ（試験用）');
        }catch(err){
          state.reanalysisNotice='実行できませんでした：'+(err?.message||'原因未確認');
          render();toast(err?.message||'再評価に失敗しました');
        }
        break;
      }
      case 'go-races':go('races');break;
      case 'back-races':{
        // Explicit back-to-list skips prior detail-to-detail hops in history.
        let list=null;
        while(navigationHistory.length){
          const previous=navigationHistory.pop();
          if(previous.view==='races'&&!previous.detailVenue){list=previous;break;}
        }
        if(list)restoreNavigation(list);
        else {state.view='races';state.raceDetail=null;resetRaceWork();render();window.scrollTo(0,0);}
        break;
      }
      case 'back-overview':state.venue='全場';go('overview');break;
      case 'export-results':exportResultsCSV();break;
      case 'export-predictions':download(`boatlab-predictions-${data.event_date}.json`,JSON.stringify(data,null,2),'application/json');toast('予想データを保存したよ');break;
      case 'export-backup':download(`boatlab-backup-${data.event_date}.json`,JSON.stringify({version:1,date:data.event_date,results},null,2),'application/json');toast('バックアップを書き出したよ');break;
      case 'reset-dataset':if(confirm('初期データに戻しますか？ 入力済みの結果は残ります。')){localStorage.removeItem(STORE_DATA);location.reload();}break;
      case 'clear-results':if(confirm('入力した結果をすべて削除します。この操作は元に戻せません。')){results={};persistResults();render();toast('結果データを削除しました');}break;
      case 'delete-result':{const r=findRace(state.resultVenue,state.resultRace);if(r&&confirm(`${r.venue} ${r.race}R の結果を取り消しますか？`)){delete results[raceKey(r)];persistResults();render();toast('入力を取り消しました');}break;}
    }
  });
  // Preserve user overrides (including deliberate clearing) while auto values refresh.
  document.addEventListener('input',e=>{
    const field=e.target?.closest?.('[data-recalc-lane][data-recalc-metric]');
    if(!field||!state.raceDetail||state.view!=='races')return;
    const lane=Number(field.dataset.recalcLane),metric=field.dataset.recalcMetric;
    if(!Number.isInteger(lane)||lane<1||lane>6||
       !['lap_time','turn_time','straight_time'].includes(metric))return;
    if(!state.reanalysisExtras[lane])state.reanalysisExtras[lane]={};
    state.reanalysisExtras[lane][metric]=field.value;
  });
  document.addEventListener('change',async e=>{
    if(e.target.matches('#batch-image')){
      try{window.BoatBatchReader?.imageSelected(e.target.files?.[0],batchContext());render();}
      catch(err){toast(err.message||'画像を選択できませんでした');}
      return;
    }
    if(e.target.matches('#batch-venue')){
      try{window.BoatBatchReader?.setVenue(e.target.value,batchContext());render();}
      catch(err){toast(err.message||'開催場が正しくありません');}
      return;
    }
    if(e.target.matches('#result-image-file')){
      const reader=window.BoatResultReader,ctx=currentReaderContext();
      if(!reader||!ctx)return;
      try{reader.fileSelected(e.target.files?.[0],ctx);render();}
      catch(error){toast(error.message||'画像を選択できませんでした');}
      return;
    }
    if(e.target.matches('[data-venue-sort]')){state.boardSort=e.target.value;render();return;}
    if(e.target.matches('[data-filter-venue]')){state.venue=e.target.value;render();}
    if(e.target.matches('#result-venue')){state.resultVenue=e.target.value;state.resultRace=1;render();}
    if(e.target.matches('#result-race')){state.resultRace=Number(e.target.value);render();}
    if(e.target.matches('#upload-dataset')){
      const file=e.target.files?.[0];if(!file)return;
      if(file.size>1024*1024){toast('1MB未満のJSONにしてね');return;}
      try{const parsed=normalizeData(JSON.parse(await file.text()));localStorage.setItem(STORE_DATA,JSON.stringify(parsed));data=parsed;results=readJSON(STORE_RESULTS,{});state.origin='利用者が読み込んだJSON（発走前固定・出典は未検証）';state.venue='全場';state.classification='ALL';state.resultVenue=getVenues()[0];state.resultRace=1;go('overview');toast(`${parsed.forecast_races.length}Rの予想データを読み込んだよ`);}catch(error){toast(`読み込みできません: ${error.message}`);}
    }
  });
  document.addEventListener('click',e=>{const b=e.target.closest('[data-filter-status]');if(b){state.classification=b.dataset.filterStatus;render();}});
  document.addEventListener('submit',e=>{
    if(e.target.id!=='result-form')return;e.preventDefault();
    const r=findRace(state.resultVenue,state.resultRace);if(!r)return;
    if(officialFor(r)||resultIssue(r)){toast('公式照合済み・要確認レースの手入力はできません');return;}
    const pos=[0,1,2].map(i=>el(`finish-${i}`)?.value||'');const finish=pos.join('-');const payout=Number(el('payout').value);
    if(!isCombo(finish)){toast('1〜3着は重複しない艇番を選択してね');return;}
    if(!Number.isSafeInteger(payout)||payout<100||payout>10000000||payout%10!==0){toast('3連単払戻は100〜10,000,000円の10円単位で入力してね');return;}
    results[raceKey(r)]={finish,payout_per_100:payout,recorded_at:new Date().toISOString(),source:'manual'};
    if(persistResults()){render();const result=compute(r);toast(result.hit?`的中！ 仮想払戻 ${money(result.payout)}`:'不的中。買い目を変更せずに記録したよ');}
  });
  el('reload-btn').addEventListener('click',()=>location.reload());
  async function fetchLive(){
    const response=await fetch('./data/live/latest.json?refresh='+Date.now(),{cache:'no-store'});
    if(!response.ok)throw Error('Live forecast unavailable');
    const incoming=normalizeData(await response.json());
    if(incoming.mode!=='auto-live')throw Error('Not a live forecast');
    return incoming;
  }
  function liveEvidenceRevision(value) {
    return JSON.stringify([value?.event_date,value?.updated_at_utc,
      value?.official_pay_info,value?.result_sync,
      value?.official_results,value?.settlement_alerts]);
  }
  function acceptLiveData(incoming) {
    if(data&&incoming.event_date<data.event_date)return false;
    if(data&&incoming.event_date===data.event_date&&lastLiveUpdate&&incoming.updated_at_utc &&
       incoming.updated_at_utc<lastLiveUpdate)return false;
    const previous=liveEvidenceRevision(data);
    const priorDay=data?.event_date,priorResults=autoResults;
    data=incoming;
    autoResults={...(incoming.official_results||{})};
    if(priorDay===incoming.event_date){
      // A newer verified official-pay snapshot may outrun the nationwide build.
      for(const [key,p] of Object.entries(priorResults||{})){
        if(p?.imported_from!=='server_verified_daily_pay_snapshot'||autoResults[key]||
          data.settlement_alerts?.[key])continue;
        const [day,venue,raceNo]=key.split('|');
        const current=data.forecast_races?.find(r=>
          r.venue===venue&&r.race===Number(raceNo));
        if(day===incoming.event_date&&current?.sha256===p.snapshot_sha256)
          autoResults[key]=p;
      }
      data.official_results=autoResults;
    }
    lastLiveUpdate=incoming.updated_at_utc||'';
    state.origin='非公式API＋GitHub Actions・発走前スナップショット';
    if(state.raceDetail)state.raceDetail=findRace(state.raceDetail.venue,state.raceDetail.race);
    const venues=getVenues();
    if(state.venue!=='全場'&&!venues.includes(state.venue))state.venue='全場';
    if(!venues.includes(state.resultVenue))state.resultVenue=venues[0];
    if(state.resultVenue&&!findRace(state.resultVenue,state.resultRace)){
      state.resultRace=allRaces().find(r=>r.venue===state.resultVenue)?.race||1;
    }
    return previous!==liveEvidenceRevision(data);
  }
  function applyOfficialPayResult(result) {
    if(!result?.available)return false;
    const previous=liveEvidenceRevision(data);
    autoResults=result.results;
    data.official_results=autoResults;
    data.settlement_alerts=result.alerts;
    if(result.retrieved_at_utc&&
       Date.parse(result.retrieved_at_utc)>Date.parse(data.official_pay_info?.retrieved_at_utc||0)){
      data.official_pay_info={...(data.official_pay_info||{}),
        retrieved_at_utc:result.retrieved_at_utc,
        verified_on_page:result.verified_on_page,
        confirmed_forecast_results:Object.keys(autoResults).length,
        source_status:'OK'};
    }
    return previous!==liveEvidenceRevision(data);
  }
  async function pollOfficialResults(){
    if(!data||data.mode!=='auto-live'||document.hidden||
       readJSON(STORE_DATA,null)||resultsRefreshBusy||officialPollBusy||
       liveUpdateInFlight||!window.BoatOfficialDirect?.refresh)return;
    officialPollBusy=true;
    const day=data.event_date;
    try{
      const result=await window.BoatOfficialDirect.refresh(
        day,allRaces(),autoResults,data.settlement_alerts||{});
      if(data.event_date!==day)return;
      if(applyOfficialPayResult(result)){
        if(result.added){
          resultsRefreshIsError=false;
          resultsRefreshNotice='自動照合で新たに'+result.added+'Rの公式結果を確認しました。';
          void window.BoatCumulative?.load(true).then(()=>
            {if(['results','analysis'].includes(state.view))render()}).catch(()=>{});
        }
        if(['overview','results','analysis'].includes(state.view))render();
      }
    }catch(error){console.warn('Automatic official pay refresh:',error?.message);}
    finally{officialPollBusy=false;}
  }
  async function refreshOfficialResults(){
    if(resultsRefreshBusy||officialPollBusy)return;
    if(readJSON(STORE_DATA,null)){
      resultsRefreshIsError=true;
      resultsRefreshNotice='手動インポート中です。データ管理から「元の予想に戻す」を選ぶと公式の自動照合を確認できます。';
      render();
      return;
    }
    resultsRefreshBusy=true;resultsRefreshIsError=false;resultsRefreshNotice='';render();
    const oldDate=data?.event_date;
    const oldVerified=new Set(Object.keys(autoResults).filter(key=>
      autoResults[key]?.verified===true&&autoResults[key]?.source==='boatrace_official_pay' &&
      !data?.settlement_alerts?.[key]));
    let networkSucceeded=false,applied=false,extra=0;
    let oldLive=false,liveError=null,directError=null;
    try{
      const incoming=await fetchLive();
      networkSucceeded=true;
      if(data&&incoming.event_date<data.event_date)oldLive=true;
      else applied=acceptLiveData(incoming);
    }catch(error){
      liveError=error;
      console.warn('Official-result nationwide snapshot refresh failed:',error?.message);
    }
    if(!oldLive&&window.BoatOfficialDirect?.refresh){
      try{
        const result=await window.BoatOfficialDirect.refresh(
          data.event_date,allRaces(),autoResults,data.settlement_alerts||{}
        );
        networkSucceeded=true;
        if(result?.available){
          extra=result.added||0;
          applyOfficialPayResult(result);
        }
      }catch(error){
        directError=error;
        console.warn('Independent verified official pay refresh:',error?.message);
      }
    }
    try{
      const newKeys=Object.keys(autoResults).filter(key=>
        autoResults[key]?.verified===true&&autoResults[key]?.source==='boatrace_official_pay' &&
        !data?.settlement_alerts?.[key]);
      const added=newKeys.filter(key=>!oldVerified.has(key)).length;
      const last=Date.parse(data?.official_pay_info?.retrieved_at_utc||
        data?.updated_at_utc||'');
      const stale=Number.isFinite(last)&&Date.now()-last>30*60*1000;
      if(oldLive){
        resultsRefreshIsError=true;
        resultsRefreshNotice='公開先のデータは表示中の記録より古いため、上書きしませんでした。';
      }else if(added){
        resultsRefreshNotice='新たに'+added+'Rの公式結果を確認しました。合計'+newKeys.length+'Rを照合済みです。';
      }else if(!networkSucceeded){
        resultsRefreshIsError=true;
        resultsRefreshNotice='公開データを取得できませんでした。最新の公式結果をまだ確認できません。';
      }else if(oldDate!==data.event_date){
        resultsRefreshNotice='対象日が'+data.event_date+'に更新されました。公式照合 '+newKeys.length+'Rを表示しています。';
      }else if(applied||extra){
        resultsRefreshNotice='公開データを更新しました。新しい公式照合結果はまだありません。';
      }else{
        resultsRefreshNotice='公開済みの最新データを確認しました。新しい公式照合結果はまだありません。';
      }
      if(stale&&added===0)
        resultsRefreshNotice+=' ※公式データの最終確認から30分以上経過。サーバー側の更新遅延の可能性があります。';
      if((liveError||directError)&&!networkSucceeded)
        resultsRefreshNotice+=' ネットワークまたは公開元を確認してください。';
      if(added>0&&window.BoatCumulative)
        void window.BoatCumulative.load(true).then(()=>
          {if(['results','analysis'].includes(state.view))render()}).catch(()=>{});
    }finally{
      resultsRefreshBusy=false;
      render();
    }
  }
  let originalRefreshBusy=false;
  async function refreshOriginalExhibition(force=false){
    const race=state.raceDetail,source=window.BoatOriginalExhibitionDirect;
    if(!source||!race||!data||!state.showExternalAnalysis||originalRefreshBusy)return;
    const date=data.event_date,key=date+'|'+race.venue+'|'+race.race;
    originalRefreshBusy=true;
    try{
      // The direct source marks its own status "loading" synchronously.
      // Render only AFTER starting the request so the button visibly changes.
      const pending=source.refresh(race,date,{force});
      if(state.view==='races')render();
      // Direct public original-exhibition CSV (no results or payouts).
      const result=await pending;
      // A manual refresh also updates the archived snapshot fallback.
      if(force)await window.BoatExhibitionAudit?.load(date);
      if(result?.state==='ready')state.reanalysisNotice='展示CSVを取得しました。入力欄に反映された値を確認して「再予想を実行」を押してね。';
      else if(force)state.reanalysisNotice=result?.message||'直前CSVを取得できませんでした。';
      if(result?.state==='error')console.warn('Original exhibition direct fetch:',result.message);
    }catch(error){console.warn('Original exhibition update:',error?.message);}
    finally{
      originalRefreshBusy=false;
      if(data?.event_date===date&&state.view==='races'&&state.showExternalAnalysis&&
         state.raceDetail&&date+'|'+state.raceDetail.venue+'|'+state.raceDetail.race===key)render();
    }
  }
  let lastExhibitionHeartbeat='';
  let exhibitionHeartbeatBusy=false;
  // This is a lightweight ~700-byte heartbeat: never download the large
  // frozen forecast JSON on every timer tick. The live file remains the
  // ONLY source of formal exhibition-phase picks.
  async function pollExhibitionHeartbeat(){
    if(exhibitionHeartbeatBusy||document.hidden||readJSON(STORE_DATA,null))return;
    exhibitionHeartbeatBusy=true;
    try{
      const response=await fetch('./data/exhibition/status-latest.json?fresh='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw Error('展示取得監査 HTTP '+response.status);
      const h=await response.json();
      if(!h||h.event_date!==data?.event_date||!h.collected_at_utc)return;
      const t=Date.parse(h.collected_at_utc);
      if(!Number.isFinite(t))return;
      if(!lastExhibitionHeartbeat){
        lastExhibitionHeartbeat=h.collected_at_utc;
        if(t>Date.parse(lastLiveUpdate||0))await reloadLiveIfNew();
        return;
      }
      if(t>Date.parse(lastExhibitionHeartbeat)){
        lastExhibitionHeartbeat=h.collected_at_utc;
        // Refresh the immutable pre-cutoff forecast ledger only AFTER its
        // source heartbeat advances. Never turn archived results into picks.
        await reloadLiveIfNew();
        await window.BoatExhibitionAudit?.load(h.event_date);
        if(data?.event_date===h.event_date)render();
      }
    }catch(e){console.warn('Exhibition heartbeat unavailable:',e?.message);}
    finally{exhibitionHeartbeatBusy=false;}
  }
  let liveUpdateInFlight=false;
  async function reloadLiveIfNew(){
    if(readJSON(STORE_DATA,null)||resultsRefreshBusy||officialPollBusy||liveUpdateInFlight||document.hidden)return;
    liveUpdateInFlight=true;
    try{
      const incoming=await fetchLive();
      if(liveEvidenceRevision(incoming)===liveEvidenceRevision(data))return;
      if(acceptLiveData(incoming))render();
      window.BoatExhibitionAudit?.load(incoming.event_date).then(()=>render()).catch(()=>{});
    }catch(error){console.warn('Live data refresh failed:',error.message);}
    finally{liveUpdateInFlight=false;}
  }
  async function init(){
    results=readJSON(STORE_RESULTS,{});
    batchOfficial=readJSON(STORE_BATCH_OFFICIAL,{});
    if(!batchOfficial||typeof batchOfficial!=='object'||Array.isArray(batchOfficial))batchOfficial={};
    favorites=readJSON(STORE_FAVORITES,window.BoatVenueBoard?.DEFAULT_FAVORITES||[]);
    if(!Array.isArray(favorites))favorites=[];
    favorites=favorites.filter(x=>typeof x==='string');
    try{
      const imported=readJSON(STORE_DATA,null);
      if(imported){try{data=normalizeData(imported);state.origin='利用者が読み込んだJSON（発走前固定・出典は未検証）';}catch{localStorage.removeItem(STORE_DATA);}}
      if(!data){if(window.BOAT_LAB_BOOTSTRAP){data=normalizeData(window.BOAT_LAB_BOOTSTRAP);}else{try{data=await fetchLive();state.origin='非公式API＋GitHub Actions・発走前スナップショット';}catch{const response=await fetch('./data/2026-10-22.json',{cache:'no-cache'});if(!response.ok)throw Error(`HTTP ${response.status}`);data=normalizeData(await response.json());state.origin='過去データの表示（最新の自動予想を取得できません）';}}}
      autoResults=data.official_results||{};lastLiveUpdate=data.updated_at_utc||'';
      state.resultVenue=getVenues()[0];render();
      window.BoatExhibitionAudit?.load(data.event_date).then(()=>{if(data?.event_date)render()}).catch(()=>{});
      window.BoatMobileRaceNav?.installSwipe(el('main'),()=>goBack());
      if('serviceWorker' in navigator&&['https:','http:'].includes(location.protocol))navigator.serviceWorker.register('./service-worker.js').catch(()=>{});
      if(typeof setInterval==='function'){
        setInterval(reloadLiveIfNew,300000);
        // Frequent, low-bandwidth exhibition freshness detection while visible.
        // The initial page load already fetches the latest frozen JSON.
        // Begin low-bandwidth heartbeat checks on the next minute.
        setInterval(pollExhibitionHeartbeat,60000);
        // While reanalysis is open, query the public original-exhibition-only CSV directly.
        // The external publisher is periodic; this is best-effort, not true realtime.
        setInterval(()=>{if(state.view==='races'&&state.raceDetail&&state.showExternalAnalysis&&!document.hidden)void refreshOriginalExhibition(false);},20000);
        setInterval(refreshTimelineClock,60000);
        // Poll the small verified payout file on every visible screen, independently
        // of the much larger forecast JSON and its prediction timestamp.
        setInterval(pollOfficialResults,60000);
      }
      void pollOfficialResults();
      document.addEventListener('visibilitychange',()=>{if(!document.hidden){void pollOfficialResults().then(reloadLiveIfNew);void pollExhibitionHeartbeat();if(state.view==='races'&&state.showExternalAnalysis)void refreshOriginalExhibition(false);}});
    }catch(error){el('main').innerHTML=`<section class="card card-pad"><h1>データを読み込めませんでした</h1><p class="muted">${escape(error.message)}</p><p>アプリはHTTPSまたはローカルHTTPサーバー上で開いてください。ダウンロードしたHTMLを直接開くと、ブラウザの制限で予想データを取得できない場合があります。</p></section>`;}
  }
  window.BoatLab={validate:normalizeData,stats,officialStats,officialFor,compute,getData:()=>data,refreshOfficialResults};
  init();
})();
