/* BOAT LAB chronological race timeline: read-only, never invents a race/result. */
(function(root){
 'use strict';
 const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const time=t=>/^([01]\d|2[0-3]):[0-5]\d$/.test(String(t||''))?t:null;
 const minutes=t=>Number(t.slice(0,2))*60+Number(t.slice(3));
 const dateJst=(d)=>{const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d);const part=k=>parts.find(p=>p.type===k)?.value||'';return part('year')+'-'+part('month')+'-'+part('day')};
 const nowJst=(d)=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
 let filter='all';
 const validFilters=['all','exhibition','entry'];
 function setFilter(next){filter=validFilters.includes(next)?next:'all';return filter;}
 function getFilter(){return filter;}
 function needsExhibition(r){return r.entry_exhibition_gate?.final_eligible!==true;}
 function entryWatch(r){return r.entry_exhibition_gate?.entry_watch===true;}
 function rows(data){
  const map=new Map();
  for(const r of (data.unforecast_races||[]).concat(data.forecast_races||[])){
   if(!r||typeof r.venue!=='string'||!Number.isInteger(r.race)||r.race<1||r.race>12||!time(r.cutoff_jst))continue;
   const key=r.venue+'|'+r.race;
   const prior=map.get(key);
   if(!prior||(!prior.bets&&r.bets))map.set(key,r);
  }
  return [...map.values()].sort((a,b)=>minutes(a.cutoff_jst)-minutes(b.cutoff_jst)||a.venue.localeCompare(b.venue,'ja')||a.race-b.race);
 }
 function official(data,r){
  const key=data.event_date+'|'+r.venue+'|'+r.race;
  const o=data.official_results?.[key];
  if(data.settlement_alerts?.[key]||!o||o.verified!==true||o.source!=='boatrace_official_pay')return false;
  if(r.sha256&&o.snapshot_sha256&&r.sha256!==o.snapshot_sha256)return false;
  return true;
 }
 function render(data,now=new Date()){
  if(!data)return '';
  const all=rows(data),today=dateJst(now),fresh=data.event_date===today,nowMinutes=minutes(nowJst(now));
  const future=fresh?all.filter(r=>minutes(r.cutoff_jst)>nowMinutes):[];
  const shown=filter==='entry'?future.filter(entryWatch):filter==='exhibition'?future.filter(needsExhibition):future;
  const upcoming=shown.slice(0,7);
  const past=fresh?all.filter(r=>minutes(r.cutoff_jst)<=nowMinutes).reverse().slice(0,5):[];
  const old=!fresh;
  const filterButtons=[['all','すべて',future.length],['exhibition','展示要確認',future.filter(needsExhibition).length],['entry','前付け警戒',future.filter(entryWatch).length]];
  const filterHTML='<div class="timeline-filters" role="group" aria-label="直近レースの絞り込み">'+filterButtons.map(([key,label,count])=>'<button type="button" data-timeline-filter="'+key+'" aria-pressed="'+(filter===key)+'">'+esc(label)+' <span>'+count+'</span></button>').join('')+'</div>';
  const updated=data.updated_at_utc?new Date(data.updated_at_utc):null;
  const updatedLabel=updated&&!Number.isNaN(updated.getTime())?updated.toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'取得時刻不明';
  const line=(r,up,first)=>{
   const verified=official(data,r);
   const gate=r.entry_exhibition_gate;
   const hasForecast=Array.isArray(r.bets)&&r.bets.length>0;
   const delta=minutes(r.cutoff_jst)-nowMinutes;
   const phase=verified?'公式結果確認済':up?(gate?.final_eligible?'展示確認済':gate?.entry_watch?'前付け・展示待ち':r.phase==='exhibition'?'展示反映':'展示未確認'):'締切経過・結果待ち';
   const urgent=up&&delta<=10;
   const label=up&&first?'次の締切 · '+phase:phase;
   const detail=up?(first?'あと'+delta+'分':'締切まで'+delta+'分'):verified?'公式結果照合可':'公式結果は未確認';
   const main=hasForecast?
     '<button type="button" data-race="'+esc(r.venue)+'|'+r.race+'" class="timeline-action">AI予想</button>':
     '<span class="timeline-disabled">予想未固定</span>';
   const result=hasForecast&&!up?'<button type="button" data-result-next="'+esc(r.venue)+'|'+r.race+'" class="timeline-action">'+(verified?'結果照合':'結果を確認')+'</button>':
     '<span class="timeline-disabled">'+(up?'結果待ち':hasForecast?'結果未確認':'結果・予想未取得')+'</span>';
   return '<article class="timeline-race'+(up&&first?' timeline-next':'')+(urgent?' timeline-urgent':'')+'"><div class="timeline-clock"><strong>'+esc(r.cutoff_jst)+'</strong><small>'+esc(detail)+'</small></div>'+
    '<div class="timeline-race-main"><strong>'+esc(r.venue)+' <span>'+r.race+'R</span></strong><span class="timeline-status">'+esc(label)+'</span>'+
    '<small>'+(gate?.entry_watch?'⚠ 前付け警戒 · ':'')+(gate?.final_eligible?'展示進入確認済':hasForecast?r.phase==='exhibition'?'展示反映・進入確定未確認':'展示前固定・最終判断保留':'展示・予想未確認')+'</small></div>'+
    '<div class="timeline-actions">'+main+result+'</div></article>';
  };
  return '<section class="race-timeline" aria-label="全国24場 締切時刻順のレース">'+
   '<div class="timeline-heading"><div><h2>🕒 直近のレース</h2><p>全国の取得済みレースを締切予定順に表示 · 現在 '+esc(nowJst(now))+' JST</p></div><button type="button" data-view="races" class="timeline-all">全レース →</button></div>'+
   (old?'<div class="notice warn">表示データは'+esc(data.event_date)+'の記録です。今日の直近レースとしては表示しません。</div>':
    filterHTML+'<div class="timeline-group">'+(upcoming.length?upcoming.map((r,i)=>line(r,true,i===0)).join(''):'<p class="timeline-empty">'+(filter==='entry'?'前付け警戒のレースはありません。':filter==='exhibition'?'展示要確認のレースはありません。':'今後の締切予定を確認できるレースはありません。')+'</p>')+'</div>'+
    '<h3>最近締切を迎えたレース</h3><div class="timeline-group">'+(past.length?past.map(r=>line(r,false,false)).join(''):'<p class="timeline-empty">該当レースはありません。</p>')+'</div>')+
   '<p class="timeline-note">最終データ更新 '+esc(updatedLabel)+' JST。時刻は締切予定（発走時刻ではありません）。残り時間は端末時刻による目安です。表示時刻は毎分更新しますが、最新展示・結果の取得を保証しません。締切経過は結果確定を意味しません。実投票・通知は行いません。</p></section>';
 }
 root.BoatRaceTimeline={rows,official,render,setFilter,getFilter,needsExhibition,entryWatch};
})(typeof window==='undefined'?globalThis:window);
