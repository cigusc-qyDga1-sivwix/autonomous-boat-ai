/*
 * BOAT LAB 2.0 — independent, read-only UI.
 * Deliberately never imports forecast calculators, changes tickets, saves
 * outcome data, fabricates missing metrics, or promotes research to formal.
 */
(function(root){
'use strict';
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=value=>Number.isSafeInteger(value)?value.toLocaleString('ja-JP')+'円':'未確認';
const percent=value=>typeof value==='number'&&Number.isFinite(value)?(value*100).toFixed(1)+'%':'—';
const validDay=day=>typeof day==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(day);
const validClock=value=>typeof value==='string'&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value);
const jstDay=(date=new Date())=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
const jstStamp=value=>{
 if(!value)return '時刻未確認';
 const d=new Date(value);
 return Number.isFinite(d.getTime())?new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d)+' JST':'時刻未確認';
};
const cutoffMs=(day,clock)=>validDay(day)&&validClock(clock)?Date.parse(day+'T'+clock+':00+09:00'):NaN;
// A forecast remains visible for ten minutes AFTER its published cutoff.
// This controls display only: it cannot create or revise a frozen prediction.
const POST_CUTOFF_GRACE_MS=10*60000;
const recentCutoff=(r,day,now)=>{
 const cutoff=cutoffMs(day,r?.cutoff_jst);
 return Number.isFinite(cutoff)&&now>=cutoff&&now<=cutoff+POST_CUTOFF_GRACE_MS;
};
const visibleAroundCutoff=(r,day,now)=>{
 const cutoff=cutoffMs(day,r?.cutoff_jst);
 return Number.isFinite(cutoff)&&(cutoff>now||recentCutoff(r,day,now));
};
const sumBets=r=>(Array.isArray(r?.bets)?r.bets:[]).reduce((n,x)=>n+(Number.isSafeInteger(x.virtual_yen)&&x.virtual_yen>=0?x.virtual_yen:0),0);
const validRace=r=>r&&typeof r.venue==='string'&&r.venue.length<=50&&Number.isInteger(r.race)&&r.race>=1&&r.race<=12&&validClock(r.cutoff_jst)&&Array.isArray(r.bets)&&r.bets.length>0;
const validCombo=combo=>typeof combo==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(combo)&&new Set(combo.split('-')).size===3;
const frozenStatus=(r,data,policy)=>{
 if(!validRace(r)||data?.mode!=='auto-live'||!validDay(data.event_date))return false;
 if(r.classification==='SKIP'||r.phase!=='exhibition'||
    r.entry_exhibition_gate?.final_eligible!==true||
    r.exhibition_input_check?.verified_before_freeze!==true)return false;
 return policy?.classify?.(r,data.event_date)?.formal===true;
};
function raceOrder(a,b){return a.cutoff_jst.localeCompare(b.cutoff_jst)||a.venue.localeCompare(b.venue,'ja')||a.race-b.race}
const verifiedOfficial=(r,data)=>{
 if(!validRace(r)||data?.mode!=='auto-live'||!validDay(data.event_date))return null;
 const key=data.event_date+'|'+r.venue+'|'+r.race;
 if(data.settlement_alerts?.[key])return null;
 const v=data.official_results?.[key];
 if(!v||v.source!=='boatrace_official_pay'||v.verified!==true||!validCombo(v.finish))return null;
 if(v.snapshot_sha256&&v.snapshot_sha256!==r.sha256)return null;
 if(!Number.isSafeInteger(v.payout_per_100)||v.payout_per_100<100)return null;
 // Refunds, cancellations and complicated settlements need separate
 // adjudication. Never assert hit/miss or financial returns for them here.
 if(v.void_trifecta===true||Array.isArray(v.refunded_boats)&&v.refunded_boats.length>0)return null;
 return v;
};
const officialOutcome=(r,data)=>{
 const v=verifiedOfficial(r,data);
 if(!v)return null;
 const hit=r.bets.some(b=>b.combination===v.finish);
 return {finish:v.finish,hit,payoutPer100:v.payout_per_100,source:v.source};
};

/* Official dividend per 100 yen × immutable virtual ticket stake (display only). */
const virtualSettlement=(r,data)=>{
 const official=verifiedOfficial(r,data);
 if(!official||!Array.isArray(r?.bets)||r.bets.length===0)return null;
 let stake=0n,winningStake=0n;
 for(const bet of r.bets){
   if(!validCombo(bet?.combination)||!Number.isSafeInteger(bet?.virtual_yen)||
      bet.virtual_yen<0||bet.virtual_yen%100!==0)return null;
   const amount=BigInt(bet.virtual_yen);
   stake+=amount;
   if(bet.combination===official.finish)winningStake+=amount;
 }
 if(stake<=0n)return null;
 const payout=winningStake*BigInt(official.payout_per_100)/100n;
 const profit=payout-stake,max=BigInt(Number.MAX_SAFE_INTEGER);
 if(stake>max||payout>max||profit>max||profit< -max)return null;
 return {stakeYen:Number(stake),payoutYen:Number(payout),profitYen:Number(profit),officialPayoutPer100:official.payout_per_100};
};
const racePhase=(r,data,policy)=>frozenStatus(r,data,policy)?'formal':r.classification==='SKIP'?'shadow':'pending';
function normalize(payload){
 if(!payload||!validDay(payload.event_date)||payload.mode!=='auto-live'||!Array.isArray(payload.forecast_races)||payload.forecast_races.length>300)
   throw new Error('正式な自動予想データを確認できませんでした');
 const races=payload.forecast_races.filter(validRace);
 // Empty auto-live days are valid: show an honest 0R state, not a load failure.
 return {...payload,forecast_races:races};
}
const dailyMetrics=(audit,day,kind='formal')=>{
 if(!validDay(day)||!['formal','provisional'].includes(kind)||
    audit?.event_date!==day||
    audit?.source!=='verified BOATRACE official payouts + immutable pre-cutoff predictions')return null;
 const value=audit.by_ticket_status?.[kind];
 if(!value)return null;
 const integers=['verified_races','hits','virtual_stake_yen','virtual_payout_yen','virtual_profit_yen'];
 if(integers.some(k=>!Number.isSafeInteger(value[k]))||
    value.verified_races<0||value.hits<0||value.hits>value.verified_races||
    value.virtual_stake_yen<0||value.virtual_payout_yen<0||
    value.virtual_profit_yen!==value.virtual_payout_yen-value.virtual_stake_yen||
    (value.verified_races===0&&value.virtual_stake_yen!==0)||
    (value.verified_races>0&&value.virtual_stake_yen===0))return null;
 return {...value,return_rate:value.virtual_stake_yen>0?value.virtual_payout_yen/value.virtual_stake_yen:null};
};
const engine={dailyMetrics,money,percent,validDay,validClock,jstDay,jstStamp,cutoffMs,sumBets,validRace,validCombo,frozenStatus,verifiedOfficial,officialOutcome,virtualSettlement,racePhase,normalize,raceOrder,recentCutoff,visibleAroundCutoff,POST_CUTOFF_GRACE_MS};
root.BoatLabV2=engine;
if(typeof module==='object'&&module.exports)module.exports=engine;
if(typeof document==='undefined')return;

