/* BOAT LAB venue board v1.2
 * Venue cards are derived from verified race snapshots only.
 * An inactive grey tile means "no information received", NOT "closed".
 * No grade, event day or session category is invented.
 */
(function () {
  'use strict';

  var VENUES = [
    ['桐生','01'],['戸田','02'],['江戸川','03'],['平和島','04'],
    ['多摩川','05'],['浜名湖','06'],['蒲郡','07'],['常滑','08'],
    ['津','09'],['三国','10'],['びわこ','11'],['住之江','12'],
    ['尼崎','13'],['鳴門','14'],['丸亀','15'],['児島','16'],
    ['宮島','17'],['徳山','18'],['下関','19'],['若松','20'],
    ['芦屋','21'],['福岡','22'],['唐津','23'],['大村','24']
  ];
  var DEFAULT_FAVORITES = ['住之江','鳴門','徳山','若松','唐津'];
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function safeTime(value) {
    return /^\d{2}:\d{2}$/.test(String(value || '')) ? value : null;
  }
  function recordStatus(data, venue, nowTime) {
    var full = (data.forecast_races || []).filter(function (r) { return r.venue === venue; });
    var absent = (data.unforecast_races || []).filter(function (r) { return r.venue === venue; });
    var map = {};
    full.forEach(function (r) { map[r.race] = {forecast:r, cutoff:safeTime(r.cutoff_jst)}; });
    absent.forEach(function (r) {
      if (!map[r.race]) map[r.race] = {unforecast:r,cutoff:safeTime(r.cutoff_jst)};
    });
    var slots = Object.keys(map).map(function (n) { return Object.assign({race:Number(n)},map[n]); });
    slots.sort(function (a,b) { return a.race-b.race; });
    var future = slots.filter(function (r) { return r.cutoff && r.cutoff > nowTime; })
      .sort(function (a,b) { return a.cutoff.localeCompare(b.cutoff); });
    var next = future[0] || null;
    var last = slots.filter(function (r) { return !!r.cutoff; })
      .sort(function (a,b) { return b.cutoff.localeCompare(a.cutoff); })[0] || null;
    var times = slots.filter(function (r) {return !!r.cutoff;}).map(function (r) {return r.cutoff;});
    times.sort();
    var first = times[0] || null;
    // Informational time-band icon only. This is NOT a confirmed race-session category.
    var session = first && first < '10:00' ? 'morning' : first && first >= '14:30' ? 'night' : 'day';
    var icon = session === 'morning' ? '🌅' : session === 'night' ? '🌙' : '☀️';
    var grade = '';
    var day = '';
    var metadata = (data.venue_metadata || {})[venue] || {};
    if (typeof metadata.grade === 'string') grade = metadata.grade;
    if (typeof metadata.event_day === 'string' || typeof metadata.event_day === 'number') day = String(metadata.event_day);
    return {
      name:venue, active:slots.length>0,forecast:full,unforecast:absent,slots:slots,
      next:next,last:last,first:first,session:session,icon:icon,
      grade:grade,day:day,ready:full.length,
      exhibition:full.filter(function (r) {return r.phase === 'exhibition';}).length,
      finished:!next && !!last,missing:absent.length
    };
  }

  function entries(data,now) {
    return VENUES.map(function (v) {return recordStatus(data,v[0],now);});
  }
  function sorted(items, opts) {
    var filter = opts.filter || 'all';
    var fav = opts.favorites || [];
    var sort = opts.sort || 'official';
    var filtered = filter === 'active' ? items.filter(function (x) {return x.active;}) :
      filter === 'favorite' ? items.filter(function (x) {return fav.indexOf(x.name)!==-1;}) : items.slice();
    var order = {};
    VENUES.forEach(function (v,i) { order[v[0]]=i; });
    if (sort === 'next') {
      filtered.sort(function (a,b) {
        var aa = a.active && a.next ? a.next.cutoff : '99:99';
        var bb = b.active && b.next ? b.next.cutoff : '99:99';
        return aa.localeCompare(bb) || order[a.name]-order[b.name];
      });
    } else if (sort === 'favorite') {
      filtered.sort(function (a,b) {
        return Number(fav.indexOf(b.name)!==-1)-Number(fav.indexOf(a.name)!==-1) ||
          Number(b.active)-Number(a.active) || order[a.name]-order[b.name];
      });
    }
    return filtered;
  }
  function badge(text,kind) {
    return '<span class="venue-badge venue-badge-'+esc(kind)+'">'+esc(text)+'</span>';
  }
  function card(entry,opts) {
    var favorite = (opts.favorites||[]).indexOf(entry.name)!==-1;
    var isDisabled = !entry.active;
    var title = entry.grade || '開催情報';
    var day = entry.day ? entry.day+'日目' : '日目未取得';
    var next = entry.next;
    var upcoming = next ? '<strong>'+esc(next.race)+'R</strong><span>'+esc(next.cutoff)+'</span>' :
      entry.last ? '<strong>最終 '+esc(entry.last.race)+'R</strong><span>'+esc(entry.last.cutoff)+'</span>' :
      '<strong>—</strong><span>—</span>';
    var stateText = !entry.active ? '情報未取得' :
      next ? '締切予定' : '本日の最終締切';
    var venueWx = (opts.weatherByVenue||{})[entry.name];
    var weatherSummary = venueWx && venueWx.wind_speed != null ? '🌬 風'+esc(venueWx.wind_speed)+'m/s・近隣予報' : '';
    var status = isDisabled ? badge('未取得','idle') :
      entry.exhibition ? badge('展示 '+entry.exhibition+'R','ready') :
      entry.ready ? badge('予想 '+entry.ready+'R','watch') : badge('未固定','missing');
    return '<article class="venue-card venue-theme-'+esc(entry.session)+(isDisabled?' venue-inactive':'')+'">' +
      '<button type="button" class="venue-favorite'+(favorite?' is-favorite':'')+'" data-favorite-venue="'+esc(entry.name)+'" aria-label="'+esc(entry.name)+'を'+(favorite?'お気に入りから外す':'お気に入りに追加')+'" aria-pressed="'+(favorite?'true':'false')+'">'+(favorite?'★':'☆')+'</button>' +
      '<button type="button" class="venue-open" data-open-venue="'+esc(entry.name)+'"'+(isDisabled?' disabled aria-disabled="true"':'')+'>' +
      '<span class="venue-topline"><span class="venue-emoji" aria-hidden="true">'+(entry.active?entry.icon:'⚓')+'</span><span class="venue-name">'+esc(entry.name)+'</span></span>' +
      '<span class="venue-meta">'+badge(title,entry.grade?'grade':'muted')+'<span>'+esc(day)+'</span></span>' +
      '<span class="venue-cutoff-caption">'+esc(stateText)+'</span>' +
      '<span class="venue-next">'+upcoming+'</span>' +
      (weatherSummary?'<span class="venue-card-weather">'+weatherSummary+'</span>':'') +
      '<span class="venue-progress">'+status+'<span>'+ (isDisabled?'—':'予想 '+entry.ready+'/12R') +'</span></span>' +
      '</button></article>';
  }
  function renderHome(data,opts) {
    var all=entries(data,opts.now);
    var held=all.filter(function (v) { return v.active; });
    var racing=held.filter(function (v) { return !!v.next; }).length;
    var ready=held.reduce(function (a,v) {return a+v.ready;},0);
    var expo=held.reduce(function (a,v) {return a+v.exhibition;},0);
    var view=sorted(all,opts);
    var official=Object.values(data.official_results||{}).filter(v=>v.source==='boatrace_official_pay'&&v.verified===true);
    var payout=official.reduce((sum,v)=>sum+(v.virtual_payout||0),0);
    var invested=official.reduce((sum,v)=>sum+(v.virtual_stake||0),0);
    var hits=official.filter(v=>v.hit).length;
    var weatherCount=Object.keys(data.venue_weather||{}).length;
    var date=esc(data.event_date||'—');
    var latest=data.updated_at_utc ? new Date(data.updated_at_utc).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}) : '取得時刻不明';
    var stale=opts.today && opts.today !== data.event_date;
    var filter=opts.filter||'all', sort=opts.sort||'official';
    var filters=[['all','全国24場'],['active','開催情報あり'],['favorite','★ お気に入り']].map(function (p) {
      return '<button type="button" class="venue-filter'+(filter===p[0]?' active':'')+'" data-venue-filter="'+p[0]+'" aria-pressed="'+(filter===p[0])+'">'+esc(p[1])+'</button>';
    }).join('');
    return '<div class="venue-board">' +
      '<div class="venue-hero"><div class="venue-hero-overline">BOAT LAB · AI予想ダッシュボード</div>' +
      '<h1>今日の開催一覧 <span>🚤</span></h1><p>'+date+' ・ 全国のレースを選んで予想を見る</p>' +
      '<div class="venue-hero-stats"><span><strong>'+held.length+'</strong>場 情報あり</span><span><strong>'+racing+'</strong>場 締切予定あり</span><span><strong>'+ready+'</strong>R 予想</span><span><strong>'+expo+'</strong>R 展示反映</span></div></div>' +
      (weatherCount?'<p class="venue-weather-coverage">🌦 開催中の周辺気象予報 '+weatherCount+'/'+held.length+'場取得済み（会場水面の実測ではありません） ・ <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Weather data by Open-Meteo.com ↗</a></p>':'') +
      (data.mode==='auto-live'?'<button type="button" class="venue-official-summary" data-view="results" aria-label="公式結果の照合画面を開く"><span>✅ BOATRACE公式照合 <b>'+official.length+'R</b></span><span>的中 <b>'+hits+'R</b></span><span>仮想回収 <b>'+(invested?(100*payout/invested).toFixed(1)+'%':'—')+'</b></span><span>詳細を見る →</span></button>':'') +
      (stale?'<div class="notice warn"><strong>過去日のデータです。</strong> 最新データはまだ取得できていません。対象日を確認してね。</div>':'') +
      '<div class="venue-board-head"><div><h2>開催場を選択</h2><p>カードをタップ → 全12R → 買い目・仮想配分</p></div>' +
      '<label class="venue-sort-label">並べ替え<select data-venue-sort aria-label="開催場の並べ替え">' +
      [['official','場番号順'],['next','次の締切順'],['favorite','お気に入り順']].map(function (p) {
        return '<option value="'+p[0]+'"'+(p[0]===sort?' selected':'')+'>'+p[1]+'</option>';
      }).join('')+'</select></label></div>' +
      '<div class="venue-filters">'+filters+'</div>' +
      '<div class="venue-card-grid">'+view.map(function (v) {return card(v,Object.assign({},opts,{weatherByVenue:data.venue_weather||{}}));}).join('')+'</div>' +
      (!view.length?'<div class="no-data">該当する競艇場がありません。</div>':'') +
      '<div class="venue-legend"><span>✅ 展示反映</span><span>📝 展示前予想</span><span>⚓ 情報未取得</span></div>' +
      '<p class="venue-disclaimer">最終取得 '+esc(latest)+' JST。締切は非公式データの予定値。グレード・開催日目は取得できた場合のみ表示します。灰色の場は「休催」ではなく開催情報未取得です。'+
      '新着は約10分間隔の取得設定ですが、遅延・欠損があります。BUY判断と実投票は行いません。</p></div>';
  }

  function officialForSlot(data,venue,number,forecast) {
    var k=data.event_date+'|'+venue+'|'+number;
    var issue=data.settlement_alerts&&data.settlement_alerts[k];
    if(issue)return {review:true,reason:issue.reason};
    var value=data.official_results&&data.official_results[k];
    if(!forecast||!value||value.source!=='boatrace_official_pay'||value.verified!==true)return null;
    if(value.snapshot_sha256&&forecast.sha256&&value.snapshot_sha256!==forecast.sha256)return null;
    return value;
  }
  function raceStatus(r,slot,now,data,venue,number) {
    var outcome=officialForSlot(data,venue,number,r);
    if(outcome&&outcome.review)return badge('要確認','missing');
    if(outcome)return badge(outcome.hit?'公式 的中':'公式 不的中',outcome.hit?'ready':'idle');
    if(!r)return slot&&slot.unforecast?badge('予想未固定','missing'):badge('情報未取得','idle');
    if(r.entry_exhibition_gate&&r.entry_exhibition_gate.entry_watch&&
       !r.entry_exhibition_gate.final_eligible)return badge('前付け警戒・展示待ち','missing');
    if(r.entry_exhibition_gate&&!r.entry_exhibition_gate.final_eligible)
      return badge('展示未確認・保留','watch');
    if(r.phase==='exhibition')return badge('展示反映','ready');
    if(r.classification==='SKIP')return badge('SKIP','missing');
    if(slot&&slot.cutoff&&slot.cutoff<=now)return badge('展示前固定','watch');
    return badge('展示前予想','watch');
  }
  function raceTile(venue,number,slot,now,data) {
    var r=slot&&slot.forecast;
    var cutoff=slot&&slot.cutoff;
    var experiment=null;
    if(r&&window.BoatTacticalModel&&!(r.entry_exhibition_gate?.entry_watch&&!r.entry_exhibition_gate?.final_eligible)){
      try{experiment=window.BoatTacticalModel.forecast(r)}catch(e){experiment=null;}
    }
    var outcome=officialForSlot(data,venue,number,r);
    var eventWx=r&&r.weather_used;
    var weather=(eventWx || (r&&r.weather_observed&&r.weather_observed.wind_speed!=null&&Object.assign({site_observed:true},r.weather_observed)) || (data.venue_weather||{})[venue]);
    var weatherLabel=weather ? (eventWx?(eventWx.site_observed?'予想時の場内展示':'予想時の周辺予報'):
      r&&r.weather_observed?'予想時の場内展示':'最新取得分の近隣予報・予想未反映') : '';
    var weatherInfo=weather && weather.wind_speed!=null ? '<div class="venue-race-weather">🌬 '+esc(weatherLabel)+' 風'+esc(weather.wind_speed)+'m/s'+(weather.wave_height!=null?' ／ 波'+esc(weather.wave_height)+'cm':'')+(r&&r.weather_adjustment&&r.weather_adjustment.applied?' ／ 気象補正試験':'')+'</div>':'';
    var payInfo=outcome && !outcome.review ?
      '<div class="venue-race-result">公式3連単 '+esc(outcome.finish)+' ／ 払戻 '+Number(outcome.payout_per_100).toLocaleString('ja-JP')+'円</div>':
      outcome&&outcome.review?'<div class="venue-race-result">公式結果：返還・中止などの確認待ち</div>':'';
    return '<div class="venue-race'+(r?' venue-race-available':' venue-race-empty')+'">' +
      '<div class="venue-race-top"><b>'+number+'R</b>'+raceStatus(r,slot,now,data,venue,number)+'</div>' +
      '<div class="venue-race-cutoff"><span>締切予定</span><strong>'+esc(cutoff||'—')+'</strong></div>' +
      (r?'<div class="venue-race-main">🔒 固定：'+esc(r.bets.slice(0,2).map(function (b){return b.combination;}).join(' / '))+'</div>' +
          (experiment?'<div class="venue-tactical">🧠 新・1M戦法研究：<b>'+esc(experiment.top)+'</b> ／ '+experiment.bets.length+'点'+(experiment.differs_from_frozen?'（変更あり）':'（配分同じ）')+'</div>':'') +
          '<div class="venue-race-scene">'+esc(r.scenario||'展開予想あり')+'</div>' +
          weatherInfo+payInfo+
          '<button type="button" class="venue-race-action" data-race="'+esc(venue)+'|'+number+'">買い目 '+r.bets.length+'点を見る →</button>' :
          '<p class="venue-race-muted">'+(slot&&slot.unforecast?'発走前の予想を固定できませんでした':'締切・出走表未取得')+'</p>') +
      '</div>';
  }
  function renderVenue(data,venue,opts) {
    var x=recordStatus(data,venue,opts.now);
    var map={};
    x.slots.forEach(function (v) {map[v.race]=v;});
    var allRaces=Array.from({length:12},function (_,i) {return raceTile(venue,i+1,map[i+1],opts.now,data);}).join('');
    var rawDay=x.day?x.day+'日目':'開催日目未取得';
    return '<div class="venue-detail-board">' +
      '<button type="button" class="venue-back" data-action="back-overview">← 開催一覧へ戻る</button>' +
      '<div class="venue-detail-hero"><span class="venue-detail-symbol">'+x.icon+'</span><div><div class="venue-hero-overline">BOAT LAB / '+esc(data.event_date)+'</div><h1>'+esc(venue)+' <small>全12R</small></h1><p>'+esc(x.grade||'グレード未取得')+' ・ '+esc(rawDay)+' ・ 自動予想 '+x.ready+'/12R ・ 展示反映 '+x.exhibition+'R</p></div></div>' +
      '<div class="venue-race-legend"><span>'+badge('公式 的中','ready')+' 公式払戻で的中</span><span>'+badge('展示反映','ready')+' 実測展示あり</span><span>'+badge('展示前','watch')+' 出走表中心</span><span>'+badge('未固定','missing')+' 後出し予想なし</span></div>' +
      ((data.venue_weather||{})[venue]?'<div class="venue-current-weather">🌦 最終取得時点の周辺予報：風'+esc(data.venue_weather[venue].wind_speed)+'m/s・突風'+esc(data.venue_weather[venue].wind_gust??'—')+'m/s・降水'+esc(data.venue_weather[venue].precipitation_mm??'—')+'mm/h　（現地実測ではありません） <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Weather data by Open-Meteo.com ↗</a></div>':'') +
      '<div class="venue-race-grid">'+allRaces+'</div>' +
      '<div class="notice">全12Rを表示していますが、データが来ていないレースや締切前の予想がなかったレースは買い目を作りません。表示時刻はJST・予定値で、公式の締切を優先してください。</div></div>';
  }
  window.BoatVenueBoard={
    VENUES:VENUES,
    DEFAULT_FAVORITES:DEFAULT_FAVORITES,
    entries:entries,
    sorted:sorted,
    renderHome:renderHome,
    renderVenue:renderVenue
  };
})();
