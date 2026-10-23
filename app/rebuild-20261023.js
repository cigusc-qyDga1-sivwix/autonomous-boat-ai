(()=>{'use strict';
const qs=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const yen=n=>Number(n).toLocaleString('ja-JP')+'円';
const venueSelect=qs('#audit-venue-filter'),statusSelect=qs('#audit-status-filter'),search=qs('#audit-search');
let doc=null;
function render(){
 if(!doc)return;
 const filterV=venueSelect.value,filterS=statusSelect.value,term=search.value.trim().toLowerCase();
 const filtered=doc.races.filter(r=>(!filterV||r.venue===filterV)&&
 (!filterS||(filterS==='changed'?r.new_vs_original.changed:r.status_at_rebuild===filterS))&&
 (!term||[r.venue,r.race+'R',r.forecast_top,...r.racers.map(x=>x.name)].join(' ').toLowerCase().includes(term)));
 const grouped=new Map();
 filtered.forEach(r=>{if(!grouped.has(r.venue))grouped.set(r.venue,[]);grouped.get(r.venue).push(r)});
 const output=[];
 const venueOrder=doc.races.map(r=>r.venue).filter((x,i,arr)=>arr.indexOf(x)===i);
 for(const venue of venueOrder){
   const group=grouped.get(venue);if(!group)continue;
   group.sort((a,b)=>a.race-b.race);
   output.push('<section><div class="audit-venue"><h2>'+esc(venue)+' <small>'+group.length+'R</small></h2><span>試験・水面補正</span></div><div class="audit-grid">');
   for(const r of group){
     const wasPre=r.status_at_rebuild==='pre_cutoff_research';
     const nowPast=Date.now()>=new Date(doc.date+'T'+r.cutoff_jst+':00+09:00').getTime();
     const status=wasPre?'作成時は締切前':'事後再評価';
     const whenNow=nowPast?'現在は締切済み':'現在も締切前';
     const msg=wasPre?'別版の仮想再予想。元の発走前固定買い目とは別。':'締切後の再計算。的中予想として集計しない。';
     const old=r.original_top;
     const changed=r.new_vs_original.changed;
     output.push('<details class="audit-race"><summary><div class="top"><h3>'+r.race+'R</h3><span class="cutoff">締切 '+esc(r.cutoff_jst)+'</span></div>'+
       '<p><span class="status '+(nowPast?'expired':'')+'">'+status+'／'+whenNow+'</span>　'+(changed?'<span class="change">旧版と変更</span>':'旧版と同じ')+'</p>'+
       '<div class="primary"><strong>'+esc(r.forecast_top)+'</strong><span>'+r.forecast_point_count+'点 · 仮想50,000円</span></div>'+
       '<p>旧版トップ：'+esc(old)+'　→　再評価：'+esc(r.forecast_top)+'</p>'+
       '<p class="muted">▶ 押すと全買い目・展開仮説を表示</p></summary><div class="detail">'+
       '<p class="callout"><b>先頭候補の攻め：</b>'+esc(r.head_scenario_hypothesis)+'。水面補正 ×'+
          esc(r.venue_relative_course1_multiplier)+'。戦法は説明用仮説。</p>'+
       '<table aria-label="買い目と仮想配分"><thead><tr><td>3連単</td><td>仮想配分</td></tr></thead><tbody>'+
          r.bets.map(b=>'<tr><td><b>'+esc(b.combination)+'</b></td><td>'+yen(b.virtual_yen)+'</td></tr>').join('')+
       '</tbody></table><p class="muted">'+msg+'</p>'+
       '<p class="muted">出走者：'+r.racers.map(x=>esc(x.lane+' '+x.name)).join(' ／ ')+'</p>'+
       '<p class="muted">資料の時点：'+esc(r.input_evidence)+'　|　元予想ハッシュ：'+esc((r.original_fixed_sha256||'').slice(0,12))+'…</p></div></details>');
   }
   output.push('</div></section>');
 }
 qs('#audit-results').innerHTML=output.join('');
 qs('#audit-empty').hidden=filtered.length>0;
 qs('#audit-meta').textContent='表示 '+filtered.length+'／'+doc.summary.races+'R ・ 作成時刻 '+new Date(doc.generated_at_utc).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'})+' JST ・ 現在の締切状態は端末時刻により更新';
}
fetch('./data/research/2026-10-23-venue-rebuilt.json',{cache:'no-store'})
 .then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
 .then(data=>{
   if(data.schema!=='boatlabs.today_full_research_rebuild.v1'||data.races.length!==168)throw Error('日付・件数の検証に失敗しました');
   doc=data;
   const order=[...new Set(data.races.map(x=>x.venue))];
   venueSelect.innerHTML='<option value="">すべての開催場</option>'+
      order.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');
   qs('#audit-stats').innerHTML='<div><strong>'+doc.summary.races+'</strong>再評価R</div><div><strong>'+
     doc.summary.venues+'</strong>開催場</div><div><strong>'+doc.summary.changed_vs_original+
     '</strong>旧版と変更</div><div><strong>'+doc.summary.before_cutoff_research+'</strong>作成時締切前</div>';
   [venueSelect,statusSelect].forEach(x=>x.addEventListener('change',render));
   search.addEventListener('input',render);render();
 })
 .catch(e=>{qs('#audit-meta').textContent='研究データが読み込めません：'+e.message;});
})();