const $=id=>document.getElementById(id);
const state={tab:'home',forecastFilter:'formal',scope:'upcoming',venue:'全場',search:'',shown:20,resultShown:20,weatherVenue:'',data:null,audit:null,windEvidence:null,previewEvidence:null,source:'Pages',loading:false,requestId:0};
const ticketPolicy=root.BoatTicketPolicy;
let toastTimeout=null;
function toast(message){
 const el=$('notification');if(!el)return;
 el.textContent=message;el.classList.add('is-shown');
 if(toastTimeout)clearTimeout(toastTimeout);
 toastTimeout=setTimeout(()=>el.classList.remove('is-shown'),2900);
}
function signal(label,kind=''){
 const el=$('connection');if(!el)return;
 el.className='v2-connection'+(kind?' is-'+kind:'');
 el.innerHTML='<span class="v2-signal" aria-hidden="true"></span>'+escapeHTML(label);
}
function sortRaces(list){return [...list].sort(raceOrder)}
function isToday(){return state.data?.event_date===jstDay()}
function nowMs(){return Date.now()}
function displayDate(){return (state.data?.event_date||'—').replaceAll('-','/')}
function allRaces(){return sortRaces(state.data?.forecast_races||[])}
function getFormal(){return allRaces().filter(r=>frozenStatus(r,state.data,ticketPolicy))}
function labelFor(r){
 const phase=racePhase(r,state.data,ticketPolicy);
 return phase==='formal'?'展示反映・正式':phase==='shadow'?'SKIP・研究':'展示未確認・暫定';
}
function timeState(r){
 const ms=cutoffMs(state.data.event_date,r.cutoff_jst);
 const diff=ms-nowMs();
 if(!isToday())return 'archive';
 if(diff>0)return diff<=10*60000?'urgent':'upcoming';
 if(recentCutoff(r,state.data.event_date,nowMs()))return 'closed-recent';
 return 'closed';
}
function formatPicks(combo){
 if(!validCombo(combo))return '<b>'+escapeHTML(combo)+'</b>';
 return '<span class="v2-combo" aria-label="'+escapeHTML(combo)+'">'+combo.split('-').map((n,i)=>
   (i?'<span class="v2-arrow" aria-hidden="true">›</span>':'')+
   '<span class="v2-lane" data-lane="'+n+'">'+n+'</span>').join('')+'</span>';
}
function pickRows(r,limit=3){
 const bets=(r.bets||[]).slice(0,limit);
 return bets.map(b=>'<div class="v2-pick">'+formatPicks(b.combination)+
   '<strong class="v2-amount">'+money(b.virtual_yen)+'</strong></div>').join('');
}
function phaseChip(r){
 const phase=racePhase(r,state.data,ticketPolicy);
 return '<span class="v2-chip '+(phase==='formal'?'formal':phase==='shadow'?'shadow':'pending')+'">'+escapeHTML(labelFor(r))+'</span>';
}
function raceCard(r){
 const phase=racePhase(r,state.data,ticketPolicy),time=timeState(r),closed=time.startsWith('closed');
 const stake=sumBets(r),id=state.data.forecast_races.indexOf(r);
 const timeText=time==='archive'?'過去の固定記録':time==='urgent'?'締切間近':time==='closed-recent'?'締切後10分間・保存中':closed?'締切済み（保存記録）':'締切予定';
 const recentRemaining=time==='closed-recent'?Math.max(0,Math.ceil((cutoffMs(state.data.event_date,r.cutoff_jst)+POST_CUTOFF_GRACE_MS-nowMs())/60000)):0;
 const closedNote=time==='closed-recent'?'<p class="v2-recent-note">締切済み・新規投票不可／固定した予想をあと'+recentRemaining+'分表示</p>':'';
 const label=(r.classification==='BUY'?'BUY分類':r.classification==='SKIP'?'SKIP分類':'WATCH分類');
 return '<article class="v2-race is-'+(phase==='formal'?'formal':'pending')+(closed?' is-closed':'')+(time==='closed-recent'?' is-closed-recent':'')+(time==='urgent'?' is-urgent':'')+'">'+
   '<div class="v2-race-head"><div><h3 class="v2-race-name">'+escapeHTML(r.venue)+' '+r.race+'R</h3>'+
   '<div class="v2-race-deadline"><span>締切</span><strong>'+escapeHTML(r.cutoff_jst)+'</strong><span class="v2-time-status">'+timeText+'</span></div>'+'<p class="v2-race-meta">'+label+' · JST</p></div>'+phaseChip(r)+'</div>'+
   closedNote+'<div class="v2-picks">'+pickRows(r)+'</div>'+
   '<div class="v2-race-foot"><small>上位'+Math.min(r.bets.length,3)+'点 / 全'+r.bets.length+'点・仮想'+money(stake)+'</small>'+
   '<button type="button" class="v2-detail-btn" data-open-race="'+id+'" aria-label="'+escapeHTML(r.venue+' '+r.race+'Rの全買い目を表示')+'">全買い目</button></div></article>';
}
function metric(label,value,sub,kind=''){
 return '<div class="v2-metric'+(kind?' is-'+kind:'')+'"><span class="v2-metric-label">'+escapeHTML(label)+'</span>'+
  '<strong>'+escapeHTML(value)+'</strong><small>'+escapeHTML(sub)+'</small></div>';
}
function title(kicker,heading,subtitle='',action=''){
 return '<div class="v2-page-title"><div><span class="v2-overline">'+escapeHTML(kicker)+'</span>'+
  '<h1>'+escapeHTML(heading)+'</h1><p>'+escapeHTML(subtitle)+'</p></div>'+action+'</div>';
}
function validAudit(){return state.audit?.event_date===state.data?.event_date&&state.audit?.source==='verified BOATRACE official payouts + immutable pre-cutoff predictions'?state.audit:null}
function resultMetrics(){
 return dailyMetrics(validAudit(),state.data?.event_date,'formal');
}
function freshAlert(){
 const date=state.data?.event_date,dt=new Date(state.data?.updated_at_utc);
 if(!isToday())return '<div class="v2-alert is-neutral">表示日は'+escapeHTML(date)+'。過去の発走前固定記録です。今日の締切予定として扱いません。</div>';
 if(!Number.isFinite(dt.getTime()))return '<div class="v2-alert">更新時刻が未確認です。最新の展示・締切状況は確認できません。</div>';
 const age=Math.max(0,Math.floor((nowMs()-dt.getTime())/60000));
 return age>20?'<div class="v2-alert">予想データの更新が'+age+'分前です。最新の展示・締切が反映されていない可能性があります。</div>':'';
}
function home(){
 const data=state.data,rs=allRaces(),formals=getFormal(),current=isToday();
 const upcoming=current?rs.filter(r=>cutoffMs(data.event_date,r.cutoff_jst)>nowMs()):[];
 const recent=current?rs.filter(r=>recentCutoff(r,data.event_date,nowMs())).sort((a,b)=>raceOrder(b,a)):[];
 // Chronological priority is non-negotiable: a pending near-cutoff race must
 // never disappear behind a later formal card.
 const priority=upcoming.slice(0,4);
 const due=upcoming[0]?.cutoff_jst||'—';
 const official=resultMetrics();
 return title('RACE CONTROL / 2.0','今日の予想を、迷わず確認','発走前に固定した買い目・表示区分・公式照合を一画面に。')+
  '<section class="v2-hero"><div class="v2-hero-top"><span class="v2-kicker">BOAT LAB · READ ONLY PREVIEW</span>'+
  '<span class="v2-updated">データ更新 '+escapeHTML(jstStamp(data.updated_at_utc))+'</span></div>'+
  '<h2>'+escapeHTML(displayDate())+' のレース状況</h2><p>展示反映済み・暫定・公式結果を分離。仮想配分であり自動購入はありません。</p></section>'+
  freshAlert()+
  '<div class="v2-section-heading"><div><h2>'+ (upcoming.length?'直近の予想':'直近レースの状況')+'</h2><p>正式と暫定を混ぜず、表示順だけを整理</p></div>'+
  '<button type="button" class="v2-text-action" data-tab="forecasts">予想一覧を見る →</button></div>'+
  (recent.length?'<div class="v2-alert is-neutral">締切後10分以内の保存済み予想：'+recent.length+'R。締切済み・新規投票不可。買い目は固定時のままです。</div>':'')+
  '<div class="v2-grid">'+(priority.length?priority.map(raceCard).join(''):recent.length?'': 
    '<div class="v2-empty"><strong>現在、これから締切を迎えるレースはありません。</strong>保存済みの予想は「予想」タブで全レースを確認できます。'+
    '<div class="v2-cta-row"><button class="v2-detail-btn" data-tab="forecasts" data-show-all="true">全レースの記録</button></div></div>')+'</div>'+
  (recent.length?'<section class="v2-recent-section" aria-label="締切後10分の固定予想">'+
    '<div class="v2-section-heading"><div><h2>締切後10分｜保存済み予想</h2><p>締切済みのレースも直前の買い目を確認できます（投票不可）</p></div></div>'+
    '<div class="v2-grid">'+recent.slice(0,6).map(raceCard).join('')+'</div>'+
    (recent.length>6?'<div class="v2-cta-row"><button type="button" class="v2-secondary-btn" data-tab="forecasts">他の保存済み予想を見る（'+(recent.length-6)+'R）</button></div>':'')+
    '</section>':'')+
  '<div class="v2-metrics">'+
  metric('固定予想',rs.length+'R','読み取り専用')+
  metric('展示反映・正式',formals.length+'R','6艇の展示照合＋締切前固定','primary')+
  metric('次の締切',current?due:'—',current?upcoming.length+'R 受付前の予想':'過去の日付')+
  metric('公式照合',official?official.verified_races+'R':'—','正式予想のうち公式照合済み')+'</div>'+
  '<div class="v2-evidence">正式予想＝保存された発走前の展示入力を6艇照合し、締切前に固定した記録。<b>BUY分類・採算判定とは別</b>です。'+
  '発走後の結果は新しい予想の計算には使いません。詳細は必ず最新の展示・締切を確認してください。</div>';
}
function filterRaces(){
 let rs=allRaces();
 if(state.forecastFilter==='formal')rs=rs.filter(r=>frozenStatus(r,state.data,ticketPolicy));
 if(state.forecastFilter==='research')rs=rs.filter(r=>!frozenStatus(r,state.data,ticketPolicy));
 if(state.venue!=='全場')rs=rs.filter(r=>r.venue===state.venue);
 if(state.search.trim()){
  const query=state.search.trim().toLowerCase();
  rs=rs.filter(r=>(r.venue+' '+r.race+'R '+r.cutoff_jst+' '+r.classification).toLowerCase().includes(query));
 }
 if(state.scope==='upcoming'){
  rs=isToday()?rs.filter(r=>visibleAroundCutoff(r,state.data.event_date,nowMs())):[];
 }
 return rs;
}
function forecasts(){
 const all=allRaces(),formals=getFormal(),venues=[...new Set(all.map(r=>r.venue))].sort((a,b)=>a.localeCompare(b,'ja'));
 const filtered=filterRaces();
 // Keep recently closed forecasts immediately accessible, even when the
 // next dozens of future races would otherwise push them below the fold.
 const recentShown=state.scope==='upcoming'?filtered.filter(r=>recentCutoff(r,state.data.event_date,nowMs())).sort((a,b)=>raceOrder(b,a)):[];
 const futureShown=state.scope==='upcoming'?filtered.filter(r=>!recentCutoff(r,state.data.event_date,nowMs())):filtered;
 const active=(value,target)=>value===target?' class="is-active" aria-pressed="true"':' aria-pressed="false"';
 const selectable=['全場',...venues].map(v=>'<option value="'+escapeHTML(v)+'"'+(state.venue===v?' selected':'')+'>'+escapeHTML(v)+'</option>').join('');
 return title('PREDICTION DESK','予想・買い目','締切・展示反映・仮想配分を確認。正式と暫定は別表示。')+
  freshAlert()+
  '<div class="v2-metrics">'+metric('保存済み',all.length+'R','発走前の固定記録')+
  metric('正式予想',formals.length+'R','条件を満たす展示反映済み','primary')+
  metric('暫定・研究',(all.length-formals.length)+'R','正式買い目ではありません','warning')+
  metric('最終更新',jstStamp(state.data.updated_at_utc).replace(' JST',''),'データ取得時刻')+'</div>'+
  '<div class="v2-filters" aria-label="予想表示を絞り込む"><div class="v2-segments" role="group" aria-label="正式・暫定の切替">'+
  '<button data-forecast-filter="formal" type="button"'+active(state.forecastFilter,'formal')+'>正式予想</button>'+
  '<button data-forecast-filter="research" type="button"'+active(state.forecastFilter,'research')+'>暫定・研究</button>'+
  '<button data-forecast-filter="all" type="button"'+active(state.forecastFilter,'all')+'>すべて</button></div>'+
  '<div class="v2-segments" role="group" aria-label="開催の絞込">'+
  '<button data-scope="upcoming" type="button"'+active(state.scope,'upcoming')+'>締切前＋10分</button>'+
  '<button data-scope="all" type="button"'+active(state.scope,'all')+'>全記録</button></div>'+
  '<label class="v2-filter-label">開催場 <select id="venue-filter" aria-label="開催場で絞る">'+selectable+'</select></label>'+
  '<input id="race-search" class="v2-search" type="search" placeholder="場名・R・締切を検索" aria-label="レース検索" value="'+escapeHTML(state.search)+'"></div>'+
  '<div class="v2-count">'+filtered.length+'R 該当 / '+all.length+'R 保存。'+(state.scope==='upcoming'?'締切前と締切後10分の予想':'締切済みの記録を含む')+'</div>'+
  (recentShown.length?'<section class="v2-recent-section" aria-label="締切後10分の固定予想">'+
    '<div class="v2-section-heading"><div><h2>締切後10分｜保存済み予想（'+recentShown.length+'R）</h2><p>新規投票不可・発走前の固定買い目をそのまま表示</p></div></div>'+
    '<div class="v2-grid">'+recentShown.map(raceCard).join('')+'</div></section>':'')+
  '<div class="v2-grid">'+(futureShown.length?futureShown.slice(0,state.shown).map(raceCard).join(''):
    recentShown.length?'':'<div class="v2-empty"><strong>条件に合う予想はありません。</strong>表示区分・開催場・「全記録」の設定を変えて確認してください。</div>')+'</div>'+
  (futureShown.length>state.shown?'<div class="v2-cta-row"><button class="v2-secondary-btn" data-load-more="forecasts" type="button">さらに'+Math.min(20,futureShown.length-state.shown)+'Rを表示（残り'+(futureShown.length-state.shown)+'R）</button></div>':'')+
  '<p class="v2-subtle">表示は保存済み買い目の読み取り専用。画面の絞り込みや並べ替えでは予想を再計算しません。</p>';
}
let dailyRefreshPromise=null,dailyRefreshedAt=0;
async function refreshTodayResults(force=false){
 if(dailyRefreshPromise)return dailyRefreshPromise;
 if(!force&&Date.now()-dailyRefreshedAt<60000)return;
 dailyRefreshPromise=(async()=>{
  try{
   const response=await fetch('./data/live/audit-latest.json?daily='+Date.now(),{cache:'no-store'});
   if(!response.ok)throw Error('公式監査 HTTP '+response.status);
   const incoming=await response.json();
   if(incoming?.event_date!==jstDay()||incoming.event_date!==state.data?.event_date||
      !dailyMetrics(incoming,jstDay(),'formal'))throw Error('本日の検証済み監査を取得できません');
   const latest=Date.parse(incoming.source_updated_at_utc||incoming.official_evidence_at_utc);
   const previous=Date.parse(state.audit?.source_updated_at_utc||state.audit?.official_evidence_at_utc);
   if(!state.audit||!Number.isFinite(previous)||(Number.isFinite(latest)&&latest>=previous))
    state.audit=incoming;
   dailyRefreshedAt=Date.now();
  }catch(error){
   dailyRefreshedAt=Date.now();
   if(force)toast('本日の公式監査を更新できません。直前の確認済みデータを維持します');
  }finally{
   dailyRefreshPromise=null;
   if(state.tab==='results'&&state.data)render();
  }
 })();
 return dailyRefreshPromise;
}
function results(){
 const today=isToday(),a=today?validAudit():null,o=today?resultMetrics():null;
 const provisional=today?dailyMetrics(a,jstDay(),'provisional'):null;
 const settled=allRaces().map(r=>({r,out:officialOutcome(r,state.data)})).filter(x=>x.out);
 settled.sort((a,b)=>raceOrder(b.r,a.r));
 const verified=settled.slice(0,state.resultShown);
 const formatProfit=o?((o.virtual_profit_yen>0?'+':'')+money(o.virtual_profit_yen)):'—';
 return title('OFFICIAL SETTLEMENT','今日の結果・収支','日本時間の当日分だけを公式照合。過去の収支は集計・表示しません。')+
  '<section class="v2-daily" aria-label="本日の公式照合済み仮想収支">'+
  '<div class="v2-daily-head"><div><span class="v2-overline">TODAY · FORMAL SETTLEMENT</span>'+
  '<h2>'+escapeHTML(jstDay().replaceAll('-','/'))+' の仮想収支</h2>'+
  '<p>展示反映・締切前固定の正式買い目のみ。公式照合済み分を集計。</p></div>'+
  '<button class="v2-secondary-btn" type="button" data-action="refresh-todays-results" '+(dailyRefreshPromise?'disabled':'')+
  '>'+(dailyRefreshPromise?'更新中…':'↻ 今日の収支を更新')+'</button></div>'+
  (!today?'<div class="v2-alert">現在の予想データは前日以前です。本日の数値は未取得として表示します。</div>':
    !o?'<div class="v2-alert">本日の正式成績をまだ確認できません。未取得・未照合は0円と見なしません。</div>':'')+
  '<div class="v2-metrics">'+
  metric('本日の仮想投資',o?money(o.virtual_stake_yen):'—','正式・公式照合分')+
  metric('本日の仮想払戻',o?money(o.virtual_payout_yen):'—','正式・公式照合分')+
  metric('本日の差引収支',formatProfit,'払戻 − 投資',o?(o.virtual_profit_yen>=0?'primary':'warning'):'')+
  metric('本日の回収率',o?percent(o.return_rate):'—','払戻 ÷ 投資')+
  metric('公式照合済み',o?o.verified_races+'R':'—','正式予想のみ')+
  metric('3連単的中',o?o.hits+'R':'—',o?percent(o.hit_rate):'未確認')+
  '</div>'+
  (provisional?'<p class="v2-subtle">参考：暫定・研究（正式とは別集計） '+provisional.verified_races+
   'R／仮想投資 '+money(provisional.virtual_stake_yen)+'／仮想払戻 '+money(provisional.virtual_payout_yen)+
   '／差引 '+(provisional.virtual_profit_yen>0?'+':'')+money(provisional.virtual_profit_yen)+'。正式成績に合算しません。</p>':'')+
  '<p class="v2-subtle">公式照合の記録時刻：'+escapeHTML(jstStamp(a?.official_evidence_at_utc))+
  '。更新ボタンは当日の集計済み監査だけを再取得します。未照合・要確認・返還の検証待ちは確定収支に算入しません。</p></section>'+
  '<div class="v2-section-heading"><div><h2>公式確認済みの着順</h2><p>返還・欠場・照合不一致は、この簡易一覧では的中/不的中に断定しません。</p></div></div>'+
  '<div class="v2-results-list">'+(verified.length?verified.map(({r,out})=>{
    const id=state.data.forecast_races.indexOf(r);
    const label=frozenStatus(r,state.data,ticketPolicy)?'正式固定':'暫定・研究';
    const settlement=virtualSettlement(r,state.data);
    const payout=settlement?money(settlement.payoutYen):'算定保留';
    const profit=settlement?(settlement.profitYen>0?'+':'')+money(settlement.profitYen):'—';
    return '<article class="v2-result-card">'+
      '<div class="v2-result-head"><div><div class="v2-result-name">'+escapeHTML(r.venue)+' '+r.race+'R <span class="v2-chip '+(out.hit?'hit':'miss')+'">'+(out.hit?'的中':'不的中')+'</span></div>'+
      '<p>'+escapeHTML(r.cutoff_jst)+' JST · '+label+'</p></div>'+
      '<div class="v2-result-outcome"><span class="v2-result-finish-label">公式着順</span>'+escapeHTML(out.finish)+'</div></div>'+
      '<div class="v2-settlement"><div class="v2-settlement-main"><span>仮想払戻</span><strong>'+payout+'</strong></div>'+
      '<div class="v2-settlement-details"><div><span>公式3連単配当（100円あたり）</span><strong>'+money(out.payoutPer100)+'</strong></div>'+
      '<div><span>仮想投資</span><strong>'+(settlement?money(settlement.stakeYen):'—')+'</strong></div>'+
      '<div><span>差引収支</span><strong class="'+(settlement?(settlement.profitYen>=0?'v2-profit-plus':'v2-profit-minus'):'')+'">'+profit+'</strong></div></div></div>'+
      '<div class="v2-result-actions"><button class="v2-secondary-btn" data-open-race="'+id+'" type="button">保存買い目を見る</button></div></article>';
  }).join(''):'<div class="v2-empty"><strong>個別レースの公式照合記録がありません。</strong>公開状況と監査の取得時刻を確認してください。</div>')+'</div>'+
  (settled.length>state.resultShown?'<div class="v2-cta-row"><button class="v2-secondary-btn" type="button" data-load-more="results">さらに'+Math.min(20,settled.length-state.resultShown)+'Rを表示</button></div>':'')+
  '<div class="v2-evidence">対象日 '+escapeHTML(state.data.event_date)+' · '+escapeHTML(jstStamp(a?.official_evidence_at_utc))+
  '。上部の成績は監査済み<b>正式予想のみ</b>、個別一覧は公式結果が揃った全区分の保存記録を示します。'+
  '公式3連単配当は100円あたり。各レースの仮想払戻と収支は保存済み買い目の配分で算出。金額が検証不能なら算定保留とし、実投票の収支とは区別します。'+
  '除外条件や返還の扱いが異なるため、一覧表示件数と正式成績の母数は一致するとは限りません。</div>';
}
function dailyLearning(){
 const a=validAudit(),review=a?.head_focus_learning,formal=review?.formal;
 const legacy=a?.learned_formal_comparison;
 const pilot=a?.third_place_pilot_comparison;
 if(!formal?.verified_races)
  return '<section class="v2-learning"><h2>今日の学習監査</h2><p>研究用の公式照合データがまだありません。未確認レースは失敗として数えません。</p></section>';
 const fmt=(v)=>Number.isInteger(v)?String(v):'—';
 const old=legacy?.previous_formal_control,learned=legacy?.learned_formal;
 const matched=Number.isInteger(legacy?.matched_verified_races)?legacy.matched_verified_races:0;
 const comparison=matched>0&&learned&&old?'<p>同一の発走前固定入力・'+fmt(matched)+'R：学習済みモデル <b>'+fmt(learned.hits)+'的中</b>／旧モデル '+fmt(old.hits)+'的中。改善は参考値であり、確率校正や収益性は未証明。</p>':'';
 const formalPilot=pilot?.learned_formal,shadow=pilot?.third_place_trial;
 const thirdPilot=pilot?.paired_verified_races>0&&formalPilot&&shadow?
   '<p>3着研究：同じ'+fmt(pilot.paired_verified_races)+'Rで正式'+fmt(formalPilot.hits)+'的中、研究'+fmt(shadow.hits)+'的中。研究結果は正式成績に含めません。</p>':'';
 const cohorts=review.cohorts||{},multi=cohorts['2_or_more'],zero=cohorts['0'];
 const cells=multi&&zero?
   '<p>発走前の1号艇不利候補が複数ある条件：'+fmt(multi.verified_races)+'R中、1号艇以外勝利 '+fmt(multi.outside_wins)+'R。'+
   '不利候補なし：'+fmt(zero.verified_races)+'R中、1号艇以外勝利 '+fmt(zero.outside_wins)+'R。小標本・相関であり、買い目には未使用。</p>':'';
 return '<section class="v2-learning"><div class="v2-learning-heading"><h2>今日の学習監査</h2><span class="v2-chip shadow">研究・未採用</span></div>'+
   '<p>公式照合済みの<b>正式・展示反映 '+fmt(formal.verified_races)+'R</b>を対象。最上位買い目が1号艇頭 '+fmt(formal.first_ticket_head1)+'R、実際の1号艇勝利 '+fmt(formal.lane1_wins)+'R、1号艇以外の1着抜け '+fmt(formal.outside_win_head_misses)+'R。</p>'+
   '<p>2着抜け '+fmt(formal.second_misses)+'R／3着抜け '+fmt(formal.third_misses)+'R。結果を見てから予想を修正せず、翌日以降の検証に使います。</p>'+
   cells+comparison+thirdPilot+
   '<p class="v2-subtle">出典：発走前固定SHA＋公式払戻。1日分の相関は勝因の証明ではなく、正式ロジックの自動変更にも使いません。</p></section>';
}



