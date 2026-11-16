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
const racePhase=(r,data,policy)=>frozenStatus(r,data,policy)?'formal':r.classification==='SKIP'?'shadow':'pending';
function normalize(payload){
 if(!payload||!validDay(payload.event_date)||payload.mode!=='auto-live'||!Array.isArray(payload.forecast_races)||payload.forecast_races.length>300)
   throw new Error('正式な自動予想データを確認できませんでした');
 const races=payload.forecast_races.filter(validRace);
 // Empty auto-live days are valid: show an honest 0R state, not a load failure.
 return {...payload,forecast_races:races};
}
const engine={money,percent,validDay,validClock,jstDay,jstStamp,cutoffMs,sumBets,validRace,validCombo,frozenStatus,verifiedOfficial,officialOutcome,racePhase,normalize,raceOrder};
root.BoatLabV2=engine;
if(typeof module==='object'&&module.exports)module.exports=engine;
if(typeof document==='undefined')return;

const $=id=>document.getElementById(id);
const state={tab:'home',forecastFilter:'formal',scope:'upcoming',venue:'全場',search:'',shown:20,resultShown:20,data:null,audit:null,loading:false,requestId:0};
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
 if(diff>=-10*60000)return 'closed-recent';
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
 const timeText=time==='archive'?'過去の固定記録':time==='urgent'?'締切間近':closed?'締切済み（保存記録）':'締切予定';
 const label=(r.classification==='BUY'?'BUY分類':r.classification==='SKIP'?'SKIP分類':'WATCH分類');
 return '<article class="v2-race is-'+(phase==='formal'?'formal':'pending')+(closed?' is-closed':'')+(time==='urgent'?' is-urgent':'')+'">'+
   '<div class="v2-race-head"><div><h3 class="v2-race-name">'+escapeHTML(r.venue)+' '+r.race+'R</h3>'+
   '<div class="v2-race-deadline"><span>締切</span><strong>'+escapeHTML(r.cutoff_jst)+'</strong><span class="v2-time-status">'+timeText+'</span></div>'+'<p class="v2-race-meta">'+label+' · JST</p></div>'+phaseChip(r)+'</div>'+
   '<div class="v2-picks">'+pickRows(r)+'</div>'+
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
 const o=validAudit()?.by_ticket_status?.formal;
 return o&&Number.isInteger(o.verified_races)?o:null;
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
 const recent=current?rs.filter(r=>{const d=nowMs()-cutoffMs(data.event_date,r.cutoff_jst);return d>=0&&d<600000&&r.classification!=='SKIP'}):[];
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
  (recent.length?'<div class="v2-alert is-neutral">締切後10分の保存済み予想：'+recent.length+'R。新規投票不可・買い目は変更しません。</div>':'')+
  '<div class="v2-grid">'+(priority.length?priority.map(raceCard).join(''):
    '<div class="v2-empty"><strong>現在、これから締切を迎えるレースはありません。</strong>保存済みの予想は「予想」タブで全レースを確認できます。'+
    '<div class="v2-cta-row"><button class="v2-detail-btn" data-tab="forecasts" data-show-all="true">全レースの記録</button></div></div>')+'</div>'+
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
  rs=isToday()?rs.filter(r=>cutoffMs(state.data.event_date,r.cutoff_jst)>nowMs()):[];
 }
 return rs;
}
function forecasts(){
 const all=allRaces(),formals=getFormal(),venues=[...new Set(all.map(r=>r.venue))].sort((a,b)=>a.localeCompare(b,'ja'));
 const filtered=filterRaces();
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
  '<button data-scope="upcoming" type="button"'+active(state.scope,'upcoming')+'>これから</button>'+
  '<button data-scope="all" type="button"'+active(state.scope,'all')+'>全記録</button></div>'+
  '<label class="v2-filter-label">開催場 <select id="venue-filter" aria-label="開催場で絞る">'+selectable+'</select></label>'+
  '<input id="race-search" class="v2-search" type="search" placeholder="場名・R・締切を検索" aria-label="レース検索" value="'+escapeHTML(state.search)+'"></div>'+
  '<div class="v2-count">'+filtered.length+'R 該当 / '+all.length+'R 保存。'+(state.scope==='upcoming'?'締切前のみ':'締切済みの記録を含む')+'</div>'+
  '<div class="v2-grid">'+(filtered.length?filtered.slice(0,state.shown).map(raceCard).join(''):
  '<div class="v2-empty"><strong>条件に合う予想はありません。</strong>表示区分・開催場・「全記録」の設定を変えて確認してください。</div>')+'</div>'+
  (filtered.length>state.shown?'<div class="v2-cta-row"><button class="v2-secondary-btn" data-load-more="forecasts" type="button">さらに'+Math.min(20,filtered.length-state.shown)+'Rを表示（残り'+(filtered.length-state.shown)+'R）</button></div>':'')+
  '<p class="v2-subtle">表示は保存済み買い目の読み取り専用。画面の絞り込みや並べ替えでは予想を再計算しません。</p>';
}
function results(){
 const a=validAudit(),o=resultMetrics();
 const auditSource=a?'監査ファイルの公式照合済みデータ':'同じ対象日の公式監査が取得できていません';
 const settled=allRaces().map(r=>({r,out:officialOutcome(r,state.data)})).filter(x=>x.out);
 settled.sort((a,b)=>raceOrder(b.r,a.r));
 const verified=settled.slice(0,state.resultShown);
 const formatProfit=o?((o.virtual_profit_yen>0?'+':'')+money(o.virtual_profit_yen)):'—';
 return title('OFFICIAL SETTLEMENT','結果・成績','公式照合済みの固定予想だけで検証。研究と実投票を混同しません。')+
  (!a?'<div class="v2-alert">公式照合監査を読み込めていません。未確認値は表示しません。</div>':'')+
  '<div class="v2-metrics">'+metric('正式・公式照合',o?o.verified_races+'R':'—',auditSource)+
  metric('3連単的中',o?o.hits+'R':'—',o?percent(o.hit_rate):'未集計','primary')+
  metric('仮想回収率',o?percent(o.return_rate):'—','実投票の収支ではありません')+
  metric('仮想収支',formatProfit,'照合済みのみ')+'</div>'+
  '<div class="v2-section-heading"><div><h2>公式確認済みの着順</h2><p>返還・欠場・照合不一致は、この簡易一覧では的中/不的中に断定しません。</p></div></div>'+
  '<div class="v2-results-list">'+(verified.length?verified.map(({r,out})=>{
    const id=state.data.forecast_races.indexOf(r);
    const label=frozenStatus(r,state.data,ticketPolicy)?'正式固定':'暫定・研究';
    return '<article class="v2-result-card"><div><div class="v2-result-name">'+escapeHTML(r.venue)+' '+r.race+'R <span class="v2-chip '+(out.hit?'hit':'miss')+'">'+(out.hit?'的中':'不的中')+'</span></div>'+
    '<p>'+escapeHTML(r.cutoff_jst)+' JST · '+label+'</p></div>'+
    '<div class="v2-result-outcome">'+escapeHTML(out.finish)+
    '<small><button class="v2-secondary-btn" data-open-race="'+id+'" type="button">保存買い目を見る</button></small></div></article>';
  }).join(''):'<div class="v2-empty"><strong>個別レースの公式照合記録がありません。</strong>公開状況と監査の取得時刻を確認してください。</div>')+'</div>'+
  (settled.length>state.resultShown?'<div class="v2-cta-row"><button class="v2-secondary-btn" type="button" data-load-more="results">さらに'+Math.min(20,settled.length-state.resultShown)+'Rを表示</button></div>':'')+
  '<div class="v2-evidence">対象日 '+escapeHTML(state.data.event_date)+' · '+escapeHTML(jstStamp(a?.official_evidence_at_utc))+
  '。上部の成績は監査済み<b>正式予想のみ</b>、個別一覧は公式結果が揃った全区分の保存記録を示します。'+
  '除外条件や返還の扱いが異なるため、一覧表示件数と正式成績の母数は一致するとは限りません。</div>';
}
function research(){
 return title('LEARNING & EVIDENCE','研究・検証','研究用シャドーと正式予想を分離して参照する。')+
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
 signal(isToday()?'発走前記録を表示':'過去の記録',isToday()?'current':'');
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
  (official?'<p class="v2-dialog-legal">公式結果：<b>'+escapeHTML(official.finish)+'</b>（'+(official.hit?'この保存買い目で的中':'この保存買い目では不的中')+'）</p>':
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
async function load(){
 if(state.loading)return;
 state.loading=true;const id=++state.requestId;
 $('refresh').disabled=true;signal('最新データ取得中');
 try{
  const [dataResponse,auditResponse]=await Promise.all([
   fetch('./data/live/latest.json',{cache:'no-store'}),
   fetch('./data/live/audit-latest.json',{cache:'no-store'}).catch(()=>null)
  ]);
  if(!dataResponse.ok)throw new Error('予想データ HTTP '+dataResponse.status);
  const data=normalize(await dataResponse.json());
  let audit=null;
  if(auditResponse?.ok){try{audit=await auditResponse.json()}catch{}}
  if(id!==state.requestId)return;
  state.data=data;state.audit=audit;
  if(!isToday()||data.forecast_races.every(r=>cutoffMs(data.event_date,r.cutoff_jst)<=nowMs()))state.scope='all';
  render();
 }catch(error){
  if(!state.data){
   $('content').innerHTML='<div class="v2-empty" role="alert"><strong>固定予想の取得に失敗しました。</strong>'+
    escapeHTML(error.message)+'。古い予想やダミー値を新しいデータとして表示しません。'+
    '<div class="v2-cta-row"><button class="v2-detail-btn" data-retry type="button">再取得する</button>'+
    '<a class="v2-text-action" href="./index.html">現行アプリへ</a></div></div>';
  }else{
   signal('データ更新失敗','alert');toast('更新に失敗しました。前回取得した表示を維持します');
  }
 }finally{state.loading=false;$('refresh').disabled=false;}
}
document.addEventListener('click',event=>{
 const target=event.target;
 if(!(target instanceof Element))return;
 const tab=target.closest('[data-tab]');
 if(tab){
  const next=tab.dataset.tab;
  if(!['home','forecasts','results','research'].includes(next))return;
  state.tab=next;
  if(tab.dataset.showAll==='true')state.scope='all';
  state.shown=20;render();window.scrollTo({top:0,behavior:'instant'});$('content').focus();return;
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
setInterval(()=>{if(!document.hidden&&state.data&&['home','forecasts'].includes(state.tab))render()},60000);
document.addEventListener('visibilitychange',()=>{
 if(!document.hidden&&!state.loading)void load();
});
})(typeof window==='undefined'?globalThis:window);
