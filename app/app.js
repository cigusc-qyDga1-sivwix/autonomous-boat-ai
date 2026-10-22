/* BOAT LAB v1.0: offline-first, manual-result, prediction inspection UI.
 * This file never places bets, never sends notifications and never fetches results.
 */
(() => {
  'use strict';
  const STORE_RESULTS = 'boatlab-results-v1';
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
  const state = {view:'overview',venue:'全場',classification:'ALL',boardFilter:'all',boardSort:'official',raceDetail:null,showExternalAnalysis:false,reanalysisResult:null,reanalysisExtras:{},resultVenue:'鳴門',resultRace:1,origin:'GitHubで発走前固定した予想のローカル写し'};
  let data = null;
  let results = {};
  let autoResults = {};
  let lastLiveUpdate = '';
  let resultsRefreshBusy = false;
  let resultsRefreshNotice = '';
  let resultsRefreshIsError = false;
  let favorites = [];
  let toastTimer = null;

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
    const v=autoResults[raceKey(r)];
    if(!v||data?.mode!=='auto-live'||v.source!=='boatrace_official_pay'||v.verified!==true)return null;
    if(v.snapshot_sha256 && r.sha256 && v.snapshot_sha256!==r.sha256)return null;
    if(!isCombo(v.finish)||!Number.isSafeInteger(v.payout_per_100)||v.payout_per_100<100)return null;
    return v;
  }
  function resultIssue(r) {return data?.settlement_alerts?.[raceKey(r)] || null;}
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
    if(window.BoatVenueBoard) return window.BoatVenueBoard.renderHome(data,boardOptions());
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
  function tile(r) {return `<button type="button" class="race-tile" data-race="${escape(r.venue)}|${r.race}"><div class="tile-top"><span class="tile-r">${escape(r.venue)} ${r.race}R</span>${pill(r.classification)}</div><div class="tile-time">締切予定 ${escape(r.cutoff_jst)} · ${r.bets.length}点 · ${r.phase==='exhibition'?'展示反映':r.phase==='baseline'?'展示前':'保存済み'}</div><div class="tile-bets">${escape(r.bets.slice(0,2).map(b=>b.combination).join(' / '))}</div><div class="tile-scenario">${escape(r.scenario)}</div><div class="tile-foot"><span>${finishPill(r)}</span><strong>詳細を見る ↗</strong></div></button>`;}
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
  function detail(r) {
    const w=weatherFor(r.venue,r.cutoff_jst),c=compute(r);
    const external=window.BoatExternalReference;
    const externalUrl=external?external.linkFor(r.venue,data.event_date,r.race):'https://boaters-boatrace.com/race';
    const predictionUrl=external?external.predictionLinkFor(r.venue,data.event_date,r.race):'https://boaters-boatrace.com/race';
    const recalc=window.BoatReanalysis;
    const exhibitionUrl=external?.exhibitionLinkFor(r.venue,data.event_date,r.race)||externalUrl;
    const modelKey=data.event_date+'|'+r.venue+'|'+r.race+'|'+(r.sha256||'sample');
    const stored=state.reanalysisResult?.key===modelKey?state.reanalysisResult:null;
    const referencePanel=`<section class="external-reference-card" aria-label="予想情報の確認と展開再評価">
      <div class="external-header"><div><span class="external-eyebrow">EXHIBITION · RACE INTELLIGENCE</span><h2>🚤 展示情報を見て予想を強化</h2></div><span class="external-status">試験モデル</span></div>
      <p>出走表・モーター・ST・展示タイムを使って<strong>1着の勝ち筋 → 2着の浮上 → 3着残存</strong>の順番で3連単を組み直します。外部サイトを無断で読み取ることはしません。</p>
      <div class="external-action-row">
        <a class="external-btn external-btn-primary" href="${escape(exhibitionUrl)}" target="_blank" rel="noopener noreferrer">↗ BOATERSの展示項目を見る</a>
        <a class="external-btn external-btn-white" href="${escape(externalUrl)}" target="_blank" rel="noopener noreferrer">↗ 出走表・モーターを確認</a>
        <button type="button" class="external-btn external-btn-white" data-action="analyze-saved-race" aria-expanded="${state.showExternalAnalysis?'true':'false'}">${state.showExternalAnalysis?'✕ 再評価画面を閉じる':'🧠 展開を再評価する'}</button>
      </div>
      ${state.showExternalAnalysis ? `<div class="recalc-workbench">
        <div class="recalc-data-status"><span>勝率・モーター・平均ST：${r.racers?.length===6?'取得済み':'未取得'}</span><span>展示タイム：${r.phase==='exhibition'?'取得済み':'未取得'}</span><span>1周・回り足・直線：追加できる場合のみ</span></div>
        ${recalc?recalc.inputForm(r,state.reanalysisExtras):'<p>再評価モジュールを読み込めませんでした。</p>'}
        <button type="button" class="external-btn external-btn-primary recalc-run" data-action="run-reanalysis">🧠 取得済みデータで再予想（4〜12点）</button>
        ${stored && recalc?recalc.resultHTML(stored.result,stored.afterCutoff):''}
      </div>` : ''}
      <p class="external-footnote">BOATERSが掲載する独自展示指標は、元の競艇場公式でも公開されることがあります。データ利用条件を確認し、許可された提供元から取り込む方針です。<strong>この機能はBOATERSから自動取得したものではありません。</strong>固定済み買い目は変更しません。</p>
    </section>`;
    return `<button class="back-btn" data-action="back-races">← レース一覧へ戻る</button><div class="detail-header"><div><div class="page-eyebrow">FORECAST DETAILS / ${escape(data.event_date)}</div><h1 class="detail-title">${escape(r.venue)} ${r.race}R <span style="font-size:17px;vertical-align:middle">${pill(r.classification)}</span></h1><div class="detail-sub">締切予定 ${escape(r.cutoff_jst)} JST　 ·　 ${r.phase==='exhibition'?'展示数値反映':r.phase==='baseline'?'展示前':'保存済み'}・結果未使用</div></div><button class="btn btn-primary" data-action="copy-bets" data-race="${escape(r.venue)}|${r.race}">⎘ 買い目をコピー</button></div>
    ${r.phase?`<div class="notice">${escape(r.evidence||'')} ・ 発走前保存 ${escape(r.frozen_at_utc||'未記録')} ・ SHA256 ${escape((r.sha256||'').slice(0,18))}…${r.weather_observed?`<br>場内風速 ${escape(r.weather_observed.wind_speed)}m/s ／ 波高 ${escape(r.weather_observed.wave_height)}cm（非公式・取得時点）`:''}<br>予想モデル：未学習・確率未校正。展示動画とオッズは未反映。</div>`:''}
    ${referencePanel}
    ${r.point_reason?`<div class="notice"><strong>点数を選んだ理由：</strong>${escape(r.point_reason)} ／ ${r.bets.length}点。これは未校正の相対指標で、実測的中確率ではありません。</div>`:''}
    <div class="detail-grid"><section class="card card-pad"><div class="section-head"><h2 class="section-title">3連単フォーメーション</h2>${pill(`${r.bets.length}点 / 仮想`,'pending')}</div><div class="feature-card"><span class="feature-label">SCENARIO / 展開の中心</span><strong>${escape(r.scenario)}</strong><p>着順連動型の仮説。1着の勝ち筋と2・3着の残り方を検証する。</p></div><table class="bets-table"><thead><tr><th>評価</th><th>3連単</th><th>仮想金額</th></tr></thead><tbody>${r.bets.map((b,i)=>`<tr class="${i<3?'top-bet':''}"><td>${i<3?'本線':i<6?'対抗':'穴'}</td><td>${escape(b.combination)}</td><td class="amount">${money(b.virtual_yen)}</td></tr>`).join('')}</tbody></table><div class="detail-total"><span>合計 / ${r.bets.length}点</span><strong>${money(c.stake)}</strong></div><div class="notice warn">実際の購入は0円。${r.phase==='exhibition'?'展示は取得時点の値を反映。':'展示は未反映。'} オッズは未反映。この金額は精度比較用の仮想配分です。</div></section>
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
    const message=resultsRefreshNotice||(imported?
      '手動インポート中です。自動照合に戻すにはデータ管理で「元の予想に戻す」を選んでね。':
      'ボタンを押すと最新の公開済み公式照合データを再読み込みします。');
    return `<div class="results-refresh" aria-label="公式結果の更新">
      <div class="results-refresh-main">
        <div class="results-refresh-copy"><strong>🔄 公式結果をチェック</strong>
          <span>公開データ更新 ${escape(published)} ／ 公式ページ確認 ${escape(officialAt)}</span></div>
        <button type="button" class="btn btn-primary results-refresh-button"
          data-action="refresh-official-results" ${resultsRefreshBusy?'disabled aria-busy="true"':''}>
          ${resultsRefreshBusy?'⏳ 更新を確認中…':'↻ 結果を更新'}
        </button>
      </div>
      <p class="results-refresh-status ${resultsRefreshIsError?'is-error':''}" role="status" aria-live="polite">${escape(resultsRefreshBusy?'最新の公開データを取得しています…':message)}</p>
      ${failed?'<p class="results-refresh-hint">直近の自動収集では公式サイトへのアクセスに失敗しています。未確認レースは的中・不的中として計上しません。</p>':''}
      <p class="results-refresh-hint">結果はサーバー側の定期収集で更新されます。このボタンは最新の公開済み結果を再読み込みします。公式サイトへの即時取得を開始するものではありません。</p>
    </div>`;
  }
  function resultsPage() {
    const races=allRaces();
    if(!races.length)return head('結果照合','発走前に保存した予想のみ結果と照合します')+resultsRefreshControl()+'<div class="no-data">予想データがまだありません。次の取得結果を確認してください。</div>';
    const r=findRace(state.resultVenue,state.resultRace)||races[0];
    const c=compute(r),settled=races.filter(x=>!!recordFor(x));
    const live=data.mode==='auto-live', verified=officialStats(races);
    const issue=resultIssue(r), hasOfficial=!!officialFor(r);
    const issues=Object.keys(data.settlement_alerts||{}).length;
    const officialUrl='https://www.boatrace.jp/owpc/pc/race/pay?hd='+data.event_date.replaceAll('-','');
    const header=live?`<div class="metrics" style="margin-bottom:16px">${metric('公式照合',verified.count+'R','公式払戻で検証済み','✓')}${metric('3連単的中',verified.hits+'R',verified.count?pct(verified.hitRate):'未確認','◎')}${metric('仮想回収率',verified.returnRate===null?'—':pct(verified.returnRate),'公式照合済みのみ','↗',verified.returnRate>=1?'positive':'')}${metric('仮想収支',verified.count?(verified.profit>=0?'+':'')+money(verified.profit):'—','正式BUYとは別','¥',verified.profit>=0?'positive':'negative')}</div><div class="notice">公式払戻：<a href="${escape(officialUrl)}" target="_blank" rel="noopener noreferrer">BOATRACE 本日の払戻金一覧 ↗</a> ／ ${issues}R 要確認。未公表・返還・レース中止は収支対象外。手入力は正式成績には算入しません。</div>`:'';
    const recent=settled.length?`<div class="result-list">${settled.slice().reverse().map(x=>{
      const result=compute(x),isOfficial=!!officialFor(x);
      return `<div class="result-item"><div><span class="text-xs muted">${escape(x.venue)} ${x.race}R ・ ${isOfficial?'公式確認':'手入力'}</span><div class="combo">${escape(result.record.finish)}</div><div class="sub">${money(result.record.payout_per_100)} / 100円</div></div><div class="status-end">${finishPill(x)}<strong class="${result.profit>=0?'positive':'negative'}">${result.profit>=0?'+':''}${money(result.profit)}</strong></div></div>`;
    }).join('')}</div>`:'<div class="no-data">未照合です。公式払戻が掲載されると自動反映されます。</div>';
    const selected=state.resultVenue, raceSelect=state.resultRace;
    const form=`<form id="result-form" class="result-form"><div class="form-row"><div class="field"><label for="result-venue">競艇場</label><select id="result-venue" class="select input">${getVenues().map(v=>`<option value="${escape(v)}" ${selected===v?'selected':''}>${escape(v)}</option>`).join('')}</select></div><div class="field"><label for="result-race">レース</label><select id="result-race" class="select input">${races.filter(x=>x.venue===selected).map(x=>`<option value="${x.race}" ${raceSelect===x.race?'selected':''}>${x.race}R</option>`).join('')}</select></div></div><div class="feature-card"><span class="feature-label">保存済み予想 / ${escape(r.classification)}</span><strong>${escape(r.bets.slice(0,3).map(b=>b.combination).join(' / '))}</strong><p>${escape(r.scenario)}</p></div><div class="field"><label for="finish">3連単（確定着順）</label><div class="form-row" style="gap:8px">${[0,1,2].map(i=>`<select id="finish-${i}" class="select input" style="width:calc(33.3% - 6px);min-width:0" aria-label="${i+1}着"><option value="">${i+1}着</option>${[1,2,3,4,5,6].map(n=>`<option value="${n}" ${c.record?.finish?.split('-')[i]===String(n)?'selected':''}>${n}号艇</option>`).join('')}</select>`).join('')}</div></div><div class="field"><label for="payout">3連単払戻（100円あたり）</label><input id="payout" class="input" inputmode="numeric" type="number" min="100" max="10000000" step="10" required placeholder="例：2430" value="${c.record?c.record.payout_per_100:''}"></div><p class="help">${hasOfficial?'公式結果を取得済み。手入力で変更はできません。':issue?'返還・中止・不一致があるため、手入力で収支を確定できません。':'公式結果未取得の場合だけ暫定的に手入力できます。公式照合済み成績には含みません。'}</p><button type="submit" class="btn btn-primary" ${hasOfficial||issue?'disabled':''}>${live?'暫定結果を保存':'結果を照合・保存'}</button>${results[raceKey(r)]&&!hasOfficial?'<button type="button" data-action="delete-result" class="btn btn-danger">手入力を取り消す</button>':''}</form>`;
    return `${head('結果照合',live?'BOATRACE公式払戻から自動照合・発走前予想は変更しません':'手入力の仮想照合',pill(live?verified.count+'R 公式確認':settled.length+'R 入力済み','local'))}${resultsRefreshControl()}${header}<div class="results-layout"><section class="card card-pad"><div class="section-head"><h2 class="section-title">${live?'レース結果の確認':'結果を入力'}</h2>${pill(hasOfficial?'公式確認済み':issue?'要確認':'未確認','local')}</div>${issue?`<div class="notice warn">このレースは${escape(issue.reason||'追加確認')}。自動の仮想収支には含めません。</div>`:''}${form}</section><section class="card card-pad"><div class="section-head"><h2 class="section-title">照合履歴</h2><span class="text-xs muted">${settled.length}R</span></div>${recent}</section></div>`;
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
    const weatherCoverage=Number(data.weather_venue_count||Object.keys(data.venue_weather||{}).length);
    const weatherTestHtml=live?'<section class="card card-pad weather-test-analysis"><div class="section-head"><h2 class="section-title">🌦 気象補正あり・なしの発走前比較</h2></div>'+
      '<p class="help">開催場の周辺予報取得 '+weatherCoverage+'/'+(data.venues_with_races||'—')+'場。実際に気象を固定予想へ記録できたのは '+(data.weather_fixed_race_count??'集計前')+'Rです。過去の固定予想は後から変更していません。</p>'+
      (weatherN?'<div class="weather-ab-metrics"><span>公式照合 <b>'+weatherN+'R</b></span><span>気象あり的中 <b>'+weatherTest.weather_hits+'R</b></span><span>気象なし的中 <b>'+weatherTest.control_hits+'R</b></span></div>'+
       '<p class="help">仮想回収率：気象あり '+(100*weatherTest.weather_payout/weatherTest.virtual_stake_per_model).toFixed(1)+'% ／ 気象なし '+(100*weatherTest.control_payout/weatherTest.virtual_stake_per_model).toFixed(1)+'%（同一レース、事前固定買い目のみ）</p>':
       '<div class="notice">気象あり・なしを同条件で公式照合できたレースはまだありません。効果は未検証です。</div>')+
      '<p class="help">この比較は未校正の試験モデル。気象補正が的中率や回収率を改善する保証はありません。</p></section>':'';
    const metrics=total.examined?`${metric('検証済み',`${total.examined} R`,live?'公式払戻で確認済み':'手入力の結果のみ','✓')}${metric('3連単的中',`${total.hits} R`,pct(total.hitRate),'◎')}${metric('仮想回収率',pct(total.returnRate),'照合済みだけ','↗',total.returnRate>=1?'positive':'negative')}${metric('仮想収支',`${total.profit>=0?'+':''}${money(total.profit)}`,'正式BUYは別管理','¥',total.profit>=0?'positive':'negative')}`:`${metric('検証済み','0 R','まず結果照合を入力','✓')}${metric('3連単的中','—','未検証','◎')}${metric('仮想回収率','—','未検証','↗')}${metric('仮想収支','—','未検証','¥')}`;
    return `${head('成績分析',`${getVenues().length}場を比較 / 仮想5万円 × 保存済み${allRaces().length}R`)}<div class="metrics">${metrics}</div>${weaknessDiagnosis()}${weatherTestHtml}<div class="columns-2"><section class="card card-pad"><div class="section-head"><h2 class="section-title">競艇場別の的中率</h2>${pill('検証済みのみ','local')}</div><div class="chart-grid">${groups.map(g=>`<div class="chart-item"><strong>${escape(g.venue)}</strong><div class="bar-back"><span class="bar-value" style="width:${g.all.examined?(100*g.all.hitRate).toFixed(1):0}%"></span></div><b>${g.all.examined?pct(g.all.hitRate):'—'}</b></div>`).join('')}</div><p class="charts-note">予想点数は4〜12点（旧8点固定記録を含む）。仮想5万円で比較。的中率は${live?'BOATRACE公式確認済み':'結果入力済み'}レースのみが分母。</p><div class="notice">${total.examined?`頭候補捕捉 ${total.heads}/${total.examined}R、1・2着順一致 ${total.firstSeconds}/${total.examined}R、3着紐抜け ${total.thirdMiss}R。`:'まだ結果がないため、モデルの実力を判定できません。'}</div></section>
    <section class="card card-pad"><div class="section-head"><h2 class="section-title">WATCHとSKIPの比較</h2></div>${[['WATCH',watchTotal],['SKIP',skipTotal]].map(([name,s])=>`<div class="feature-card"><span class="feature-label">${name} · ${s.examined}/${s.count}R</span><strong>的中 ${s.hits}R${s.examined?' / '+pct(s.hitRate):''}</strong><p>仮想回収率 ${s.returnRate===null?'未算出':pct(s.returnRate)} ・ 収支 ${s.examined?money(s.profit):'未算出'}</p></div>`).join('')}<div class="notice warn">SKIPの仮想配分はベンチマーク用。実際に買ったと仮定した場合の数字で、正式な投資収支ではありません。</div></section></div>
    <div class="card card-pad" style="margin-top:18px"><div class="section-head"><h2 class="section-title">場別・モデル検証サマリー</h2></div><table class="bets-table"><thead><tr><th>場</th><th>照合</th><th>的中</th><th>仮想回収</th></tr></thead><tbody>${groups.map(g=>`<tr><td>${escape(g.venue)}</td><td>${g.all.examined}/${g.all.count}</td><td>${g.all.hits}R</td><td>${g.all.returnRate===null?'—':pct(g.all.returnRate)}</td></tr>`).join('')}</tbody></table></div><p class="footer-disclaimer">検証値には事後作成の予想を混ぜない。データの入手時刻と発走前固定を確認できる予想のみを、正式なモデル評価に使用します。</p>`;
  }
  function settings() {
    return `${head('データ管理',`予想データと結果を管理 / この端末のブラウザに保存`)}<div class="settings-grid"><section class="card settings-card"><span class="mini-caption">PREDICTION SOURCE</span><h2 class="section-title" style="margin:12px 0">発走前の固定データ</h2><p>${escape(state.origin)}。${data.mode==='auto-live'?'出走表・展示は非公式データ、結果・払戻はBOATRACE公式ページを参照。発走前に固定できたレースだけ照合しています。':'新しい予想の自動取得はまだありません。'}</p><div class="meta-list"><div class="meta"><span>対象日</span><b>${dateDisplay(data.event_date)}</b></div><div class="meta"><span>予想件数</span><b>${data.forecast_races.length}R</b></div><div class="meta"><span>モデル</span><b>${data.mode==='auto-live'?'未訓練ヒューリスティック・展示2段階':'展示前・参考気象補正'}</b></div><div class="meta"><span>オッズ / 動画解析</span><b>未接続</b></div></div><div class="notice"><span class="mini-caption">GIT COMMIT</span><br><span class="code-ref">${escape(data.freeze_reference||'外部固定記録なし')}</span></div><div class="settings-btns" style="margin-top:14px"><a class="btn btn-soft" href="https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai" target="_blank" rel="noopener noreferrer">↗ GitHubを見る</a><button data-action="export-predictions" class="btn btn-white">↧ 予想JSON保存</button></div></section>
    <section class="card settings-card"><span class="mini-caption">LOCAL DATA</span><h2 class="section-title" style="margin:12px 0">結果をバックアップ</h2><p>入力した確定結果はブラウザ内だけに保存。機種変更やブラウザのデータ削除に備えてJSONで保存できるよ。</p><div class="settings-btns"><button data-action="export-results" class="btn btn-primary">↧ 結果CSVを書き出す</button><button data-action="export-backup" class="btn btn-white">↧ 結果JSON</button></div><p class="help" style="margin-top:16px">※ バックアップなしでブラウザを消去すると、結果入力も消える可能性があります。</p><div style="margin-top:24px"><label class="mini-caption" for="upload-dataset">将来の予想データを読み込む</label><input type="file" id="upload-dataset" class="input" accept="application/json,.json" style="margin-top:10px"><p class="help">BOAT LAB形式のJSONのみ。インポートしたデータは発走前固定の証明を伴わないため、正式成績としては扱えません。</p></div><div class="settings-btns" style="margin-top:15px"><button data-action="reset-dataset" class="btn btn-white">元の予想に戻す</button><button data-action="clear-results" class="btn btn-danger">入力した結果を全削除</button></div></section></div>
    <div class="card card-pad" style="margin-top:18px"><h2 class="section-title">開発ロードマップ</h2><div class="status-pills" style="margin-top:17px"><span class="tag">✓ レース・買い目一覧</span><span class="tag">✓ 仮想配分</span><span class="tag">✓ 結果照合</span><span class="tag">✓ 収支集計</span><span class="tag">✓ iPhone用画面</span></div><p class="footer-disclaimer">自動取得：出走表、展示ST・タイム・場内気象、非公式結果。未実装：動画AI、潮流実測補正、直前オッズ、正式BUY判断。実行・配信遅延で未予想のレースもあります。</p></div>`;
  }
  function render() {
    if (!data) return;
    const main=el('main');
    el('breadcrumb-label').textContent=titles[state.view];
    document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===state.view);if(b.dataset.view===state.view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    main.innerHTML=({overview,races,results:resultsPage,analysis,settings})[state.view]();
  }
  function go(view) {state.view=view;state.raceDetail=null;state.showExternalAnalysis=false;state.reanalysisResult=null;state.reanalysisExtras={};render();window.scrollTo({top:0,behavior:'instant'});}
  function toast(message){const node=el('toast');node.textContent=message;node.classList.add('show');if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('show'),3200);}
  function download(name,content,type='text/plain;charset=utf-8') {const blob=new Blob([content],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
  function exportResultsCSV(){const header=['date','venue','race','classification','cutoff_jst','finish','payout_per_100','is_hit','stake_yen','virtual_payout_yen','virtual_profit_yen','recorded_at','source'];const body=allRaces().map(r=>{let c=compute(r);return [data.event_date,r.venue,r.race,r.classification,r.cutoff_jst,c.record?.finish||'',c.record?.payout_per_100??'',c.record?Number(c.hit):'',c.record?c.stake:'',c.payout??'',c.profit??'',c.record?.recorded_at||'',c.record?'manual':''];});const csv=[header,...body].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n');download(`boatlab-results-${data.event_date}.csv`,'\uFEFF'+csv,'text/csv;charset=utf-8');toast('結果CSVを書き出したよ');}
  function copyBets(r){const s=`${data.event_date} ${r.venue} ${r.race}R ${r.cutoff_jst} [${r.classification}] ${r.phase==='exhibition'?'展示反映':'展示前'}予想（${r.bets.length}点）\n${r.scenario}\n${r.bets.map((b,i)=>`${i+1}. ${b.combination} ${money(b.virtual_yen)}`).join('\n')}\n合計 ${money(r.bets.reduce((s,b)=>s+b.virtual_yen,0))} / 研究用・仮想`;if(navigator.clipboard?.writeText)navigator.clipboard.writeText(s).then(()=>toast('買い目をコピーしたよ'),()=>toast('コピーできませんでした'));else {const t=document.createElement('textarea');t.value=s;document.body.append(t);t.select();document.execCommand('copy');t.remove();toast('買い目をコピーしたよ');}}
  document.addEventListener('click',e=>{
    const nav=e.target.closest('[data-view]');if(nav){if(nav.dataset.view==='races')state.venue='全場';go(nav.dataset.view);return;}
    const venueOpen=e.target.closest('[data-open-venue]');if(venueOpen){if(venueOpen.disabled)return;state.venue=venueOpen.dataset.openVenue;state.raceDetail=null;state.view='races';render();window.scrollTo(0,0);return;}
    const fav=e.target.closest('[data-favorite-venue]');if(fav){const name=fav.dataset.favoriteVenue;favorites=favorites.includes(name)?favorites.filter(x=>x!==name):favorites.concat([name]);try{localStorage.setItem(STORE_FAVORITES,JSON.stringify(favorites));}catch{}render();return;}
    const boardFilter=e.target.closest('[data-venue-filter]');if(boardFilter){state.boardFilter=boardFilter.dataset.venueFilter;render();return;}
    const row=e.target.closest('[data-race]');if(row){const [v,n]=row.dataset.race.split('|');let r=findRace(v,n);if(!r)return;if(row.dataset.action==='settle-this'){state.resultVenue=v;state.resultRace=Number(n);go('results');return;}if(row.dataset.action==='copy-bets'){copyBets(r);return;}state.raceDetail=r;state.showExternalAnalysis=false;state.reanalysisResult=null;state.reanalysisExtras={};state.view='races';render();window.scrollTo(0,0);return;}
    const btn=e.target.closest('[data-action]');if(!btn)return;
    switch(btn.dataset.action){
      case 'refresh-official-results':void refreshOfficialResults();break;
      case 'analyze-saved-race':state.showExternalAnalysis=!state.showExternalAnalysis;render();break;
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
          const formatter=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
          const afterCutoff=formatter.format(new Date()).replace(' ','T')>=data.event_date+'T'+r.cutoff_jst;
          state.reanalysisExtras=clean;
          state.reanalysisResult={key:data.event_date+'|'+r.venue+'|'+r.race+'|'+(r.sha256||'sample'),result:estimate,afterCutoff};
          state.showExternalAnalysis=true;render();
          toast(afterCutoff?'締切後の参考試算を生成したよ':'展開を再評価したよ（試験用）');
        }catch(err){toast(err.message||'再評価に失敗しました');}
        break;
      }
      case 'go-races':go('races');break;
      case 'back-races':state.raceDetail=null;render();break;
      case 'back-overview':state.venue='全場';go('overview');break;
      case 'export-results':exportResultsCSV();break;
      case 'export-predictions':download(`boatlab-predictions-${data.event_date}.json`,JSON.stringify(data,null,2),'application/json');toast('予想データを保存したよ');break;
      case 'export-backup':download(`boatlab-backup-${data.event_date}.json`,JSON.stringify({version:1,date:data.event_date,results},null,2),'application/json');toast('バックアップを書き出したよ');break;
      case 'reset-dataset':if(confirm('初期データに戻しますか？ 入力済みの結果は残ります。')){localStorage.removeItem(STORE_DATA);location.reload();}break;
      case 'clear-results':if(confirm('入力した結果をすべて削除します。この操作は元に戻せません。')){results={};persistResults();render();toast('結果データを削除しました');}break;
      case 'delete-result':{const r=findRace(state.resultVenue,state.resultRace);if(r&&confirm(`${r.venue} ${r.race}R の結果を取り消しますか？`)){delete results[raceKey(r)];persistResults();render();toast('入力を取り消しました');}break;}
    }
  });
  document.addEventListener('change',async e=>{
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
  function acceptLiveData(incoming) {
    if(data&&incoming.event_date<data.event_date)return false;
    if(data&&incoming.event_date===data.event_date&&lastLiveUpdate&&incoming.updated_at_utc &&
       incoming.updated_at_utc<lastLiveUpdate)return false;
    const previous=(data?.event_date||'')+'|'+(lastLiveUpdate||'')+'|'+Object.keys(autoResults).length;
    data=incoming;
    autoResults=incoming.official_results||{};
    lastLiveUpdate=incoming.updated_at_utc||'';
    state.origin='非公式API＋GitHub Actions・発走前スナップショット';
    if(state.raceDetail)state.raceDetail=findRace(state.raceDetail.venue,state.raceDetail.race);
    const venues=getVenues();
    if(state.venue!=='全場'&&!venues.includes(state.venue))state.venue='全場';
    if(!venues.includes(state.resultVenue))state.resultVenue=venues[0];
    if(state.resultVenue&&!findRace(state.resultVenue,state.resultRace)){
      state.resultRace=allRaces().find(r=>r.venue===state.resultVenue)?.race||1;
    }
    return previous!==(data.event_date+'|'+lastLiveUpdate+'|'+Object.keys(autoResults).length);
  }
  async function refreshOfficialResults(){
    if(resultsRefreshBusy)return;
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
    try{
      const incoming=await fetchLive();
      if(data&&incoming.event_date<data.event_date){
        resultsRefreshIsError=true;
        resultsRefreshNotice='公開先のデータは表示中の記録より古いため、上書きしませんでした。';
      }else{
        const applied=acceptLiveData(incoming);
        const newKeys=Object.keys(autoResults).filter(key=>
          autoResults[key]?.verified===true&&autoResults[key]?.source==='boatrace_official_pay' &&
          !data?.settlement_alerts?.[key]);
        const added=newKeys.filter(key=>!oldVerified.has(key)).length;
        if(oldDate!==data.event_date){
          resultsRefreshNotice='対象日が'+data.event_date+'に更新されました。公式照合 '+newKeys.length+'Rを表示しています。';
        }else if(added>0){
          resultsRefreshNotice='新たに'+added+'Rの公式結果を確認しました。合計'+newKeys.length+'Rを照合済みです。';
        }else if(applied){
          resultsRefreshNotice='公開データを更新しました。公式照合の追加はまだありません。';
        }else{
          resultsRefreshNotice='公開済みの最新データを確認しました。新しい公式照合結果はまだありません。';
        }
        resultsRefreshIsError=false;
      }
    }catch(error){
      resultsRefreshIsError=true;
      resultsRefreshNotice='データを取得できませんでした。通信状態を確認して、もう一度押してね。';
      console.warn('Official-result data refresh failed:',error.message);
    }finally{
      resultsRefreshBusy=false;
      render();
    }
  }
  async function reloadLiveIfNew(){
    if(readJSON(STORE_DATA,null)||resultsRefreshBusy)return;
    try{
      const incoming=await fetchLive();
      if(incoming.event_date===data?.event_date&&incoming.updated_at_utc===lastLiveUpdate)return;
      if(acceptLiveData(incoming))render();
    }catch(error){console.warn('Live data refresh failed:',error.message);}
  }
  async function init(){
    results=readJSON(STORE_RESULTS,{});
    favorites=readJSON(STORE_FAVORITES,window.BoatVenueBoard?.DEFAULT_FAVORITES||[]);
    if(!Array.isArray(favorites))favorites=[];
    favorites=favorites.filter(x=>typeof x==='string');
    try{
      const imported=readJSON(STORE_DATA,null);
      if(imported){try{data=normalizeData(imported);state.origin='利用者が読み込んだJSON（発走前固定・出典は未検証）';}catch{localStorage.removeItem(STORE_DATA);}}
      if(!data){if(window.BOAT_LAB_BOOTSTRAP){data=normalizeData(window.BOAT_LAB_BOOTSTRAP);}else{try{data=await fetchLive();state.origin='非公式API＋GitHub Actions・発走前スナップショット';}catch{const response=await fetch('./data/2026-10-22.json',{cache:'no-cache'});if(!response.ok)throw Error(`HTTP ${response.status}`);data=normalizeData(await response.json());state.origin='過去データの表示（最新の自動予想を取得できません）';}}}
      autoResults=data.official_results||{};lastLiveUpdate=data.updated_at_utc||'';
      state.resultVenue=getVenues()[0];render();
      if('serviceWorker' in navigator&&['https:','http:'].includes(location.protocol))navigator.serviceWorker.register('./service-worker.js').catch(()=>{});
      if(typeof setInterval==='function')setInterval(reloadLiveIfNew,300000);
      document.addEventListener('visibilitychange',()=>{if(!document.hidden)reloadLiveIfNew();});
    }catch(error){el('main').innerHTML=`<section class="card card-pad"><h1>データを読み込めませんでした</h1><p class="muted">${escape(error.message)}</p><p>アプリはHTTPSまたはローカルHTTPサーバー上で開いてください。ダウンロードしたHTMLを直接開くと、ブラウザの制限で予想データを取得できない場合があります。</p></section>`;}
  }
  window.BoatLab={validate:normalizeData,stats,officialStats,officialFor,compute,getData:()=>data,refreshOfficialResults};
  init();
})();