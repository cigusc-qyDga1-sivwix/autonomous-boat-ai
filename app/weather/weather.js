/* WEATHER LAB standalone PWA. Data read-only from the dedicated weather-lab-data branch. */
(function(root){
  "use strict";
  const DATA_URL="https://raw.githubusercontent.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/weather-lab-data/weather_lab/data/latest.json";
  const SCHEMA="weather_lab.water_surface_monitor.v1";
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
    if(num(row.weather?.wind_mps)===null||num(row.weather?.wave_cm)===null)return "incomplete";
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
    const wind=row?UNIT_VALUE(row.weather?.wind_mps,""):"—";
    const wave=row?UNIT_VALUE(row.weather?.wave_cm,""):"—";
    const note=row?"最新："+row.race+"R・観測 "+shortTime(row.weather_observed_at_jst):
      q==="failed"?"取得元への接続を確認":"対象日の記録なし";
    return '<button type="button" class="venue-card is-'+esc(q)+(selected===v.code?' selected':'')+'" data-venue="'+esc(v.code)+'" aria-pressed="'+String(selected===v.code)+'">'+
      '<span class="card-head"><span><span class="venue-id">VENUE '+esc(v.code)+'</span><h3>'+esc(v.name)+'</h3></span>'+
      '<span class="status-chip '+esc(chip[1])+'">'+esc(chip[0])+'</span></span>'+
      '<span class="venue-metrics"><span class="venue-metric"><small>風速</small><strong>'+esc(wind)+'<span>m/s</span></strong></span>'+
      '<span class="venue-metric"><small>波高</small><strong>'+esc(wave)+'<span>cm</span></strong></span></span>'+
      '<span class="card-foot"><span>'+esc(note)+'</span><strong>'+item.rows.length+'R</strong></span>'+
      (v.code==="03"?'<span class="scope-note">BOAT LABの予想対象外</span>':'')+
      '</button>';
  }
  function renderRace(row,now){
    const q=quality(row,now),chip=displayLabel(q);
    const sourceAge=ageMinutes(row.source_captured_at_jst,now),obsAge=ageMinutes(row.weather_observed_at_jst,now);
    const flags=[
      q==="fresh"?'<span class="flag good">暫定鮮度基準内</span>':'<span class="flag">古い記録は現在の状況を示しません</span>',
      row.weather?.wind_direction_status==="calm_undefined"?'<span class="flag">無風：風向未設定</span>':'',
      row.weather?.wind_direction_status==="missing_noncalm"?'<span class="flag">風向コード欠損</span>':'',
    ].join("");
    return '<article class="race-card"><div class="race-row"><strong>'+esc(row.race)+'R</strong>'+
      '<span class="status-chip '+esc(chip[1])+'">'+esc(chip[0])+'</span><small>締切 '+esc(row.cutoff_jst||"不明")+'</small></div>'+
      '<div class="race-readings"><div class="race-reading"><span>風速</span><strong>'+esc(UNIT_VALUE(row.weather?.wind_mps,""))+'<em>m/s</em></strong></div>'+
      '<div class="race-reading"><span>波高</span><strong>'+esc(UNIT_VALUE(row.weather?.wave_cm,""))+'<em>cm</em></strong></div>'+
      '<div class="race-reading"><span>風向コード</span><strong>'+esc(num(row.weather?.wind_direction_raw_code)??"—")+'</strong></div></div>'+
      '<div class="flags">'+flags+'</div>'+
      '<div class="race-time">気象観測：'+esc(shortTime(row.weather_observed_at_jst))+
      (obsAge!==null?'（'+esc(obsAge)+'分前）':'')+
      '<br>元データ取得：'+esc(shortTime(row.source_captured_at_jst))+
      (sourceAge!==null?'（'+esc(sourceAge)+'分前）':'')+
      '<br>気温：'+esc(UNIT_VALUE(row.weather?.air_c,"℃"))+
      '／水温：'+esc(UNIT_VALUE(row.weather?.water_c,"℃"))+'</div></article>';
  }
  function renderDetail(item,doc,now){
    if(!item)return '<div class="detail-empty"><span aria-hidden="true">↗</span><h2>レース場を選択</h2><p>場をタップすると、1〜12Rの風・波・観測時刻を確認できます。</p></div>';
    const v=item.venue,rows=[...item.rows].sort((a,b)=>Number(b.race)-Number(a.race));
    const count='<b>'+rows.length+'R</b>';
    const notes= v.code==="03"?"江戸川は収集監査のみ。BOAT LABの正式予想対象外。":"WEATHER LABは監視専用。正式予想に自動適用しません。";
    return '<div class="detail-heading"><div><span class="section-kicker">RACE DETAILS ・ VENUE '+esc(v.code)+'</span><h2>'+esc(v.name)+' の気象記録</h2>'+
      '<p class="detail-meta">'+esc(doc.event_date)+' の記録 '+count+' ／ '+esc(notes)+
      '<br>潮位・潮流：<b>未取得</b>（ゼロではありません）</p></div><span class="status-chip '+esc(displayLabel(item.quality)[1])+'">'+esc(displayLabel(item.quality)[0])+'</span></div>'+
      (rows.length?'<div class="detail-list">'+rows.map(r=>renderRace(r,now)).join("")+'</div>':
        '<div class="no-results">この日のレース別気象記録はありません。未開催・公開前・提供元欠損は区別して監査中です。</div>');
  }
  const api={quality,ageMinutes,dayJST,summary,venueView,latestRow,renderVenueCard,renderRace,renderDetail,esc};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(!root.document)return;

  const D=root.document;
  const $=id=>D.getElementById(id);
  const state={doc:null,filter:"all",search:"",selected:null,loading:false,error:null};
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
    $("stat-venue-note").textContent=stats?stats.day+"の記録":"本日の記録";
    const when=doc?.collected_at_utc?japaneseDate(new Date(doc.collected_at_utc)):"未取得";
    $("updated-label").textContent="最終取得： "+when+" JST";
    const alert=$("data-alert"),health=$("source-health");
    alert.className="alert";health.className="hero-tag";
    if(state.error||!doc||stats?.source_ok===false){
      alert.classList.add("is-error");health.classList.add("is-error");
      health.textContent="取得元・通信エラー";
      alert.textContent="データを取得できませんでした。数字を推測で補いません。「更新」で再取得できます。";
    }else if(stats.age===null||stats.age>15||stats.fresh===0){
      alert.classList.add("is-warn");health.classList.add("is-stale");
      health.textContent="過去の観測データ";
      alert.textContent="最新保存から "+(stats.age===null?"時刻不明":stats.age+"分")+"。現在も新鮮な観測は"+
        stats.fresh+"件です。古いレース別記録を現在の風・波として使用しないでください。";
    }else{
      health.textContent="観測データを取得";
      alert.textContent="鮮度基準内の気象記録が "+stats.fresh+"件あります。ただしレース別のスナップショットであり、連続実況ではありません。";
    }
    const items=doc?doc.venues.map(v=>venueView(v,doc,now)):VENUES.map((name,i)=>
      venueView({name,code:String(i+1).padStart(2,"0"),race_snapshots:0},{provider:{fetch_status:state.error?"unavailable":"ok"},races:[]},now));
    const filtered=items.filter(it=>{
      const q=it.quality;
      if(state.filter==="available"&&!it.rows.length)return false;
      if(state.filter==="fresh"&&q!=="fresh")return false;
      if(state.filter==="stale"&&!["stale","incomplete","unknown"].includes(q))return false;
      if(state.filter==="missing"&&!["missing","failed"].includes(q))return false;
      return !state.search||it.venue.name.includes(state.search)||it.venue.code.includes(state.search);
    });
    $("venues").innerHTML=filtered.length?filtered.map(v=>renderVenueCard(v,state.selected)).join(""):
      '<div class="no-results">該当するレース場はありません。絞り込みを変更してください。</div>';
    $("detail").innerHTML=renderDetail(items.find(it=>it.venue.code===state.selected)||null,doc||{event_date:"—"},now);
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
    root.navigator.serviceWorker.register("./service-worker.js",{scope:"./"}).catch(()=>{});
  });
  reload();
})(typeof window!=="undefined"?window:globalThis);
