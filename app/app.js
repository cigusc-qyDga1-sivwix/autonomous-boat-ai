/* BOAT LAB v1.0: offline-first, manual-result, prediction inspection UI.
 * This file never places bets, never sends notifications and never fetches results.
 */
(() => {
  'use strict';
  const STORE_RESULTS = 'boatlab-results-v1';
  const STORE_DATA = 'boatlab-imported-dataset-v1';
  const dateDisplay = s => /^\d{4}-\d{2}-\d{2}$/.test(s) ? s.replace(/-/g, '/') : s;
  const money = n => `${Number(n || 0).toLocaleString('ja-JP')}円`;
  const pct = v => `${(v * 100).toFixed(1)}%`;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const isCombo = s => /^[1-6]-[1-6]-[1-6]$/.test(s) && new Set(s.split('-')).size === 3;
  const raceKey = r => `${data.event_date}|${r.venue}|${r.race}`;
  const el = id => document.getElementById(id);
  const titles = {overview:'ダッシュボード',races:'レース・買い目',results:'結果照合',analysis:'成績分析',settings:'データ管理'};
  const state = {view:'overview',venue:'全場',classification:'ALL',raceDetail:null,resultVenue:'鳴門',resultRace:1,origin:'GitHubで発走前固定した予想のローカル写し'};
  let data = null;
  let results = {};
  let autoResults = {};
  let lastLiveUpdate = '';
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
  function recordFor(r) {return results[raceKey(r)] || autoResults[raceKey(r)] || null;}
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
  function finishPill(r) {const c=compute(r);return c.record?pill(c.hit?'的中':'不的中',c.hit?'hit':'miss'):pill('未照合','pending');}
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
  function overview() {
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
    const filtered=allRaces().filter(r=>(state.venue==='全場'||r.venue===state.venue)&&(state.classification==='ALL'||r.classification===state.classification));
    return `${head('レース・買い目',`${dateDisplay(data.event_date)} / ${data.mode==='auto-live'?'全国の発走前固定済み予想':'保存済み予想'} / 各Rの仮想5万円配分`)}<div class="filter-bar"><div class="segmented">${['ALL','WATCH','SKIP'].map(v=>`<button data-filter-status="${v}" class="${state.classification===v?'active':''}">${v==='ALL'?'すべて':v}</button>`).join('')}</div>${venueSelect(state.venue)}</div><div class="race-grid">${filtered.map(tile).join('')||'<div class="no-data">該当するレースはありません</div>'}</div>${data.mode==='auto-live'&&data.unforecast_races?.length?`<div class="notice warn">${data.unforecast_races.length}Rは締切前の予想を固定できなかったため、買い目を表示しません。結果を見てから予想を追加することもありません。</div>`:''}<p class="footer-disclaimer">BUYが0件なのは、オッズによる採算チェックを完了していないため。SKIPレースも研究目的で予想を保持しています。</p>`;
  }
  function detail(r) {
    const w=weatherFor(r.venue,r.cutoff_jst),c=compute(r);
    return `<button class="back-btn" data-action="back-races">← レース一覧へ戻る</button><div class="detail-header"><div><div class="page-eyebrow">FORECAST DETAILS / ${escape(data.event_date)}</div><h1 class="detail-title">${escape(r.venue)} ${r.race}R <span style="font-size:17px;vertical-align:middle">${pill(r.classification)}</span></h1><div class="detail-sub">締切予定 ${escape(r.cutoff_jst)} JST　 ·　 ${r.phase==='exhibition'?'展示数値反映':r.phase==='baseline'?'展示前':'保存済み'}・結果未使用</div></div><button class="btn btn-primary" data-action="copy-bets" data-race="${escape(r.venue)}|${r.race}">⎘ 買い目をコピー</button></div>
    ${r.phase?`<div class="notice">${escape(r.evidence||'')} ・ 発走前保存 ${escape(r.frozen_at_utc||'未記録')} ・ SHA256 ${escape((r.sha256||'').slice(0,18))}…${r.weather_observed?`<br>場内風速 ${escape(r.weather_observed.wind_speed)}m/s ／ 波高 ${escape(r.weather_observed.wave_height)}cm（非公式・取得時点）`:''}<br>予想モデル：未学習・確率未校正。展示動画とオッズは未反映。</div>`:''}
    <div class="detail-grid"><section class="card card-pad"><div class="section-head"><h2 class="section-title">3連単フォーメーション</h2>${pill(`${r.bets.length}点 / 仮想`,'pending')}</div><div class="feature-card"><span class="feature-label">SCENARIO / 展開の中心</span><strong>${escape(r.scenario)}</strong><p>着順連動型の仮説。1着の勝ち筋と2・3着の残り方を検証する。</p></div><table class="bets-table"><thead><tr><th>評価</th><th>3連単</th><th>仮想金額</th></tr></thead><tbody>${r.bets.map((b,i)=>`<tr class="${i<3?'top-bet':''}"><td>${i<3?'本線':i<6?'対抗':'穴'}</td><td>${escape(b.combination)}</td><td class="amount">${money(b.virtual_yen)}</td></tr>`).join('')}</tbody></table><div class="detail-total"><span>合計 / ${r.bets.length}点</span><strong>${money(c.stake)}</strong></div><div class="notice warn">実際の購入は0円。${r.phase==='exhibition'?'展示は取得時点の値を反映。':'展示は未反映。'} オッズは未反映。この金額は精度比較用の仮想配分です。</div></section>
    <div><section class="card card-pad bottom-margin"><h3>レース情報</h3><div class="meta-list"><div class="meta"><span>開催</span><b>${escape(r.venue)}</b></div><div class="meta"><span>対象日</span><b>${dateDisplay(data.event_date)}</b></div><div class="meta"><span>締切予定</span><b>${escape(r.cutoff_jst)} JST</b></div><div class="meta"><span>予想区分</span><b>${escape(r.classification)}</b></div><div class="meta"><span>展示データ</span><b>${r.phase==='exhibition'?'反映済み（非公式）':'未反映'}</b></div><div class="meta"><span>オッズ</span><b>未反映</b></div></div></section>
    <section class="card card-pad bottom-margin"><h3>気象補正メモ</h3>${w?`<div class="weather-box"><div class="weather-symbol">≋</div><div class="weather-body"><strong>${escape(w.wind)}</strong><p>${escape(w.note)}</p></div></div>`:'<p class="muted text-sm">気象見通し未登録</p>'}<p class="help">${data.mode==='auto-live'?'展示時点に場内で取得された非公式気象データがある場合のみ表示。展示前の時間別予報はまだ未接続。':'同じ時間帯の周辺予報を参照。予報の風向はレース水面の風向と一致するとは限りません。'}</p></section>
    <section class="card card-pad"><h3>結果照合</h3><div class="meta-list"><div class="meta"><span>現在の状態</span>${finishPill(r)}</div>${c.record?`<div class="meta"><span>入力した確定着順</span><b>${escape(c.record.finish)}</b></div><div class="meta"><span>仮想払戻</span><b>${money(c.payout)}</b></div>`:''}</div><button class="btn btn-soft" style="width:100%;margin-top:15px" data-action="settle-this" data-race="${escape(r.venue)}|${r.race}">照合する →</button></section></div></div>`;
  }
  function resultsPage() {
    const r=findRace(state.resultVenue,state.resultRace)||allRaces()[0];const c=compute(r),settled=allRaces().filter(x=>!!recordFor(x));
    const status=settled.length?`<div class="result-list">${settled.slice().reverse().map(x=>{let result=compute(x);return `<div class="result-item"><div><span class="text-xs muted">${escape(x.venue)} ${x.race}R</span><div class="combo">${escape(result.record.finish)}</div><div class="sub">${money(result.record.payout_per_100)} / 100円</div></div><div class="status-end">${finishPill(x)}<strong class="${result.profit>=0?'positive':'negative'}">${result.profit>=0?'+':''}${money(result.profit)}</strong></div></div>`;}).join('')}</div>`:'<div class="no-data">まだ確定結果が入力されていません。<br>右のフォームから公式着順と3連単払戻を入力してね。</div>';
    return `${head('結果照合',`確定結果は手入力 / レースの買い目を変えずに判定`,pill(`${settled.length}R 入力済み`,'local'))}<div class="results-layout"><section class="card card-pad"><div class="section-head"><h2 class="section-title">確定結果を入力</h2>${pill('端末内保存','local')}</div><form id="result-form" class="result-form"><div class="form-row"><div class="field"><label for="result-venue">競艇場</label><select id="result-venue" class="select input">${getVenues().map(v=>`<option value="${escape(v)}" ${state.resultVenue===v?'selected':''}>${escape(v)}</option>`).join('')}</select></div><div class="field"><label for="result-race">レース</label><select id="result-race" class="select input">${allRaces().filter(x=>x.venue===state.resultVenue).map(x=>`<option value="${x.race}" ${state.resultRace===x.race?'selected':''}>${x.race}R</option>`).join('')}</select></div></div><div class="feature-card"><span class="feature-label">元の予想 / ${escape(r.classification)}</span><strong>${escape(r.bets.slice(0,3).map(b=>b.combination).join(' / '))}</strong><p>${escape(r.scenario)}</p></div><div class="field"><label for="finish">確定3連単（数字を1つずつ選択）</label><div class="form-row" style="gap:8px">${[0,1,2].map((i)=>`<select id="finish-${i}" class="select input" style="width:calc(33.3% - 6px);min-width:0" aria-label="${i+1}着"><option value="">${i+1}着</option>${[1,2,3,4,5,6].map(n=>`<option value="${n}" ${c.record?.finish?.split('-')[i]===String(n)?'selected':''}>${n}号艇</option>`).join('')}</select>`).join('')}</div></div><div class="field"><label for="payout">3連単払戻（100円あたり）</label><input id="payout" class="input" inputmode="numeric" type="number" min="100" max="10000000" step="10" required placeholder="例：2430" value="${c.record?c.record.payout_per_100:''}"></div><p class="help">公式の確定着順・3連単払戻を自分で入力。自動照合機能はまだありません。配当は100円当たりの金額です。</p><button type="submit" class="btn btn-primary">✓ 結果を照合・保存</button>${results[raceKey(r)]?'<button type="button" data-action="delete-result" class="btn btn-danger">このレースの入力を取り消す</button>':''}</form></section><section class="card card-pad"><div class="section-head"><h2 class="section-title">照合履歴</h2><span class="text-xs muted">${settled.length}レース</span></div>${status}</section></div><div class="notice">${data.mode==='auto-live'?'非公式APIから自動取得した3連単払戻を照合に利用。ユーザー入力を優先する場合があります。公式発表と差がある場合は公式を確認してください。':'この画面の結果はユーザー入力です。公式サイトと自動照合していないため、成績は入力値に依存します。'}</div>`;
  }
  function analysis() {
    const groups=getVenues().map(venue=>({venue,watch:stats(allRaces().filter(r=>r.venue===venue&&r.classification==='WATCH')),skip:stats(allRaces().filter(r=>r.venue===venue&&r.classification==='SKIP')),all:stats(allRaces().filter(r=>r.venue===venue))}));
    const total=stats(allRaces());const watchTotal=stats(allRaces().filter(r=>r.classification==='WATCH'));const skipTotal=stats(allRaces().filter(r=>r.classification==='SKIP'));
    const metrics=total.examined?`${metric('検証済み',`${total.examined} R`,'手入力の結果のみ','✓')}${metric('3連単的中',`${total.hits} R`,pct(total.hitRate),'◎')}${metric('仮想回収率',pct(total.returnRate),'照合済みだけ','↗',total.returnRate>=1?'positive':'negative')}${metric('仮想収支',`${total.profit>=0?'+':''}${money(total.profit)}`,'正式BUYは別管理','¥',total.profit>=0?'positive':'negative')}`:`${metric('検証済み','0 R','まず結果照合を入力','✓')}${metric('3連単的中','—','未検証','◎')}${metric('仮想回収率','—','未検証','↗')}${metric('仮想収支','—','未検証','¥')}`;
    return `${head('成績分析',`${getVenues().length}場を比較 / 仮想5万円 × 保存済み${allRaces().length}R`)}<div class="metrics">${metrics}</div><div class="columns-2"><section class="card card-pad"><div class="section-head"><h2 class="section-title">競艇場別の的中率</h2>${pill('検証済みのみ','local')}</div><div class="chart-grid">${groups.map(g=>`<div class="chart-item"><strong>${escape(g.venue)}</strong><div class="bar-back"><span class="bar-value" style="width:${g.all.examined?(100*g.all.hitRate).toFixed(1):0}%"></span></div><b>${g.all.examined?pct(g.all.hitRate):'—'}</b></div>`).join('')}</div><p class="charts-note">同じ8点、同じ仮想5万円の比較。的中率は結果入力済みレースのみが分母。</p><div class="notice">${total.examined?`頭候補捕捉 ${total.heads}/${total.examined}R、1・2着順一致 ${total.firstSeconds}/${total.examined}R、3着紐抜け ${total.thirdMiss}R。`:'まだ結果がないため、モデルの実力を判定できません。'}</div></section>
    <section class="card card-pad"><div class="section-head"><h2 class="section-title">WATCHとSKIPの比較</h2></div>${[['WATCH',watchTotal],['SKIP',skipTotal]].map(([name,s])=>`<div class="feature-card"><span class="feature-label">${name} · ${s.examined}/${s.count}R</span><strong>的中 ${s.hits}R${s.examined?' / '+pct(s.hitRate):''}</strong><p>仮想回収率 ${s.returnRate===null?'未算出':pct(s.returnRate)} ・ 収支 ${s.examined?money(s.profit):'未算出'}</p></div>`).join('')}<div class="notice warn">SKIPの仮想配分はベンチマーク用。実際に買ったと仮定した場合の数字で、正式な投資収支ではありません。</div></section></div>
    <div class="card card-pad" style="margin-top:18px"><div class="section-head"><h2 class="section-title">場別・モデル検証サマリー</h2></div><table class="bets-table"><thead><tr><th>場</th><th>照合</th><th>的中</th><th>仮想回収</th></tr></thead><tbody>${groups.map(g=>`<tr><td>${escape(g.venue)}</td><td>${g.all.examined}/${g.all.count}</td><td>${g.all.hits}R</td><td>${g.all.returnRate===null?'—':pct(g.all.returnRate)}</td></tr>`).join('')}</tbody></table></div><p class="footer-disclaimer">検証値には事後作成の予想を混ぜない。データの入手時刻と発走前固定を確認できる予想のみを、正式なモデル評価に使用します。</p>`;
  }
  function settings() {
    return `${head('データ管理',`予想データと結果を管理 / この端末のブラウザに保存`)}<div class="settings-grid"><section class="card settings-card"><span class="mini-caption">PREDICTION SOURCE</span><h2 class="section-title" style="margin:12px 0">発走前の固定データ</h2><p>${escape(state.origin)}。${data.mode==='auto-live'?'全国の出走表・展示・結果を非公式APIから自動取得。発走前に固定できたレースを掲載しています。':'新しい予想の自動取得はまだありません。'}</p><div class="meta-list"><div class="meta"><span>対象日</span><b>${dateDisplay(data.event_date)}</b></div><div class="meta"><span>予想件数</span><b>${data.forecast_races.length}R</b></div><div class="meta"><span>モデル</span><b>${data.mode==='auto-live'?'未訓練ヒューリスティック・展示2段階':'展示前・参考気象補正'}</b></div><div class="meta"><span>オッズ / 動画解析</span><b>未接続</b></div></div><div class="notice"><span class="mini-caption">GIT COMMIT</span><br><span class="code-ref">${escape(data.freeze_reference||'外部固定記録なし')}</span></div><div class="settings-btns" style="margin-top:14px"><a class="btn btn-soft" href="https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai" target="_blank" rel="noopener noreferrer">↗ GitHubを見る</a><button data-action="export-predictions" class="btn btn-white">↧ 予想JSON保存</button></div></section>
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
  function go(view) {state.view=view;state.raceDetail=null;render();window.scrollTo({top:0,behavior:'instant'});}
  function toast(message){const node=el('toast');node.textContent=message;node.classList.add('show');if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('show'),3200);}
  function download(name,content,type='text/plain;charset=utf-8') {const blob=new Blob([content],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
  function exportResultsCSV(){const header=['date','venue','race','classification','cutoff_jst','finish','payout_per_100','is_hit','stake_yen','virtual_payout_yen','virtual_profit_yen','recorded_at','source'];const body=allRaces().map(r=>{let c=compute(r);return [data.event_date,r.venue,r.race,r.classification,r.cutoff_jst,c.record?.finish||'',c.record?.payout_per_100??'',c.record?Number(c.hit):'',c.record?c.stake:'',c.payout??'',c.profit??'',c.record?.recorded_at||'',c.record?'manual':''];});const csv=[header,...body].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n');download(`boatlab-results-${data.event_date}.csv`,'\uFEFF'+csv,'text/csv;charset=utf-8');toast('結果CSVを書き出したよ');}
  function copyBets(r){const s=`${data.event_date} ${r.venue} ${r.race}R ${r.cutoff_jst} [${r.classification}] ${r.phase==='exhibition'?'展示反映':'展示前'}予想\n${r.scenario}\n${r.bets.map((b,i)=>`${i+1}. ${b.combination} ${money(b.virtual_yen)}`).join('\n')}\n合計 ${money(r.bets.reduce((s,b)=>s+b.virtual_yen,0))} / 研究用・仮想`;if(navigator.clipboard?.writeText)navigator.clipboard.writeText(s).then(()=>toast('買い目をコピーしたよ'),()=>toast('コピーできませんでした'));else {const t=document.createElement('textarea');t.value=s;document.body.append(t);t.select();document.execCommand('copy');t.remove();toast('買い目をコピーしたよ');}}
  document.addEventListener('click',e=>{
    const nav=e.target.closest('[data-view]');if(nav){go(nav.dataset.view);return;}
    const row=e.target.closest('[data-race]');if(row){const [v,n]=row.dataset.race.split('|');let r=findRace(v,n);if(!r)return;if(row.dataset.action==='settle-this'){state.resultVenue=v;state.resultRace=Number(n);go('results');return;}if(row.dataset.action==='copy-bets'){copyBets(r);return;}state.raceDetail=r;state.view='races';render();window.scrollTo(0,0);return;}
    const btn=e.target.closest('[data-action]');if(!btn)return;
    switch(btn.dataset.action){
      case 'go-races':go('races');break;
      case 'back-races':state.raceDetail=null;render();break;
      case 'export-results':exportResultsCSV();break;
      case 'export-predictions':download(`boatlab-predictions-${data.event_date}.json`,JSON.stringify(data,null,2),'application/json');toast('予想データを保存したよ');break;
      case 'export-backup':download(`boatlab-backup-${data.event_date}.json`,JSON.stringify({version:1,date:data.event_date,results},null,2),'application/json');toast('バックアップを書き出したよ');break;
      case 'reset-dataset':if(confirm('初期データに戻しますか？ 入力済みの結果は残ります。')){localStorage.removeItem(STORE_DATA);location.reload();}break;
      case 'clear-results':if(confirm('入力した結果をすべて削除します。この操作は元に戻せません。')){results={};persistResults();render();toast('結果データを削除しました');}break;
      case 'delete-result':{const r=findRace(state.resultVenue,state.resultRace);if(r&&confirm(`${r.venue} ${r.race}R の結果を取り消しますか？`)){delete results[raceKey(r)];persistResults();render();toast('入力を取り消しました');}break;}
    }
  });
  document.addEventListener('change',async e=>{
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
  async function reloadLiveIfNew(){
    if(readJSON(STORE_DATA,null))return;
    try{
      const incoming=await fetchLive();
      if(data&&incoming.event_date<data.event_date)return;
      if(incoming.updated_at_utc===lastLiveUpdate)return;
      data=incoming;autoResults=incoming.official_results||{};lastLiveUpdate=incoming.updated_at_utc||'';
      state.origin='非公式API＋GitHub Actions・発走前スナップショット';
      if(state.raceDetail)state.raceDetail=findRace(state.raceDetail.venue,state.raceDetail.race);
      if(state.venue!=='全場'&&!getVenues().includes(state.venue))state.venue='全場';
      state.resultVenue=getVenues().includes(state.resultVenue)?state.resultVenue:getVenues()[0];
      render();
    }catch(error){console.warn('Live data refresh failed:',error.message);}
  }
  async function init(){
    results=readJSON(STORE_RESULTS,{});
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
  window.BoatLab={validate:normalizeData,stats,compute,getData:()=>data};
  init();
})();