function previewFeatureCoverage(){
 const d=state.previewEvidence;
 if(!d||d.event_date!==state.data?.event_date||d.schema!=='boatlabs.openapi-preview-field-coverage.v1')
  return '<section class="v2-learning"><h2>展示情報の取得品質</h2><p>今日の項目別監査データは未確認。取得済みと推測して表示しません。</p></section>';
 const s=d.totals||{},six=s.six_of_six||{},wx=s.weather_present||{};
 const n=v=>Number.isInteger(v)?String(v):'—';
 const status=d.fetch_status==='ok'?'取得元に接続済み':'取得元が利用できず、保存済み記録を保持';
 return '<section class="v2-learning"><div class="v2-learning-heading"><h2>展示情報の取得品質</h2><span class="v2-chip shadow">研究用・未採用</span></div>'+
 '<p>'+escapeHTML(status)+'。締切前に取得したレース <b>'+n(s.races)+'R</b>／6艇の進入・展示ST・タイムが完備 <b>'+n(s.six_boat_ready)+'R</b>。</p>'+
 '<p>6艇完備の内訳：展示タイム <b>'+n(six.exhibition_time)+'R</b>、ST <b>'+n(six.start_timing)+'R</b>、チルト <b>'+n(six.tilt_adjustment)+'R</b>、体重 <b>'+n(six.weight)+'R</b>、重量調整 <b>'+n(six.weight_adjustment)+'R</b>、部品交換欄 <b>'+n(six.parts)+'R</b>。</p>'+
 '<p>場内直前情報：風向 <b>'+n(wx.wind_direction_number)+'R</b>、風速 <b>'+n(wx.wind_speed)+'R</b>、波高 <b>'+n(wx.wave_height)+'R</b>、水温 <b>'+n(wx.water_temperature)+'R</b>。</p>'+
 '<p class="v2-subtle">取得確認 '+escapeHTML(jstStamp(d.checked_at_utc))+'。部品交換欄の欠損は「交換なし」とみなさない。非公式APIの定期スナップショットであり、元の観測時刻の保証はありません。'+
 '<a href="./data/exhibition-preview-evidence/latest.json" target="_blank" rel="noopener noreferrer">場別の詳細</a></p></section>';
}
function onsiteWeatherCaptureStatus(){
 const w=state.windEvidence;
 if(!w||w.event_date!==state.data?.event_date||
    w.schema!=='boatlabs.site-weather-precursor-evidence.v1')
  return '<div class="v2-evidence"><b>場内気象の時刻付き収集：</b>データ未確認。風向・風速を取得したとは表示しません。</div>';
 const valid=Number.isInteger(w.saved_races)&&w.saved_races>=0?w.saved_races:null;
 const count=valid===null?'—':String(valid)+'R';
 const sourceState=w.provider_status==='ok'?'取得元に接続済み':'取得元未確認（'+escapeHTML(w.provider_status||'不明')+'）';
 return '<div class="v2-evidence"><b>場内の風向・風速・波高（研究用）：</b>'+escapeHTML(count)+
  '／'+sourceState+'。取得確認 '+escapeHTML(jstStamp(w.checked_at_utc))+'。'+
  '風向は元データのコードを保管する段階で、向かい風・追い風の補正には未使用。'+
  '<a href="./data/weather-research/latest.json" target="_blank" rel="noopener noreferrer">取得証拠JSONを確認</a></div>';
}
function venueWeatherLearning(){
 const audit=validAudit()?.venue_weather_learning,sites=audit?.by_venue;
 if(!sites||audit.research_only!==true)return '<section class="v2-weather-study"><h2>場別 × 気象研究</h2><p>公式照合済みの場別・気象研究は未公開です。欠損は推測で補いません。</p></section>';
 const keys=Object.keys(sites),active=keys.filter(v=>sites[v]?.official_verified_formal?.n>0).sort((a,b)=>sites[b].official_verified_formal.n-sites[a].official_verified_formal.n);
 const venue=keys.includes(state.weatherVenue)?state.weatherVenue:(active[0]||keys[0]),data=sites[venue]||{},m=data.official_verified_formal||{};
 const n=x=>Number.isInteger(x)?x:'—';
 const ratio=(x,total)=>total>0?(100*x/total).toFixed(1)+'%':'—';
 const windLabels={site_preview_unverified_timestamp:'場内展示値／時刻未検証',nearby_grid_forecast:'周辺格子予報',source_unverified:'出典不明'};
 const waveLabels={site_wave_time_verified:'場内波高／時刻照合済',preview_wave_timestamp_unverified:'展示波高／時刻未検証',source_unverified:'出典不明'};
 const wb={under_4:'4m/s未満','4_to_under_6':'4～6m/s','6_to_under_8':'6～8m/s','8_plus':'8m/s以上'};
 const vb={under_4:'4cm未満','4_to_under_8':'4～8cm','8_plus':'8cm以上'};
 const build=(sets,sources,bands)=>{
  let rows=[];
  for(const [source,group] of Object.entries(sets||{})){
   for(const [band,v] of Object.entries(group||{})){
    if(!v||v.n===0)continue;
    rows.push('<div class="v2-weather-row"><span>'+escapeHTML((sources[source]||source)+'・'+(bands[band]||band))+'</span>'+
    '<strong>'+n(v.n)+'R</strong><small>外艇勝利 '+n(v.outside_wins)+'R／頭抜け '+n(v.head_miss)+'R／2着抜け '+n(v.second_miss)+'R</small></div>');
   }
  }
  return rows.join('')||'<p class="v2-subtle">数値なし・未確認</p>';
 };
 const overview=active.map(v=>{
  const c=sites[v].official_verified_formal;
  return '<div class="v2-weather-place"><strong>'+escapeHTML(v)+'</strong><span>'+n(c.n)+'R</span><small>外艇勝利 '+n(c.outside_wins)+'R／頭抜け '+n(c.head_miss)+'R</small></div>';
 }).join('');
 const options=keys.map(v=>'<option value="'+escapeHTML(v)+'"'+(v===venue?' selected':'')+'>'+escapeHTML(v)+'</option>').join('');
 return '<section class="v2-weather-study"><div class="v2-learning-heading"><h2>🌊 レース場別 × 気象研究</h2><span class="v2-chip shadow">研究用・未採用</span></div>'+
 '<p>江戸川を除く23場の発走前の風速・波高を公式着順と照合。場内観測・周辺予報は別集計で、勝因とは断定しません。</p>'+
 '<div class="v2-weather-places">'+overview+'</div>'+
 '<label class="v2-weather-select" for="weather-venue-filter">レース場を選ぶ <select id="weather-venue-filter">'+options+'</select></label>'+
 '<div class="v2-weather-venue-title"><h3>'+escapeHTML(venue)+'</h3><span>'+n(m.n)+'R 公式照合</span></div>'+
 '<div class="v2-weather-facts"><div><small>外艇勝利</small><strong>'+n(m.outside_wins)+'R</strong></div>'+
 '<div><small>1着抜け</small><strong>'+n(m.head_miss)+'R</strong></div>'+
 '<div><small>2着抜け</small><strong>'+n(m.second_miss)+'R</strong></div>'+
 '<div><small>的中率（参考）</small><strong>'+ratio(m.hits,m.n)+'</strong></div></div>'+
 '<div class="v2-weather-columns"><section><h4>風速 × 着順</h4>'+build(data.wind_by_band,windLabels,wb)+'</section>'+
 '<section><h4>波高 × 着順</h4>'+build(data.wave_by_band,waveLabels,vb)+'</section></div>'+
 '<p class="v2-weather-coverage">検証済みの風向 '+n(data.coverage?.relative_wind_verified)+'R／現地潮位 '+n(data.coverage?.tide_verified)+'R／場内波高 '+n(data.coverage?.wave_site_time_verified)+'R。未確認の風向・潮位は補正に使いません。</p>'+
 '<p class="v2-subtle">保存SHAと公式結果が一致した展示反映・正式のみ。未来の観測値は除外。少標本から正式ロジックは変更しません。</p></section>';
}
function research(){
 return title('LEARNING & EVIDENCE','研究・検証','研究用シャドーと正式予想を分離して参照する。')+
  dailyLearning()+
  previewFeatureCoverage()+
  onsiteWeatherCaptureStatus()+
  venueWeatherLearning()+
  '<div class="v2-info-list">'+
  '<article class="v2-info-tile"><h3>🧠 学習AIの成長</h3><p>正式モデルの推移、前向き比較、同一条件での検証を確認。学習しただけでは精度向上と判定しません。</p><a href="./learning-performance.html">成長記録を見る →</a></article>'+
  '<article class="v2-info-tile"><h3>🌊 WEATHER LAB</h3><p>場内波高・周辺風・予報を区別し、取得時刻と予想への反映を監査。</p><a href="./weather/">気象研究を見る →</a></article>'+
  '<article class="v2-info-tile"><h3>🔬 展示データの効果</h3><p>同一時点の展示あり／なしを別記録で比較。展示効果が実証されたとは断定しません。</p><a href="./exhibition-evidence.html">展示寄与検証を見る →</a></article>'+
  '<article class="v2-info-tile"><h3>🎥 映像・レース研究</h3><p>6艇追跡とターン・伸び・出口加速は独立検証。映像分析を正式的中成績へ混ぜません。</p><a href="./intelligence.html">データ研究室へ →</a></article>'+
  '</div><div class="v2-section-heading"><h2>ソースと運用上の区分</h2></div>'+
  '<div class="v2-evidence"><b>正式：</b>締切前固定・6艇展示照合・保存SHA検証を満たす買い目のみ。'+
  '<br><b>暫定：</b>展示確認前、欠損、締切条件未達など。正式成績には含めません。'+
  '<br><b>研究：</b>シャドー予想と事後分析。結果を使った後付け予想は正式として扱いません。'+
  '<br><b>公式結果：</b>BOATRACE公式照合済みのものだけを成績に計上します。</div>'+
  '<div class="v2-cta-row"><a href="./index.html" class="v2-text-action">現行の詳細機能を開く ↗</a>'+
  '<a href="https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai" class="v2-text-action" target="_blank" rel="noopener noreferrer">GitHubの根拠を見る ↗</a></div>';
}
function updateNav(){
 document.querySelectorAll('[data-tab]').forEach(b=>{
  if(!b.matches('.v2-bottom-nav button, .v2-side-nav button'))return;
  const active=b.dataset.tab===state.tab;
  b.classList.toggle('is-active',active);
  if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
 });
}
function render(){
 if(!state.data)return;
 const main=$('content');
 const pages={home,forecasts,results,research};
 main.innerHTML=pages[state.tab]();
 updateNav();
 signal(isToday()?(state.source==='GitHub main'?'GitHub最新台帳':'発走前記録を表示'):'過去の記録',isToday()?'current':'');
}
function openRace(index){
 const r=state.data?.forecast_races?.[index];
 if(!validRace(r))return;
 const isFormal=frozenStatus(r,state.data,ticketPolicy),official=officialOutcome(r,state.data);
 const frozen=typeof r.frozen_at_utc==='string'?jstStamp(r.frozen_at_utc):'時刻未確認';
 const phase=isFormal?'展示反映済み・正式固定':'暫定・研究用／正式ではありません';
 const note=typeof r.scenario==='string'&&r.scenario.trim()?'<p class="v2-dialog-legal"><b>保存時の展開仮説：</b>'+escapeHTML(r.scenario)+'</p>':'';
 const bets=r.bets.filter(b=>validCombo(b.combination)&&Number.isSafeInteger(b.virtual_yen)&&b.virtual_yen>=0);
 $('dialog-content').innerHTML='<header class="v2-dialog-head"><div><span class="v2-overline">FROZEN FORECAST / PREVIEW</span>'+
  '<h2>'+escapeHTML(r.venue)+' '+r.race+'R</h2><p>締切 '+escapeHTML(r.cutoff_jst)+' JST · '+escapeHTML(phase)+'</p></div>'+
  '<button type="button" class="v2-close" data-close-dialog aria-label="閉じる">×</button></header>'+
  '<div class="v2-dialog-body"><span class="v2-chip '+(isFormal?'formal':'pending')+'">'+escapeHTML(phase)+'</span>'+
  '<h3 class="v2-dialog-section">3連単の全買い目</h3><div class="v2-detail-list">'+
  bets.map(b=>'<div class="v2-pick">'+formatPicks(b.combination)+'<strong class="v2-amount">'+money(b.virtual_yen)+'</strong></div>').join('')+'</div>'+
  '<div class="v2-dialog-summary"><span>合計 '+bets.length+'点（仮想）</span><strong>'+money(sumBets(r))+'</strong></div>'+
  note+'<div class="v2-evidence">予想固定 '+escapeHTML(frozen)+'<br>SHA：<code>'+escapeHTML(r.sha256||'未確認')+'</code><br>'+
  'モデル：'+escapeHTML(r.model_version||'未確認')+'<br>分類：'+escapeHTML(r.classification||'未確認')+'</div>'+
  (official?'<p class="v2-dialog-legal">公式結果：<b>'+escapeHTML(official.finish)+'</b>（'+(official.hit?'この保存買い目で的中':'この保存買い目では不的中')+'）・公式配当 <b>'+money(official.payoutPer100)+'</b>／100円・仮想払戻 <b>'+(virtualSettlement(r,state.data)?money(virtualSettlement(r,state.data).payoutYen):'算定保留')+'</b></p>':
    '<p class="v2-dialog-legal">公式照合未完了／返還・欠場などの保留がある場合は、的中判定を表示しません。</p>')+
  '<div class="v2-dialog-actions"><button class="v2-detail-btn" type="button" data-copy-race="'+index+'">買い目をコピー</button>'+
  '<button class="v2-secondary-btn" type="button" data-close-dialog>閉じる</button></div>'+
  '<p class="v2-dialog-legal">これは保存済みの仮想買い目です。画面操作で正式予想や配分を変更しません。</p></div>';
 const d=$('race-dialog');
 if(!d.open)d.showModal();
}
async function copyRace(index){
 const r=state.data?.forecast_races?.[index];
 if(!validRace(r))return;
 const txt=[state.data.event_date+' '+r.venue+' '+r.race+'R '+r.cutoff_jst+' JST',
   frozenStatus(r,state.data,ticketPolicy)?'展示反映・正式固定':'暫定・研究用',
   ...r.bets.map(b=>b.combination+' '+money(b.virtual_yen)),
   '計 '+money(sumBets(r))+' / 仮想配分・投票していません'].join('\n');
 try{
  if(!navigator.clipboard?.writeText)throw new Error('clipboard API unavailable');
  await navigator.clipboard.writeText(txt);toast('保存済み買い目をコピーしました');
 }catch{toast('自動コピーできません。画面で買い目をご確認ください');}
}

