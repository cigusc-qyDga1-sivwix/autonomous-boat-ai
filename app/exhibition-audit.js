/* Displays previously collected six-boat exhibition records for research only.
 * NEVER feeds retrospective data to the prediction engine. */
(function(global){
'use strict';
const names=['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
const esc=x=>String(x??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const state={day:'',map:new Map(),collected:'',error:'',loading:false};
function key(r){const idx=names.indexOf(r.venue);return state.day.replaceAll('-','')+String(idx+1).padStart(2,'0')+String(r.race).padStart(2,'0');}
async function load(day){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return;
 state.day=day;state.loading=true;
 try{
 const res=await fetch('./data/exhibition/'+day+'.json?v='+Date.now(),{cache:'no-store'});
 if(!res.ok)throw Error('展示記録 HTTP '+res.status);
 const j=await res.json();
 if(j.event_date!==day||j.schema!=='boatlabs.exhibition_research.v1')throw Error('展示記録の日付が不一致');
 const map=new Map();
 for(const r of j.records||[]){
  if(r.race_code&&Array.isArray(r.boats)&&r.boats.length===6)
   map.set(r.race_code,{observed:r.source_observed_jst,boats:r.boats.map(b=>({
    lane:b.lane,course:b.course,st:b.exhibition_st,time:b.exhibition_time,
    metrics:(b.original_exhibition||[]).map(v=>v.metric+': '+v.value).join(' / ')
   }))});
 }
 if(state.day===day){state.map=map;state.collected=j.created_at_utc;state.error='';}
 }catch(e){if(state.day===day){state.error=e.message;state.map=new Map();}}
 state.loading=false;
}
function age(value){const t=new Date(value).getTime();return Number.isFinite(t)?Math.max(0,Math.round((Date.now()-t)/60000)):null;}
function banner(data){
 if(data?.mode!=='auto-live')return '';
 const fore=(data.forecast_races||[]),used=fore.filter(x=>x.phase==='exhibition').length;
 const a=age(data.updated_at_utc),b=age(state.collected),stale=a===null||a>20||b===null||b>20;
 return '<div class="exhibit-health '+(stale?'stale':'ready')+'" role="status"><strong>📡 展示の取得状況</strong>　'+
  '発走前反映 '+used+'/'+fore.length+'R ／ 展示研究記録 '+state.map.size+'R ／ '+ 
  '予想更新 '+(a===null?'不明':a+'分前')+' ／ 展示更新 '+(b===null?'不明':b+'分前')+
  (stale?' ／ ⚠ 更新遅延あり':'')+(state.error?' ／ '+esc(state.error):'')+
  '<p>研究記録と発走前に反映済みの展示は別です。'+
  '<a href="./exhibition.html">展示の研究記録を見る ↗</a></p></div>';
}
function panel(r){
 if(!state.day||!r)return '';
 const x=state.map.get(key(r));
 if(!x)return '<div class="notice warn">📋 6艇の展示は研究記録にまだありません。締切後には固定買い目を書き換えません。</div>';
 const rows=x.boats.map(b=>'<tr><td>'+esc(b.lane)+'</td><td>'+esc(b.course)+'</td><td>'+esc(b.st)+
 '</td><td>'+esc(b.time)+'</td><td>'+esc(b.metrics||'—')+'</td></tr>').join('');
 return '<section class="card card-pad bottom-margin"><h3>📋 取得済み展示（研究記録）</h3>'+
  '<p><strong>'+(r.phase==='exhibition'?'発走前展示版を固定済み':'固定予想には未反映')+'</strong>'+
  ' ／ 元の展示観測：'+esc(x.observed||'不明')+'</p>'+
  '<div class="tablewrap"><table class="bets-table"><thead><tr><th>艇</th><th>進入</th><th>展示ST</th>'+
  '<th>展示タイム</th><th>一周・回り足・直線</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
  '<p class="muted text-sm">記録の観測時刻は、サーバーへの保存が締切前だった証拠ではありません。結果・払戻は予想に利用しません。</p></section>';
}
global.BoatExhibitionAudit={load,banner,panel,status:()=>({count:state.map.size,collected:state.collected,error:state.error})};
})(typeof window!=='undefined'?window:globalThis);
