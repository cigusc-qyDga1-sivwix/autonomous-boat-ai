/* Read-only historical observations. NEVER mutates the frozen forecast ledger. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fixed = v => v===null||v===undefined ? '—' : Number(v).toFixed(2);
  let payload = null;
  let reading = false;
  const parts = Intl.DateTimeFormat('en-US',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const jst = Object.fromEntries(parts.map(p=>[p.type,p.value]));
  const today = [jst.year,jst.month,jst.day].join('-');
  const requested = new URLSearchParams(location.search).get('date');
  el('date').value = /^\d{4}-\d{2}-\d{2}$/.test(requested||'') ? requested : today;
  function summaryMetric(label,value) {
    return '<div class="stat"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>';
  }
  function display() {
    if (!payload) return;
    const mode = el('mode').value, venue = el('venue').value;
    const rows = payload.records.filter(r => (!venue || venue===r.venue) &&
      (mode==='all' || (mode==='finished' ? !!(r.result||r.payout) : !(r.result||r.payout))));
    el('summary').innerHTML = [
      summaryMetric('展示取得',rows.length+'R'),
      summaryMetric('展示艇数',(rows.length*6)+'艇'),
      summaryMetric('着順データ',rows.filter(r=>r.result).length+'R'),
      summaryMetric('払戻データ',rows.filter(r=>r.payout).length+'R'),
      summaryMetric('開催場',new Set(rows.map(r=>r.venue)).size+'場')
    ].join('');
    el('races').innerHTML = rows.map((r,i) => {
      const times = r.boats.map(b=>b.exhibition_time).filter(Number.isFinite);
      const fastest = times.length ? Math.min(...times) : null;
      const leader = r.boats.filter(b=>fastest!==null && b.exhibition_time===fastest).map(b=>b.lane).join('・');
      const weather = r.weather.wind_mps===null ? '—' : r.weather.wind_mps+'m/s / 波'+(r.weather.wave_cm??'—')+'cm';
      const finish = r.result?.finish || r.payout?.finish || '未取得';
      return '<tr><td>'+esc(r.venue)+' '+r.race+'R</td><td>'+esc(r.cutoff_jst)+
        '</td><td>'+esc((r.source_observed_jst||'').slice(11,19))+'</td><td>'+esc(leader)+'号艇 ('+fixed(fastest)+
        ')</td><td>'+esc(weather)+'</td><td>'+esc(finish)+'</td><td><a href="#race-'+i+'">詳細 ↓</a></td></tr>';
    }).join('');
    el('details').innerHTML = rows.map((r,i) => {
      const body = r.boats.map(b => '<tr><td>'+esc(b.lane)+'</td><td>'+esc(b.name||'—')+
        '</td><td>'+esc(b.course)+'</td><td class="'+(b.exhibition_f?'negative':'')+'">'+fixed(b.exhibition_st)+
        (b.exhibition_f?' (展示F)':'')+'</td><td>'+fixed(b.exhibition_time)+'</td><td>'+fixed(b.tilt)+
        '</td><td>'+esc((b.original_exhibition||[]).map(v=>v.metric+': '+v.value).join(' / '))+'</td></tr>').join('');
      return '<details id="race-'+i+'"><summary>'+esc(r.venue)+' '+r.race+'R｜結果: '+
        esc(r.result?.finish||r.payout?.finish||'未取得')+' '+esc(r.result?.decision||'')+
        '</summary><div class="tablewrap"><table><thead><tr><th>艇</th><th>選手</th><th>進入</th><th>展示ST</th>'+
        '<th>展示タイム</th><th>チルト</th><th>場別オリジナル展示</th></tr></thead><tbody>'+body+
        '</tbody></table></div><p class="sub">観測: '+esc(r.source_observed_jst)+
        '。研究用記録で、事前予想とは別です。</p></details>';
    }).join('');
  }
  async function load() {
    const date = el('date').value;
    if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(date)||reading)return;
    reading=true;
    if(!payload)el('status').textContent = '公開データを読み込み中…';
    try {
      const res = await fetch('./data/exhibition/'+date+'.json?ts='+Date.now(),{cache:'no-store'});
      if (!res.ok) throw Error('HTTP '+res.status+'（未保存日付の可能性）');
      const value = await res.json();
      if (value.schema!=='boatlabs.exhibition_research.v1'||value.event_date!==date||
          !Array.isArray(value.records)) throw Error('データ形式不正');
      if(el('date').value!==date)return; // Never paint a previous date's response.
      payload = value;
      const selected = el('venue').value;
      el('venue').innerHTML = '<option value="">全場</option>'+Array.from(new Set(value.records.map(r=>r.venue)))
        .sort().map(name=>'<option value="'+esc(name)+'">'+esc(name)+'</option>').join('');
      el('venue').value = selected;
      const recorded = value.created_at_utc ?
        new Date(value.created_at_utc).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}) : '不明';
      const newest = value.records.reduce((a,r)=>r.source_observed_jst>a?r.source_observed_jst:a,'');
      el('status').textContent = date+'｜展示 '+value.coverage.race_count+
        'R｜研究データ保存 '+recorded+' JST｜最新観測 '+(newest?newest.slice(11,19):'不明')+
        ' JST｜画面確認 '+new Date().toLocaleTimeString('ja-JP');
      display();
    } catch(err) {
      if(el('date').value!==date)return;
      el('status').textContent = '⚠ 更新確認に失敗：'+err.message+
        (payload?'（以前の記録を表示中。最新情報ではありません）':'');
      if(!payload){
        el('summary').innerHTML = '';el('races').innerHTML='';el('details').innerHTML='';
      }
    } finally {
      reading=false;
    }
  }
  el('date').addEventListener('change',load);
  el('reload').addEventListener('click',load);
  el('venue').addEventListener('change',display);
  el('mode').addEventListener('change',display);
  // The research page previously refreshed ONLY on click. Poll while open,
  // and do not backfill formal predictions from these retrospective records.
  setInterval(()=>{if(!document.hidden&&el('date').value===today)void load();},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&el('date').value===today)void load();});
  load();
})();
