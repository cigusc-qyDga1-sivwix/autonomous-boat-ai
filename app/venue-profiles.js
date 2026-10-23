(() => {
'use strict';
const q=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cards=q('#venue-grid'),count=q('#venue-count'),input=q('#venue-filter');
let rows=[];
function render(){
  const term=input.value.trim().toLocaleLowerCase('ja-JP');
  const filtered=rows.filter(r=>[r.name,r.water_type,r.layout_focus,r.tactical_focus,r.wind_exposure,r.code].join(' ').toLocaleLowerCase('ja-JP').includes(term));
  count.textContent=filtered.length+'場を表示中';
  cards.innerHTML=filtered.map(r=>{
    const label=r.course1_reference_rate==null?'未取得':(r.course1_reference_rate*100).toFixed(1)+'%';
    return '<section class="venue-card" aria-label="'+esc(r.name)+'">'+
      '<div class="venue-code">BOAT RACE '+esc(r.code)+'</div>'+
      '<h2>'+esc(r.name)+'</h2><div class="venue-meta">'+
      '<span>'+esc(r.water_type)+'</span><span>風の注意：'+esc(r.wind_exposure)+'</span>'+
      '<span>潮・流れ：'+(r.tide_sensitive?'データ取得待ち':'補正対象外')+'</span></div>'+
      '<p class="headrate">過去の1コース1着率（参考）：'+label+'</p>'+
      '<p><b>水面・レイアウト：</b>'+esc(r.layout_focus)+'</p>'+
      '<p><b>展開で注目：</b>'+esc(r.tactical_focus)+'</p>'+
      (r.pit_layout_changed?'<p>ピット位置変更：'+esc(r.pit_layout_changed)+'。ピット離れ・実進入を優先</p>':'')+
      '<p><small>※ 未校正の会場別補正。過去率をそのまま的中確率にはしません。</small></p>'+
      '<a href="'+esc(r.reference_url)+'" target="_blank" rel="noopener noreferrer">参考資料 ↗</a>'+
    '</section>';
  }).join('')||'<p>該当する会場がありません。</p>';
}
input.addEventListener('input',render);
fetch('./data/venue-profiles.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
  .then(doc=>{
    if(doc.schema!=='boatlabs.venue_profiles.v1'||doc.profiles?.length!==24)throw Error('会場データの形式が不正');
    rows=doc.profiles;render();
  })
  .catch(e=>{count.textContent='会場データを読み込めません：'+String(e.message);});
})();
