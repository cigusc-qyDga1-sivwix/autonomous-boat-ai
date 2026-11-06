/* WEATHER LAB standalone PWA. Data read-only from the dedicated weather-lab-data branch. */
(function(root){
  "use strict";
  const DATA_URL="https://raw.githubusercontent.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/weather-lab-data/weather_lab/data/latest.json";
  const SCHEMA="weather_lab.water_surface_monitor.v1";
  const REGIONAL_SCHEMA="weather_lab.regional_jma_forecast.v1";
  const TIDE_SCHEMA="weather_lab.jma_tide_reference.v1";
  const TIDE_URL="https://raw.githubusercontent.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/weather-lab-data/weather_lab/data/tide/latest.json";
  const REGIONAL_URL="https://raw.githubusercontent.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/weather-lab-data/weather_lab/data/regional/latest.json";
  const VENUES=["桐生","戸田","江戸川","平和島","多摩川","浜名湖","蒲郡","常滑",
   "津","三国","びわこ","住之江","尼崎","鳴門","丸亀","児島",
   "宮島","徳山","下関","若松","芦屋","福岡","唐津","大村"];
  const LIMITS={weather:20,source:15}; // Research alert thresholds, not forecast criteria
  const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const num=x=>(typeof x==="number"&&Number.isFinite(x)?x:null);
  const japaneseDate=when=>new Intl.DateTimeFormat("ja-JP",{timeZone:"Asia/Tokyo",year:"numeric",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(when);
  const shortTime=value=>{const t=Date.parse(value||"");return Number.isFinite(t)?new Intl.DateTimeFormat("ja-JP",{timeZone:"Asia/Tokyo",hour:"2-digit",minute:"2-digit"}).format(t):"時刻未確認";};
  const dayJST=when=>new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"}).format(when);
  const ageMinutes=(at,now)=>{let t=Date.parse(at||"");return Number.isFinite(t)?Math.round((now-t)/60000*10)/10:null;};
  function quality(row,now=Date.now()){
    if(!row)return "missing";
    if(num(row.weather?.wave_cm)===null)return "incomplete";
    const obs=ageMinutes(row.weather_observed_at_jst,now);
    const src=ageMinutes(row.source_captured_at_jst,now);
    if(obs===null||src===null||obs < -1||src < -1)return "unknown";
    if(obs>LIMITS.weather||src>LIMITS.source)return "stale";
    return "fresh";
  }
  const labels={
    fresh:["新鮮","fresh"],stale:["観測が古い","stale"],
    incomplete:["データ不完全","bad"],unknown:["時刻未確認","bad"],
    missing:["データなし","none"],failed:["取得元に障害","bad"]};
  function latestRow(rows){
    return [...rows].sort((a,b)=>(Date.parse(b.source_captured_at_jst||"")||0)-(Date.parse(a.source_captured_at_jst||"")||0)||Number(b.race||0)-Number(a.race||0))[0]||null;
  }
  function summary(doc,now=Date.now()){
    if(!doc||doc.schema!==SCHEMA||!Array.isArray(doc.venues)||!Array.isArray(doc.races))return null;
    const available=doc.venues.filter(v=>Number(v.race_snapshots)>0).length;
    return {venues:available,races:doc.races.length,fresh:doc.races.filter(r=>quality(r,now)==="fresh").length,
      day:doc.event_date,source_ok:doc.provider?.fetch_status==="ok"||doc.provider?.fetch_status==="ok_empty",
      age:ageMinutes(doc.collected_at_utc,now)};
  }
  const UNIT_VALUE=(value,unit)=>num(value)===null?"—":String(value)+unit;
  function regionalEntry(doc,code,now=Date.now()){
    if(doc?.schema!==REGIONAL_SCHEMA||doc.event_date!==dayJST(now))return null;
    const age=ageMinutes(doc.retrieved_at_utc,now);
    if(age===null||age < -5||age > 180||!Array.isArray(doc.venues)||doc.venues.length!==24)return null;
    const row=doc.venues.find(v=>v.code===code),model=row?.model_current;
    if(!row||num(model?.wind_mps)===null||!Number.isFinite(Date.parse(model?.valid_at_jst||"")))return null;
    return {row,model,age};
  }
  function venueRows(doc,code){return (doc?.races||[]).filter(r=>r.venue_code===code);}
  function venueView(v,doc,now){
    const rows=venueRows(doc,v.code);
    const row=latestRow(rows);
    const q=doc.provider?.fetch_status==="unavailable"?"failed":quality(row,now);
    return {venue:v,row,rows,quality:q};
  }
  function displayLabel(q){return labels[q]||labels.unknown;}
  function renderVenueCard(item,selected){
    const v=item.venue,row=item.row,q=item.quality,chip=displayLabel(q);

    const wave=row?UNIT_VALUE(row.weather?.wave_cm,""):"—";
    const note=row?"最新："+row.race+"R・観測 "+shortTime(row.weather_observed_at_jst):
      q==="failed"?"取得元への接続を確認":"対象日の記録なし";
    return '<button type="button" class="venue-card is-'+esc(q)+(selected===v.code?' selected':'')+'" data-venue="'+esc(v.code)+'" aria-pressed="'+String(selected===v.code)+'">'+
      '<span class="card-head"><span><span class="venue-id">VENUE '+esc(v.code)+'</span><h3>'+esc(v.name)+'</h3></span>'+
      '<span class="status-chip '+esc(chip[1])+'">場内 '+esc(chip[0])+'</span></span>'+
      '<span class="venue-metrics"><span class="venue-metric"><small>場内波高</small><strong>'+esc(wave)+'<span>cm</span></strong></span>'+
      '</span>'+
      '<span class="card-foot"><span>'+esc(note)+'</span><strong>'+item.rows.length+'R</strong></span>'+
      (v.code==="03"?'<span class="scope-note">BOAT LABの予想対象外</span>':'')+
      (item.regional?'<span class="regional-forecast"><span class="regional-caption">近隣JMAモデル予報（場内実測ではない）</span>'+
        '<strong>風 '+esc(UNIT_VALUE(item.regional.model.wind_mps,"m/s"))+
        ' ／ 気温 '+esc(UNIT_VALUE(item.regional.model.air_c,"℃"))+'</strong>'+
        '<small>予報対象 '+esc(shortTime(item.regional.model.valid_at_jst))+'</small></span>':'')+
      '</button>';
  }
  function renderRace(row,now){
    const q=quality(row,now),chip=displayLabel(q);
    const sourceAge=ageMinutes(row.source_captured_at_jst,now),obsAge=ageMinutes(row.weather_observed_at_jst,now);
    const flags=[
      q==="fresh"?'<span class="flag good">暫定鮮度基準内</span>':'<span class="flag">古い記録は現在の状況を示しません</span>',


      q==="fresh"&&row.weather_advisory?.status==="attention"?'<span class="flag">気象注意・研究用：'+esc((row.weather_advisory.alerts||[]).join("／"))+'</span>':'',
    ].join("");
    return '<article class="race-card"><div class="race-row"><strong>'+esc(row.race)+'R</strong>'+
      '<span class="status-chip '+esc(chip[1])+'">'+esc(chip[0])+'</span><small>締切 '+esc(row.cutoff_jst||"不明")+'</small></div>'+
      '<div class="race-readings">'+
      '<div class="race-reading"><span>場内波高</span><strong>'+esc(UNIT_VALUE(row.weather?.wave_cm,""))+'<em>cm</em></strong></div>'+
      '</div>'+
      '<div class="flags">'+flags+'</div>'+
      '<div class="race-time">気象観測：'+esc(shortTime(row.weather_observed_at_jst))+
      (obsAge!==null?'（'+esc(obsAge)+'分前）':'')+
      '<br>元データ取得：'+esc(shortTime(row.source_captured_at_jst))+
      (sourceAge!==null?'（'+esc(sourceAge)+'分前）':'')+
      '<br>場内データは波高のみ。風・気温は近隣モデル予報を参照。</div></article>';
  }
  function renderDetail(item,doc,now){
    if(!item)return '<div class="detail-empty"><span aria-hidden="true">↗</span><h2>レース場を選択</h2><p>場をタップすると、1〜12Rの風・波・観測時刻を確認できます。</p></div>';
    const v=item.venue,rows=[...item.rows].sort((a,b)=>Number(b.race)-Number(a.race));
    const count='<b>'+rows.length+'R</b>';
    const regional=item.regional;
    const regionalHTML=regional?'<article class="race-card"><strong>近隣JMA数値モデル予報（Open-Meteo配信）</strong>'+
      '<div class="race-time">予報対象時刻 '+esc(shortTime(regional.model.valid_at_jst))+
      '／風速 '+esc(UNIT_VALUE(regional.model.wind_mps,"m/s"))+
      '／気温 '+esc(UNIT_VALUE(regional.model.air_c,"℃"))+
      '／取得から '+esc(regional.age)+'分</div>'+
      '<p>これはレース場の実測ではありません。波高・潮位は未取得で、正式買い目への自動反映はありません。</p></article>':'';
    const notes= v.code==="03"?"江戸川は収集監査のみ。BOAT LABの正式予想対象外。":"WEATHER LABは監視専用。正式予想に自動適用しません。";
    return '<div class="detail-heading"><div><span class="section-kicker">RACE DETAILS ・ VENUE '+esc(v.code)+'</span><h2>'+esc(v.name)+' の気象記録</h2>'+
      '<p class="detail-meta">'+esc(doc.event_date)+' の記録 '+count+' ／ '+esc(notes)+
      '<br>潮位・潮流：<b>未取得</b>（ゼロではありません）</p></div><span class="status-chip '+esc(displayLabel(item.quality)[1])+'">'+esc(displayLabel(item.quality)[0])+'</span></div>'+
      regionalHTML+
      (rows.length?'<div class="detail-list">'+rows.map(r=>renderRace(r,now)).join("")+'</div>':
        '<div class="no-results">この日のレース別気象記録はありません。未開催・公開前・提供元欠損は区別して監査中です。</div>');
  }
  function tidePanel(doc,now=Date.now()){
    if(doc?.schema!==TIDE_SCHEMA||doc.event_date!==dayJST(now)||!Array.isArray(doc.stations)||!doc.stations.length)
      return '<h2>潮位・潮流（独立データ）</h2><p>潮位は未取得。潮流の流速・流向は未接続です。</p>';
    const trusted={TK:"東京",OS:"大阪",ST:"洲本"};
    const stations=doc.stations.filter(x=>trusted[x.station_code]===x.station_name);
    const row=x=>x.map(t=>t.time_jst+" "+t.height_cm_datum+"cm").join("・")||"未取得";
    return '<h2>気象庁・参照地点の潮位予測</h2><p>天文潮位の予測です。レース場内の水位・潮流ではありません。</p>'+
      '<div class="info-grid">'+stations.map(st=>'<div><strong>'+esc(st.station_name)+'（参照地点）</strong>'+
        '<p>満潮 '+esc(row(st.high_tides||[]))+'</p><p>干潮 '+esc(row(st.low_tides||[]))+'</p></div>').join("")+'</div>'+
      '<p>潮流の流速・流向：未取得。海上保安庁の潮流推算との地点対応・API認証を確認中。潮位から潮流を推定しません。</p>';
  }
  const api={quality,ageMinutes,dayJST,summary,venueView,regionalEntry,tidePanel,latestRow,renderVenueCard,renderRace,renderDetail,esc};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(!root.document)return;

  const D=root.document;
  const $=id=>D.getElementById(id);
  const state={doc:null,regional:null,tide:null,regionalError:null,tideError:null,filter:"all",search:"",selected:null,loading:false,error:null};
  // Optional BOAT LAB deep link; only allow the predeclared 24 venue codes.
  const requestedVenue=(()=>{try{const v=new URLSearchParams(root.location?.search||"").get("venue");return /^(0[1-9]|1[0-9]|2[0-4])$/.test(v||"")?v:null;}catch{return null;}})();
  if(requestedVenue)state.selected=requestedVenue;
  function setToast(msg){
    const toast=$("toast");
    toast.textContent=msg;toast.classList.add("show");
    clearTimeout(setToast.timeout);
    setToast.timeout=setTimeout(()=>toast.classList.remove("show"),3500);
  }
  function render(){
    const now=Date.now(),doc=state.doc,stats=summary(doc,now);
    $("stat-monitored").innerHTML='24<small>場</small>';
    $("stat-venues").textContent=stats?stats.venues:"—";
    $("stat-races").textContent=stats?stats.races:"—";
    $("stat-fresh").textContent=stats?stats.fresh:"—";
    const regionalCount=VENUES.reduce((n,_,i)=>n+(regionalEntry(state.regional,String(i+1).padStart(2,"0"),now)?1:0),0);
    const modelCountNode=$("stat-regional"),modelNoteNode=$("stat-regional-note");
    // An older installed PWA shell can temporarily coexist with new JS.
    if(modelCountNode)modelCountNode.textContent=regionalCount||"—";
    if(modelNoteNode)modelNoteNode.textContent=regionalCount?
      "取得 "+shortTime(state.regional.retrieved_at_utc)+"（近隣モデル予報）":
      state.regionalError?"通信・提供元を確認":"広域予報の取得待ち";
    $("stat-venue-note").textContent=stats?stats.day+"の記録":"本日の記録";
    const when=doc?.collected_at_utc?japaneseDate(new Date(doc.collected_at_utc)):"未取得";
    $("updated-label").textContent="最終取得： "+when+" JST";
    const alert=$("data-alert"),health=$("source-health");
    alert.className="alert";health.className="hero-tag";
    if(state.error||!doc||stats?.source_ok===false){
      alert.classList.add(regionalCount?"is-warn":"is-error");
      health.classList.add(regionalCount?"is-stale":"is-error");
      health.textContent=regionalCount?"広域予報 "+regionalCount+"場取得":"取得元・通信エラー";
      alert.textContent=regionalCount?
        "場内波高は未取得ですが、近隣JMAモデル予報を"+regionalCount+"場で表示しています。カードの予報は場内実測ではありません。":
        "場内実測と広域予報を確認できません。推測で補いません。"+
          (state.regionalError?" 広域予報："+state.regionalError:"");
    }else if(stats.age===null||stats.age>15||stats.fresh===0){
      alert.classList.add("is-warn");health.classList.add("is-stale");
      health.textContent=regionalCount?"広域予報 "+regionalCount+"場取得":"過去の観測データ";
      alert.textContent="場内の新鮮な実測は"+stats.fresh+"件。"+
        (regionalCount?"近隣JMAモデル予報は"+regionalCount+"場で確認できます（場内実測ではありません）。":
        "古い波高記録を現在の水面状況として使用しないでください。");
    }else{
      health.textContent="場内観測 "+stats.fresh+"件";
      alert.textContent="場内の新鮮な波高"+stats.fresh+"件／近隣モデル予報"+regionalCount+"場。実測と予報は別のデータです。";
    }
    const items=(doc?doc.venues.map(v=>venueView(v,doc,now)):VENUES.map((name,i)=>
      venueView({name,code:String(i+1).padStart(2,"0"),race_snapshots:0},{provider:{fetch_status:state.error?"unavailable":"ok"},races:[]},now)))
      .map(item=>({...item,regional:regionalEntry(state.regional,item.venue.code,now)}));
    const filtered=items.filter(it=>{
      const q=it.quality;
      if(state.filter==="available"&&!it.rows.length&&!it.regional)return false;
      if(state.filter==="fresh"&&q!=="fresh")return false;
      if(state.filter==="stale"&&!["stale","incomplete","unknown"].includes(q))return false;
      if(state.filter==="missing"&&!["missing","failed"].includes(q))return false;
      return !state.search||it.venue.name.includes(state.search)||it.venue.code.includes(state.search);
    });
    $("venues").innerHTML=filtered.length?filtered.map(v=>renderVenueCard(v,state.selected)).join(""):
      '<div class="no-results">該当するレース場はありません。絞り込みを変更してください。</div>';
    $("detail").innerHTML=renderDetail(items.find(it=>it.venue.code===state.selected)||null,doc||{event_date:"—"},now);
    if($("tide-reference"))$("tide-reference").innerHTML=tidePanel(state.tide,now);
  }
  async function reload(manual=false){
    if(state.loading)return;
    state.loading=true;$("refresh").disabled=true;
    if(!state.doc)$("venues").innerHTML='<div class="skeleton">保存された気象記録を読み込み中…</div>';
    try{
      const response=await root.fetch(DATA_URL+"?ts="+Date.now(),{cache:"no-store"});
      if(!response.ok)throw new Error("HTTP "+response.status);
      const doc=await response.json();
      if(doc?.schema!==SCHEMA||!Array.isArray(doc.venues)||doc.venues.length!==24||
         !Array.isArray(doc.races)||!doc.collected_at_utc)
        throw new Error("監視JSONの形式が一致しません");
      state.doc=doc;state.error=null;
      if(manual)setToast("保存された最新の監視記録を読み込みました");
    }catch(err){
      state.error=String(err?.message||err);
      // Keep only a previous real snapshot, and display an explicit error.
      if(manual)setToast("データ更新に失敗しました");
    }finally{
      try{
        const response=await root.fetch(REGIONAL_URL+"?ts="+Date.now(),{cache:"no-store"});
        if(!response.ok)throw new Error("JMA model HTTP "+response.status);
        const regional=await response.json();
        if(regional?.schema!==REGIONAL_SCHEMA||!Array.isArray(regional.venues)||regional.venues.length!==24)
          throw new Error("広域予報JSONの形式が一致しません");
        state.regional=regional;state.regionalError=null;
      }catch(err){
        state.regionalError=String(err?.message||err);
      }
      try{
        const response=await root.fetch(TIDE_URL+"?ts="+Date.now(),{cache:"no-store"});
        if(!response.ok)throw new Error("潮位HTTP "+response.status);
        const tide=await response.json();
        if(tide?.schema!==TIDE_SCHEMA||!Array.isArray(tide.stations))throw new Error("潮位形式不正");
        state.tide=tide;state.tideError=null;
      }catch(err){state.tideError=String(err?.message||err);}
      state.loading=false;$("refresh").disabled=false;render();
    }
  }
  $("refresh").addEventListener("click",()=>reload(true));
  $("venue-search").addEventListener("input",e=>{state.search=e.target.value.trim();render();});
  $("filters").addEventListener("click",e=>{
    const button=e.target.closest("button[data-filter]");if(!button)return;
    state.filter=button.dataset.filter;
    for(const b of $("filters").querySelectorAll("button")){
      b.classList.toggle("active",b===button);b.setAttribute("aria-pressed",String(b===button));
    }
    render();
  });
  $("venues").addEventListener("click",e=>{
    const card=e.target.closest("button[data-venue]");if(!card)return;
    state.selected=card.dataset.venue;render();$("detail").scrollIntoView({behavior:"smooth",block:"start"});
  });
  D.addEventListener("visibilitychange",()=>{if(!D.hidden)reload();});
  root.setInterval(()=>{if(!D.hidden)reload();},60_000);
  if("serviceWorker" in root.navigator)root.addEventListener("load",()=>{
    root.navigator.serviceWorker.register("./service-worker.js?v=3",{scope:"./",updateViaCache:"none"}).then(reg=>reg.update()).catch(()=>{});
  });
  reload();
})(typeof window!=="undefined"?window:globalThis);
