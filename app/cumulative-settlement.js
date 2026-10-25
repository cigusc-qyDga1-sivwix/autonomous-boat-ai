/* BOAT LAB: dynamic daily official-only cumulative virtual settlement.
 * Reads immutable per-date ledgers; no predictions, results or SHA are modified. */
(function(root){
'use strict';
const START_DAY='2026-10-22';
const jstDay=now=>{
 const date=now instanceof Date?now:new Date(now);
 if(!Number.isFinite(date.getTime()))throw Error('現在日付が不正です');
 return new Intl.DateTimeFormat('en-CA',{
  timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'
 }).format(date);
};
const daysThrough=now=>{
 const end=jstDay(now),result=[];
 const start=Date.parse(START_DAY+'T00:00:00Z'),last=Date.parse(end+'T00:00:00Z');
 if(!Number.isFinite(last)||last<start)return [];
 for(let day=start;day<=last&&result.length<370;day+=86400000)
  result.push(new Date(day).toISOString().slice(0,10));
 return result;
};
const label=day=>day.slice(5).replace('-','/');
const EMPTY=()=>({eligible:0,checked:0,hits:0,invested:0,paid:0,profit:0,excluded:0});
const combo=x=>typeof x==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(x)&&new Set(x.split('-')).size===3;
const money=n=>(n>=0?'+':'−')+Math.abs(n).toLocaleString('ja-JP')+'円';
const yen=n=>n.toLocaleString('ja-JP')+'円';
const validBets=bets=>Array.isArray(bets)&&bets.length>=4&&bets.length<=12&&
 bets.every(b=>b&&combo(b.combination)&&Number.isSafeInteger(b.virtual_yen)&&b.virtual_yen>=0&&b.virtual_yen%100===0)&&
 new Set(bets.map(b=>b.combination)).size===bets.length&&
 bets.reduce((s,b)=>s+b.virtual_yen,0)===50000;
function summary(doc,day,formalOnly=false){
 if(!doc||doc.event_date!==day||!doc.race_records||typeof doc.race_records!=='object'||Array.isArray(doc.race_records))
   throw Error('日付別の固定記録が不正です');
 const list=Object.entries(doc.race_records);
 if(list.length>288)throw Error('レース記録数が上限を超えています');
 const out=EMPTY();
 for(const [id,record] of list){
  if(!/^\d{1,2}-([1-9]|1[0-2])$/.test(id)||!record||!Array.isArray(record.versions)||!record.versions.length)continue;
  const r=record.versions[record.versions.length-1];
  const cutoff=Date.parse(r?.cutoff_iso_jst),frozen=Date.parse(r?.frozen_at_utc);
  if(!r||typeof r.sha256!=='string'||! /^[a-f0-9]{64}$/i.test(r.sha256)||
     typeof r.cutoff_iso_jst!=='string'||!r.cutoff_iso_jst.startsWith(day+'T')||
     !/(\+09:00)$/.test(r.cutoff_iso_jst)||
     !Number.isFinite(cutoff)||!Number.isFinite(frozen)||frozen>=cutoff||
     !validBets(r.bets)||r.venue!==record.venue||r.race!==record.race){out.excluded++;continue;}
  if(formalOnly&&!root.BoatTicketPolicy?.classify(r,day).formal)continue;
  out.eligible++;
  if(record.official_conflict||record.official_review){out.excluded++;continue;}
  const p=record.official_pay;
  if(!p)continue;
  if(p.source!=='boatrace_official_pay'||p.verified!==true||!combo(p.finish)||
     !Number.isSafeInteger(p.payout_per_100)||p.payout_per_100<100||
     p.payout_per_100>10000000||p.payout_per_100%10!==0||
     (p.snapshot_sha256&&p.snapshot_sha256!==r.sha256)){out.excluded++;continue;}
  const match=r.bets.find(b=>b.combination===p.finish);
  const payout=match?Math.round(match.virtual_yen*p.payout_per_100/100):0;
  out.checked++;out.hits+=Number(!!match);out.invested+=50000;out.paid+=payout;
 }
 out.profit=out.paid-out.invested;
 return out;
}
function overlayVerifiedPays(ledger,doc,day){
 if(!ledger||ledger.event_date!==day||!ledger.race_records||
    !doc||doc.date!==day||doc.status!=='verified_by_server_fetch'||
    doc.evidence_type!=='official_boatrace_pay_snapshot'||
    doc.source_url!=='https://www.boatrace.jp/owpc/pc/race/pay?hd='+day.replace(/-/g,'')||
    !Number.isFinite(Date.parse(doc.retrieved_at_utc))||
    !doc.results||typeof doc.results!=='object'||Array.isArray(doc.results)||
    Object.keys(doc.results).length>288)return 0;
 let added=0;
 for(const [id,rec] of Object.entries(ledger.race_records)){
  if(!rec||!Array.isArray(rec.versions)||!rec.versions.length||
     rec.official_conflict||rec.official_review)continue;
  const snap=rec.versions[rec.versions.length-1];
  if(!snap||!/^[a-f0-9]{64}$/i.test(snap.sha256||''))continue;
  const pay=doc.results[id];
  if(doc.reviews?.[id]||doc.cancellations?.[id]||doc.conflicts?.[id])continue;
  if(!pay||!combo(pay.finish)||!Number.isSafeInteger(pay.payout_per_100)||
     pay.payout_per_100<100||pay.payout_per_100>10000000||
     pay.payout_per_100%10!==0)continue;
  const existing=rec.official_pay;
  if(existing&&(!existing.verified||existing.finish!==pay.finish||
      existing.payout_per_100!==pay.payout_per_100))continue;
  if(existing?.verified)continue;
  rec.official_pay={
   finish:pay.finish,payout_per_100:pay.payout_per_100,
   verified:true,source:'boatrace_official_pay',source_url:doc.source_url,
   recorded_at:doc.retrieved_at_utc,snapshot_sha256:snap.sha256
  };
  added++;
 }
 return added;
}
let state={loading:false,ready:false,days:{},formalDays:{},errors:{},range:[],lastFetchedAt:0};
let inflight=null;
async function load(force=false,fetcher=root.fetch?.bind(root),now=new Date()){
 if(inflight)return inflight;
 const range=daysThrough(now);
 const fresh=state.ready&&state.range.join(',')===range.join(',')&&
  Date.now()-state.lastFetchedAt<90000;
 if(!force&&fresh)return state;
 state={loading:true,ready:false,days:force?{}:{...state.days},errors:{},
   range,formalDays:force?{}:{...state.formalDays},lastFetchedAt:state.lastFetchedAt};
 inflight=(async()=>{
  for(const day of range){
   try{
    if(typeof fetcher!=='function')throw Error('取得機能が利用できません');
    const response=await fetcher('./data/live/'+day+'.json',{cache:'no-store'});
    if(!response?.ok)throw Error('HTTP '+(response?.status??'接続失敗'));
    const ledger=await response.json();
    if(day===range[range.length-1]){
     // Daily immutable ledger may lag the independently refreshed verified
     // official pay snapshot by hours. Overlay ONLY official verified pays
     // matching the same immutable prediction SHA, without changing bets.
     try{
      const payResponse=await fetcher('./data/live/official-pay/'+day+'.json?refresh='+Date.now(),{cache:'no-store'});
      if(payResponse?.ok)overlayVerifiedPays(ledger,await payResponse.json(),day);
     }catch(_e){/* older ledger is still useful; never guess a payoff */ }
    }
    state.days[day]=summary(ledger,day);
    state.formalDays[day]=summary(ledger,day,true);
   }catch(e){
    delete state.days[day];delete state.formalDays[day];state.errors[day]=e?.message||'データを取得できません';
   }
  }
  state.loading=false;state.ready=true;state.lastFetchedAt=Date.now();
  return state;
 })().finally(()=>{inflight=null;});
 return inflight;
}
function status(){return state.loading?'loading':state.ready?'ready':'idle'}
function needsRefresh(now=new Date()){
 const current=daysThrough(now);
 return !state.loading&&(!state.ready||state.range.join(',')!==current.join(',')||
  Date.now()-state.lastFetchedAt>=90000);
}
function renderFormal(){
 if(!root.BoatTicketPolicy)return '';
 if(!state.range.some(day=>state.formalDays[day]))return '<section class="card card-pad"><h2>正式買い目の累積収支</h2><p>日付別の固定記録を取得できていないため、正式収支は未集計です。</p></section>';
 const total=EMPTY();
 for(const day of state.range){const s=state.formalDays[day];if(s)for(const key of Object.keys(total))total[key]+=s[key];}
 return '<section class="card card-pad" aria-label="正式買い目の累積収支"><h2>正式買い目の累積収支</h2><p>展示反映・締切前固定 '+total.eligible+'R ／ 公式照合 '+total.checked+'R ／ 的中 '+total.hits+'R</p><p>仮想投資 '+yen(total.invested)+' ／ 仮想払戻 '+yen(total.paid)+' ／ 仮想収支 '+money(total.profit)+' ／ 回収率 '+(total.invested?(100*total.paid/total.invested).toFixed(1)+'%':'—')+'</p><p>各レースの最新の展示反映固定版だけ。暫定予想・未照合・返還・中止は正式収支に含めません。欠損日は集計対象外です。</p></section>';
}
function render(){
 const dates=state.range.length?state.range:daysThrough(new Date());
 const found=dates.filter(day=>state.days[day]);
 const combined=EMPTY();
 let rows='',running=0;
 for(const day of dates){
  const d=state.days[day];
  if(!d){rows+='<tr><th scope="row">'+label(day)+'</th><td colspan="5">未取得・累積に含めない</td></tr>';continue;}
  for(const key of ['eligible','checked','hits','invested','paid','profit'])combined[key]+=d[key];
  running+=d.profit;
  rows+='<tr><th scope="row">'+label(day)+'</th><td>'+d.checked+' / '+d.eligible+
   'R</td><td>'+d.hits+'R</td><td>'+yen(d.invested)+'</td><td>'+yen(d.paid)+
   '</td><td class="'+(d.profit>=0?'cum-plus':'cum-minus')+'">'+money(d.profit)+'</td></tr>';
 }
 const completed=found.length===dates.length;
 const current=label(dates.at(-1)||START_DAY);
 return renderFormal()+'<section class="card card-pad cumulative-settlement" aria-label="10月22日からの累積仮想収支">'+
  '<div class="section-head"><div><h2 class="section-title">📈 10/22〜'+current+' 累積収支</h2>'+
  '<p class="cum-subtitle">全研究予想（展示前の暫定を含む）× 公式確認済み払戻だけ（当日は途中経過）</p></div>'+
  '<button type="button" class="btn btn-white" data-action="reload-cumulative-results" '+
   (state.loading?'disabled':'')+'>'+(state.loading?'読み込み中…':'↻ 再集計')+'</button></div>'+
  (found.length?
   '<div class="cum-total"><span>'+(completed?'累積仮想収支（当日は暫定）':'取得済み日だけの暫定累積')+
   '</span><strong class="'+(running>=0?'cum-plus':'cum-minus')+'">'+money(running)+'</strong>'+
   '<small>仮想投資累計 '+yen(combined.invested)+' ／ 仮想払戻累計 '+yen(combined.paid)+'</small>'+
   '<small>公式照合 '+combined.checked+'R／対象固定 '+combined.eligible+'R · 的中 '+combined.hits+
   'R · 回収率 '+(combined.invested?(combined.paid/combined.invested*100).toFixed(1)+'%':'—')+'</small></div>':
   '<p class="notice">まだ集計できる日付別の公式照合記録がありません。</p>')+
  '<div class="cum-table-wrap"><table class="cum-table"><thead><tr><th>日付</th><th>公式照合</th>'+
  '<th>的中</th><th>仮想投資</th><th>仮想払戻</th><th>日別収支</th></tr></thead><tbody>'+rows+
  '</tbody></table></div>'+
  (state.loading?'<p class="help">10/22から'+current+'の固定記録を読み込んでいます…</p>':'')+
  (Object.keys(state.errors).length?'<p class="notice warn">未取得：'+
    Object.keys(state.errors).map(day=>label(day)+'分').join('、')+
    '。欠損日は0円として扱わず、累積から除外しています。</p>':'')+
  '<p class="help">10/22以降の日別GitHub発走前固定記録について、各レースの最新の締切前固定バージョンだけを計上。'+
  '今日を含め公式照合済みレースだけが仮想投資と払戻の集計対象です。未照合・中止・返還・矛盾・不正データは集計せず、日付欠損を0円扱いしません。'+
  '旧モデルと新モデルの買い目を二重計上しません。全研究予想の仮想収支であり、実際の購入成績・正式BUY収支ではありません。</p></section>';
}
root.BoatCumulative={summary,overlayVerifiedPays,load,render,status,needsRefresh,daysThrough,jstDay,get dates(){return daysThrough(new Date())}};
})(typeof window==='undefined'?globalThis:window);