let canonicalBusy=false;
/* Reuse the old app's read-only canonical immutable forecast feed. */
async function pollCanonicalForecast(){
 const client=root.BoatCanonicalExhibitionFeed;
 if(!client||canonicalBusy||!state.data||document.hidden)return {state:'skipped'};
 canonicalBusy=true;
 try{
  const check=await client.check({current:state.data});
  if(check.state!=='newer')return check;
  const incoming=normalize(check.payload);
  const held=state.data;
  const oldTime=Date.parse(held?.updated_at_utc),newTime=Date.parse(incoming.updated_at_utc);
  if(incoming.event_date<held.event_date||
     (incoming.event_date===held.event_date&&
      Number.isFinite(oldTime)&&(!Number.isFinite(newTime)||newTime<=oldTime)))
      return {state:'older'};
  state.data=incoming;state.source='GitHub main';
  if(!isToday()||incoming.forecast_races.every(r=>!visibleAroundCutoff(r,incoming.event_date,nowMs())))state.scope='all';
  render();
  return {state:'applied'};
 }catch(error){
  // Never replace a last good frozen forecast when GitHub/CDN is unavailable.
  return {state:'unavailable',reason:String(error?.message||error)};
 }finally{canonicalBusy=false;}
}
async function load(){
 if(state.loading)return;
 state.loading=true;const id=++state.requestId;
 $('refresh').disabled=true;signal('最新データ取得中');
 try{
  const [dataResponse,auditResponse,windEvidenceResponse,previewEvidenceResponse]=await Promise.all([
   fetch('./data/live/latest.json',{cache:'no-store'}),
   fetch('./data/live/audit-latest.json',{cache:'no-store'}).catch(()=>null),
   fetch('./data/weather-research/latest.json',{cache:'no-store'}).catch(()=>null),
   fetch('./data/exhibition-preview-evidence/latest.json',{cache:'no-store'}).catch(()=>null)
  ]);
  if(!dataResponse.ok)throw new Error('予想データ HTTP '+dataResponse.status);
  const data=normalize(await dataResponse.json());
  let audit=null,windEvidence=null,previewEvidence=null;
  if(auditResponse?.ok){try{audit=await auditResponse.json()}catch{}}
  if(windEvidenceResponse?.ok){try{windEvidence=await windEvidenceResponse.json()}catch{}}
  if(previewEvidenceResponse?.ok){try{previewEvidence=await previewEvidenceResponse.json()}catch{}}
  if(id!==state.requestId)return;
  state.windEvidence=windEvidence;
  state.previewEvidence=previewEvidence;
  // Pages may lag GitHub main; do not roll back a newer frozen forecast.
  const held=state.data;
  const dataTime=Date.parse(data.updated_at_utc),heldTime=Date.parse(held?.updated_at_utc);
  const rollback=!!held&&(data.event_date<held.event_date||
    (data.event_date===held.event_date&&Number.isFinite(heldTime)&&
     (!Number.isFinite(dataTime)||dataTime<heldTime)));
  if(!rollback){state.data=data;state.source='Pages';}
  if(audit?.event_date===state.data?.event_date){
   const prior=Date.parse(state.audit?.source_updated_at_utc||state.audit?.official_evidence_at_utc);
   const next=Date.parse(audit.source_updated_at_utc||audit.official_evidence_at_utc);
   if(!state.audit||!Number.isFinite(prior)||(Number.isFinite(next)&&next>=prior))state.audit=audit;
  }
  if(!isToday()||state.data.forecast_races.every(r=>!visibleAroundCutoff(r,state.data.event_date,nowMs())))state.scope='all';
  render();
  if(state.tab==='results')void refreshTodayResults();
 }catch(error){
  if(!state.data){
   $('content').innerHTML='<div class="v2-empty" role="alert"><strong>固定予想の取得に失敗しました。</strong>'+
    escapeHTML(error.message)+'。古い予想やダミー値を新しいデータとして表示しません。'+
    '<div class="v2-cta-row"><button class="v2-detail-btn" data-retry type="button">再取得する</button>'+
    '<a class="v2-text-action" href="./index.html">現行アプリへ</a></div></div>';
  }else{
   signal('データ更新失敗','alert');toast('更新に失敗しました。前回取得した表示を維持します');
  }
 }finally{state.loading=false;$('refresh').disabled=false;if(state.data)void pollCanonicalForecast();}
}
document.addEventListener('click',event=>{
 const target=event.target;
 if(!(target instanceof Element))return;
 if(target.closest('[data-action="refresh-todays-results"]')){void refreshTodayResults(true);return;}
 const tab=target.closest('[data-tab]');
 if(tab){
  const next=tab.dataset.tab;
  if(!['home','forecasts','results','research'].includes(next))return;
  state.tab=next;
  if(tab.dataset.showAll==='true')state.scope='all';
  state.shown=20;render();if(next==='results')void refreshTodayResults();window.scrollTo({top:0,behavior:'instant'});$('content').focus();return;
 }
 const filter=target.closest('[data-forecast-filter]');
 if(filter){
  if(!['formal','research','all'].includes(filter.dataset.forecastFilter))return;
  state.forecastFilter=filter.dataset.forecastFilter;state.shown=20;render();return;
 }
 const scope=target.closest('[data-scope]');
 if(scope){if(!['upcoming','all'].includes(scope.dataset.scope))return;
  state.scope=scope.dataset.scope;state.shown=20;render();return;}
 const more=target.closest('[data-load-more]');
 if(more){if(more.dataset.loadMore==='forecasts')state.shown+=20;
  else if(more.dataset.loadMore==='results')state.resultShown+=20;
  render();return;}
 const detail=target.closest('[data-open-race]');
 if(detail){const i=Number(detail.dataset.openRace);if(Number.isInteger(i))openRace(i);return;}
 const copy=target.closest('[data-copy-race]');
 if(copy){const i=Number(copy.dataset.copyRace);if(Number.isInteger(i))void copyRace(i);return;}
 if(target.closest('[data-close-dialog]')){$('race-dialog').close();return;}
 if(target.closest('[data-retry]')){void load();}
});
document.addEventListener('change',e=>{
 if(e.target?.id==='venue-filter'){
  state.venue=e.target.value;state.shown=20;render();
 }
});
document.addEventListener('change',e=>{if(e.target?.id==='weather-venue-filter'){state.weatherVenue=e.target.value;render();}});
document.addEventListener('input',e=>{
 if(e.target?.id==='race-search'){
  const value=e.target.value;
  state.search=value;state.shown=20;
  // Preserve the user's keyboard focus/selection while filtering.
  const pos=e.target.selectionStart;
  render();
  const next=$('race-search');
  if(next){next.focus();try{next.setSelectionRange(pos,pos)}catch{}}
 }
});
$('refresh').addEventListener('click',()=>void load());
$('race-dialog').addEventListener('click',event=>{
 if(event.target===$('race-dialog'))$('race-dialog').close();
});
void load();
// Re-fetch real source snapshots at a moderate interval, matching the
// existing PWA's foreground refresh policy. No write, no local fallback.
setInterval(()=>{if(!document.hidden&&!state.loading)void load()},300000);
setInterval(()=>{if(!document.hidden)void pollCanonicalForecast()},60000);
setInterval(()=>{if(!document.hidden&&state.tab==='results')void refreshTodayResults()},60000);
setInterval(()=>{if(!document.hidden&&state.data&&['home','forecasts'].includes(state.tab))render()},60000);
document.addEventListener('visibilitychange',()=>{
 if(!document.hidden&&state.tab==='results')void refreshTodayResults();
 if(!document.hidden&&!state.loading)void load();
 if(!document.hidden)void pollCanonicalForecast();
});
})(typeof window==='undefined'?globalThis:window);
