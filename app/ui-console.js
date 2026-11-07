/* BOAT LAB Race Desk — read-only, pre-race-first display.
 * Never computes, overwrites, promotes or replays predictions.
 * A green "formal" status requires the same immutable snapshot policy
 * as the ticket panel; research-only exhibition is NOT formal evidence.
 */
(function(root) {
  'use strict';
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const jstDay=date=>new Intl.DateTimeFormat('sv-SE',{
    timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'
  }).format(date);
  const jstClock=date=>new Intl.DateTimeFormat('ja-JP',{
    timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit',hour12:false
  }).format(date);
  const validTime=t=>typeof t==='string'&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(t);
  const validDay=t=>typeof t==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(t);
  const percent=(a,b)=>b>0?Math.min(100,Math.max(0,Math.round(100*a/b))):0;

  function summarize(data,now=new Date(),policy=root.BoatTicketPolicy) {
    const list=Array.isArray(data?.forecast_races)?data.forecast_races:[];
    const day=validDay(data?.event_date)?data.event_date:'';
    const live=data?.mode==='auto-live';
    const today=validDay(jstDay(now))?jstDay(now):'';
    const current=day===today;
    // Fail closed on missing ticket-policy code, even if phase says exhibition.
    // The existing formal policy owns classification; explicit pre-cutoff
    // failure flags may narrow the visual count but never expand it.
    const formal=list.filter(r=>
      r?.entry_exhibition_gate?.final_eligible!==false&&
      r?.exhibition_input_check?.verified_before_freeze!==false&&
      policy?.classify?.(r,day)?.formal===true);
    const eligible=new Set(formal.map(r=>r.venue+'|'+r.race));
    const frozenExhibition=list.filter(r=>r.phase==='exhibition').length;
    const reviews=data?.settlement_alerts||{};
    const verified=list.filter(r=>{
      const key=day+'|'+r.venue+'|'+r.race;
      const x=data?.official_results?.[key];
      return x&&x.source==='boatrace_official_pay'&&x.verified===true&&
        !reviews[key]&&(!x.snapshot_sha256||x.snapshot_sha256===r.sha256);
    }).length;
    const upcoming=current?list.filter(r=>
      validTime(r.cutoff_jst)&&r.cutoff_jst>jstClock(now)&&
      typeof r.venue==='string'&&Number.isInteger(r.race)&&
      r.race>=1&&r.race<=12)
      .sort((a,b)=>a.cutoff_jst.localeCompare(b.cutoff_jst)||
        a.venue.localeCompare(b.venue,'ja')||a.race-b.race)
      .slice(0,2):[];
    const rawUpdated=Date.parse(data?.updated_at_utc||'');
    const ageMin=Number.isFinite(rawUpdated)?
      Math.max(0,Math.floor((now.getTime()-rawUpdated)/60000)):null;
    const freshness=(!live?'import':!current?'old':ageMin===null||ageMin>20?'delayed':'recent');
    return {
      day,live,current,eligible,formal:formal.length,forecast:list.length,
      frozenExhibition,verified,upcoming,freshness,ageMin,
      progress:percent(formal.length,list.length),
      updatedAt:Number.isFinite(rawUpdated)?jstClock(new Date(rawUpdated)):'不明',
    };
  }

  function render(data,now=new Date(),policy=root.BoatTicketPolicy) {
    if(!data||!Array.isArray(data.forecast_races))return '';
    const s=summarize(data,now,policy);
    const freshnessText={
      recent:'最新取得を確認',
      delayed:'更新遅延・要確認',
      old:'過去日の記録を表示中',
      import:'インポート資料を表示中'
    }[s.freshness];
    const label='BOAT LAB / RACE DESK';
    const next=s.upcoming.length?
      '<div class="bl-desk-next"><span class="bl-desk-next-label">次の締切予定</span>'+
      s.upcoming.map(r=>{
        const formal=s.eligible.has(r.venue+'|'+r.race);
        const status=r.classification==='SKIP'?'SKIP・研究用':
          formal?'展示反映':'正式未確定';
        return '<button type="button" class="bl-desk-next-race" data-race="'+escape(r.venue)+'|'+r.race+'" aria-label="'+
        escape(r.venue+' '+r.race+'R '+r.cutoff_jst+' '+status)+'">'+
        '<span class="bl-desk-time">'+escape(r.cutoff_jst)+'</span>'+
        '<span class="bl-desk-name">'+escape(r.venue)+' '+r.race+'R</span>'+
        '<span class="bl-desk-race-state '+(formal?'is-formal':'is-pending')+'">'+
        status+'</span></button>';
      }).join('')+'</div>':
      '<p class="bl-desk-next-empty">'+(s.current?'次の締切予定はありません':'当日の締切情報ではありません')+'</p>';
    return '<section class="bl-race-desk" aria-label="予想と展示の稼働ステータス">'+
      '<div class="bl-desk-topline"><div><span class="bl-desk-eyebrow">'+label+
      '</span><h2>今日のレースデスク <small>'+escape(s.day||'日付未確認')+'</small></h2></div>'+
      '<div class="bl-desk-fresh '+(s.freshness==='recent'?'is-current':'is-delayed')+'">'+
      '<span aria-hidden="true" class="bl-desk-indicator"></span>'+freshnessText+
      ' <span class="bl-desk-updated">'+escape(s.updatedAt)+' JST</span></div></div>'+
      '<div class="bl-desk-stat-grid">'+
      '<div class="bl-desk-stat bl-desk-stat-hero"><span>展示後の正式買い目</span>'+
      '<strong>'+s.formal+'<small> / '+s.forecast+' R</small></strong>'+
      '<div role="progressbar" aria-label="全予想のうち正式買い目として固定済み" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+s.progress+'" class="bl-desk-progress">'+
      '<span style="width:'+s.progress+'%"></span></div></div>'+
      '<div class="bl-desk-stat"><span>展示版の固定予想</span><strong>'+s.frozenExhibition+'<small> R</small></strong>'+
      '<em>正式認定とは別</em></div>'+
      '<div class="bl-desk-stat"><span>公式結果照合済み</span><strong>'+s.verified+'<small> R</small></strong>'+
      '<em>照合されたレースのみ</em></div></div>'+
      next+
      '<p class="bl-desk-safety">緑の「展示反映」は発走前の正式固定が確認できた場合のみ表示。研究用展示・オッズ未確認・SKIPは正式買い目に含めません。締切時刻は予定値です。</p>'+
      '</section>';
  }

  root.BoatLabUIConsole={summarize,render};
  if(typeof module==='object'&&module.exports)module.exports=root.BoatLabUIConsole;
})(typeof window==='undefined'?globalThis:window);
