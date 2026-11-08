/* BOAT LAB × WEATHER LAB: read-only, source-labelled context on race view.
 * Never modifies frozen predictions, classifications, tickets, SHA or results.
 * Only first pre-cutoff frozen wave evidence can be marked as such.
 */
(function(root){
  'use strict';
  const BASE='https://raw.githubusercontent.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/weather-lab-data/weather_lab/data/';
  const SCHEMAS={
    regional:'weather_lab.regional_jma_forecast.v1',
    wave:'weather_lab.water_surface_monitor.v1',
    tide:'weather_lab.jma_tide_reference.v1',
    frozen:'weather_lab.forward_weather_evidence.v1',
    scenario:'weather_lab.forward_weather_scenario.v1',
  };
  const VENUES=['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const validDay=d=>typeof d==='string'&&/^20\d\d-\d\d-\d\d$/.test(d);
  const numeric=x=>typeof x==='number'&&Number.isFinite(x)?x:null;
  const ms=x=>{const n=Date.parse(x||'');return Number.isFinite(n)?n:null;};
  const nameCode=name=>{const i=VENUES.indexOf(name);return i>=0?String(i+1).padStart(2,'0'):null;};
  const URLS={regional:BASE+'regional/latest.json',wave:BASE+'latest.json',tide:BASE+'tide/latest.json'};
  function sourceIsToday(doc,schema,day){
    return doc&&doc.schema===schema&&doc.event_date===day;
  }
  function cutoffTime(race,day){
    if(!race||!validDay(day)||!/^([01]\d|2[0-3]):[0-5]\d$/.test(race.cutoff_jst||''))return null;
    return ms(day+'T'+race.cutoff_jst+':00+09:00');
  }
  function closestForecast(row,cutoff){
    if(!row||!Number.isFinite(cutoff))return null;
    const options=(Array.isArray(row.hourly)?row.hourly:[]).filter(v=>
      numeric(v?.wind_mps)!==null&&ms(v.valid_at_jst)!==null&&
      Math.abs(ms(v.valid_at_jst)-cutoff)<=3600000);
    if(!options.length)return null;
    return options.reduce((a,b)=>Math.abs(ms(a.valid_at_jst)-cutoff)<=Math.abs(ms(b.valid_at_jst)-cutoff)?a:b);
  }
  function selectContext(feeds,race,day){
    const code=nameCode(race?.venue);
    const cutoff=cutoffTime(race,day);
    const valid=!!(code&&cutoff!==null&&Number.isInteger(race?.race)&&race.race>=1&&race.race<=12);
    const result={valid,code,cutoff,wave:null,waveStatus:'missing',regional:null,
      regionalStatus:'missing',tideCount:0,tideStatus:'missing',flowStatus:'not_connected',preCutoffEvidence:false,
      scenario:null,scenarioStatus:'unavailable'};
    if(!valid)return result;
    const frozen=feeds?.frozen,water=feeds?.wave,regional=feeds?.regional,tide=feeds?.tide;
    const match=doc=>sourceIsToday(doc,SCHEMAS.frozen,day)&&Array.isArray(doc.records)?
      doc.records.find(x=>x.venue_code===code&&x.race===race.race):null;
    const witnessed=match(frozen);
    const cutoffSafe=cutoff-180000;
    const receipt=ms(witnessed?.collector_received_at_utc);
    const source=ms(witnessed?.source_captured_at_jst);
    const observed=ms(witnessed?.weather_observed_at_jst);
    const h=numeric(witnessed?.weather?.wave_cm);
    if(witnessed&&h!==null&&h>=0&&h<=150&&receipt!==null&&source!==null&&observed!==null&&
       receipt<=cutoffSafe&&source<=receipt&&observed<=source+120000&&
       receipt-source<=15*60000&&receipt-observed<=20*60000&&
       typeof witnessed.weather_evidence_sha256==='string'&&/^[a-f0-9]{64}$/.test(witnessed.weather_evidence_sha256)){
      result.wave={cm:h,at:witnessed.weather_observed_at_jst,source:'場内波高・発走前固定'};
      result.waveStatus='precutoff_frozen';result.preCutoffEvidence=true;
    }else if(sourceIsToday(water,SCHEMAS.wave,day)&&Array.isArray(water.races)){
      const r=water.races.find(x=>x.venue_code===code&&x.race===race.race);
      const raw=numeric(r?.weather?.wave_cm);
      if(raw!==null&&raw>=0&&raw<=150){
        result.wave={cm:raw,at:r.weather_observed_at_jst,source:'場内波高・閲覧用'};
        result.waveStatus='reference_unfrozen';
      }else if(r){result.waveStatus='incomplete';}
    }
    if(sourceIsToday(regional,SCHEMAS.regional,day)&&Array.isArray(regional.venues)&&regional.venues.length===24){
      const site=regional.venues.find(v=>v.code===code);
      const forecast=closestForecast(site,cutoff);
      const retrieved=ms(regional.retrieved_at_utc);
      if(forecast&&retrieved!==null){
        result.regional=forecast;
        result.regionalStatus=retrieved<=cutoffSafe?'model_retrieved_pre_cutoff':'model_reference_after_cutoff';
      }
    }
    if(sourceIsToday(tide,SCHEMAS.tide,day)&&Array.isArray(tide.stations)){
      result.tideCount=tide.stations.filter(s=>['TK','OS','ST'].includes(s.station_code)
        &&s.data_kind==='astronomical_tide_prediction_not_measured'
        &&s.on_course_station===false).length;
      result.tideStatus=result.tideCount?'unmapped_reference_only':'missing';
    }
    const sc=feeds?.scenario;
    if(sourceIsToday(sc,SCHEMAS.scenario,day)&&Array.isArray(sc.records)){
      const item=sc.records.find(x=>x.venue_code===code&&x.race===race.race&&
        x.race_code===day.replace(/-/g,'')+code+String(race.race).padStart(2,'0'));
      const at=ms(item?.recorded_at_utc),src=ms(item?.wave_source_captured_at_jst),
        obs=ms(item?.wave_observed_at_jst),modelAt=ms(item?.regional_retrieved_at_utc);
      const wind=numeric(item?.nearby_model_wind_mps),waveCm=numeric(item?.on_course_wave_cm);
      const flags=item?.signals;
      const allowed=['nearby_model_wind_ge_6mps','on_course_wave_ge_5cm','wind_wave_joint_attention'];
      if(item&&at!==null&&src!==null&&obs!==null&&modelAt!==null&&
          at<=cutoffSafe&&modelAt<=at&&src<=at&&obs<=at&&obs<=src+120000&&
          at-src<=15*60000&&at-obs<=20*60000&&
          wind!==null&&wind>=0&&wind<=80&&waveCm!==null&&waveCm>=0&&waveCm<=150&&
          Array.isArray(flags)&&flags.every(x=>allowed.includes(x))&&
          ['research_attention','research_baseline'].includes(item.status)&&
          item.formal_prediction_modified===false&&item.bets_changed===false&&
          item.headwind_tailwind==='unverified_not_inferred'&&
          typeof item.evidence_sha256==='string'&&/^[a-f0-9]{64}$/.test(item.evidence_sha256)){
        result.scenario={
          attention:item.status==='research_attention',wind, waveCm,
          flags:flags.slice(),recordedAt:item.recorded_at_utc,
        };
        result.scenarioStatus='precutoff_research_only';
      }
    }
    return result;
  }
  function renderContext(ctx,race,day){
    const code=ctx.code;
    if(!ctx.valid)return '<section class="card card-pad"><h2>🌊 WEATHER LAB</h2><p>場と締切時刻を確認できないため、気象データは連携していません。</p></section>';
    const wave=ctx.wave?esc(ctx.wave.cm)+'cm':'未取得';
    const waveNote=ctx.waveStatus==='precutoff_frozen'?'発走前固定・波高の取得時刻を検証済み':
      ctx.waveStatus==='reference_unfrozen'?'参考記録（発走前の固定証拠ではありません）':
      ctx.waveStatus==='incomplete'?'波高欠損':'未取得（0cmではありません）';
    const speed=ctx.regional?esc(ctx.regional.wind_mps)+'m/s':'未取得';
    const temp=ctx.regional&&numeric(ctx.regional.air_c)!==null?esc(ctx.regional.air_c)+'℃':'未取得';
    const windNote=ctx.regionalStatus==='model_retrieved_pre_cutoff'?'発走前に取得した近隣モデル予報':
      ctx.regionalStatus==='model_reference_after_cutoff'?'発走後取得の参照予報（事前予想の根拠にはできません）':'予報未取得';
    const tideNote=ctx.tideCount?ctx.tideCount+'参照地点（場内との対応未検証）':'未取得';
    const href='./weather/?venue='+encodeURIComponent(code);
    const scenarioText=ctx.scenario?
      '<div class="meta"><span>気象展開チェック（発走前・研究）</span><b>'+
      (ctx.scenario.attention?'展開の不確実性を再確認':'強い気象注意シグナルなし')+
      '</b><small>近隣モデル風 '+esc(ctx.scenario.wind)+'m/s・場内波高 '+esc(ctx.scenario.waveCm)+
      'cm。着順・コース別有利不利は未推定。買い目への自動補正なし。</small></div>':
      '<div class="meta"><span>気象展開チェック（発走前・研究）</span><b>未固定</b>'+
      '<small>締切前の波高と近隣予報が揃った場合のみ表示。欠損をゼロ扱いしません。</small></div>';
    return '<section class="card card-pad boat-weather-lab-bridge" data-weather-link="verified-read-only" style="margin:16px 0">'+
      '<div class="section-head"><h2 class="section-title">🌊 WEATHER LAB × BOAT LAB</h2>'+
      '<a class="btn btn-soft" href="'+href+'" target="_blank" rel="noopener noreferrer">場別データを開く</a></div>'+
      '<p class="help">'+esc(day)+' '+esc(race.venue)+' '+esc(race.race)+'R　締切 '+esc(race.cutoff_jst)+
      '／独立データ閲覧・検証用。正式買い目と評価には反映していません。</p>'+
      '<div class="meta-list">'+
      '<div class="meta"><span>場内波高</span><b>'+wave+'</b><small>'+esc(waveNote)+'</small></div>'+
      '<div class="meta"><span>近隣の風・気温（JMAモデル）</span><b>'+speed+' ／ '+temp+'</b><small>'+esc(windNote)+'</small></div>'+
      '<div class="meta"><span>天文潮位（気象庁）</span><b>'+esc(tideNote)+'</b><small>参照地点の予測。場内水位の推定ではありません。</small></div>'+
      '<div class="meta"><span>潮流の速さ・向き</span><b>未取得</b><small>流速・流向は潮位から推定しません。</small></div>'+scenarioText+'</div>'+
      '<p class="help">選手・モーター・展示・進入・展開が予想の主因。気象は補正研究のみ。事後に入手した値は発走前データとして使いません。</p></section>';
  }
  const cache=new Map();
  async function getJSON(url){
    const response=await root.fetch(url,{cache:'no-store'});
    if(!response.ok)throw new Error('Data source HTTP '+response.status);
    return response.json();
  }
  async function load(day){
    if(!validDay(day))return {};
    const hit=cache.get(day);
    if(hit&&Date.now()-hit.at<60000)return hit.doc;
    const items=[['regional',URLS.regional],['wave',URLS.wave],['tide',URLS.tide],
      ['frozen',BASE+'forward/'+day+'.json'],
      ['scenario',BASE+'scenarios/'+day+'.json']];
    const entries=await Promise.all(items.map(async([key,url])=>{
      try{return [key,await getJSON(url)];}catch{return [key,null];}
    }));
    const doc=Object.fromEntries(entries);
    cache.set(day,{doc,at:Date.now()});
    return doc;
  }
  async function mount(main,race,day){
    if(!main||!race||!validDay(day))return;
    const section=root.document.createElement('div');
    section.className='weather-lab-bridge-host';
    section.textContent='🌊 WEATHER LAB：波高・広域風・潮位データを照合中…';
    // Keep the context visible near the race heading, not below a long ticket list.
    main.insertBefore(section,main.firstElementChild?.nextSibling||null);
    const code=nameCode(race.venue);
    if(!code){section.textContent='WEATHER LAB：このレース場は未対応';return;}
    const feeds=await load(day);
    if(!section.isConnected)return;
    section.innerHTML=renderContext(selectContext(feeds,race,day),race,day);
  }
  const api={SCHEMAS,URLS,nameCode,cutoffTime,closestForecast,selectContext,renderContext,load,mount};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(root&&root.document)root.BoatWeatherLabLink=api;
})(typeof window!=='undefined'?window:globalThis);
