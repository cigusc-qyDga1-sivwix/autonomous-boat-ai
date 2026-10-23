/* BOAT LAB: historical official-only cumulative virtual settlement (Oct 22–23, 2026).
 * Reads immutable per-date ledgers; no predictions, results or SHA are modified. */
(function(root){
'use strict';
const DAYS=['2026-10-22','2026-10-23'];
const EMPTY=()=>({eligible:0,checked:0,hits:0,invested:0,paid:0,profit:0,excluded:0});
const combo=x=>typeof x==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(x)&&new Set(x.split('-')).size===3;
const money=n=>(n>=0?'+':'−')+Math.abs(n).toLocaleString('ja-JP')+'円';
const yen=n=>n.toLocaleString('ja-JP')+'円';
const validBets=bets=>Array.isArray(bets)&&bets.length>=4&&bets.length<=12&&
 bets.every(b=>b&&combo(b.combination)&&Number.isSafeInteger(b.virtual_yen)&&b.virtual_yen>=0&&b.virtual_yen%100===0)&&
 new Set(bets.map(b=>b.combination)).size===bets.length&&
 bets.reduce((s,b)=>s+b.virtual_yen,0)===50000;
function summary(doc,day){
 if(!doc||doc.event_date!==day||!doc.race_records||typeof doc.race_records!=='object'||Array.isArray(doc.race_records))
   throw Error('日付別の固定記録が不正です');
 const list=Object.entries(doc.race_records);
 if(list.length>288)throw Error('レース記録数が上限を超えています');
 const out=EMPTY();
 for(const [id,record] of list){
  if(!/^\\d{1,2}-([1-9]|1[0-2])$/.test(id)||!record||!Array.isArray(record.versions)||!record.versions.length)continue;
  const r=record.versions[record.versions.length-1];
  const cutoff=Date.parse(r?.cutoff_iso_jst),frozen=Date.parse(r?.frozen_at_utc);
  if(!r||typeof r.sha256!=='string'||! /^[a-f0-9]{64}$/i.test(r.sha256)||
     typeof r.cutoff_iso_jst!=='string'||!r.cutoff_iso_jst.startsWith(day+'T')||
     !/(\\+09:00)$/.test(r.cutoff_iso_jst)||
     !Number.isFinite(cutoff)||!Number.isFinite(frozen)||frozen>=cutoff||
     !validBets(r.bets)||r.venue!==record.venue||r.race!==record.race){out.excluded++;continue;}
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
let state={loading:false,ready:false,days:{},errors:{}};
let inflight=null;
async function load(force=false,fetcher=root.fetch?.bind(root)){
 if(inflight)return inflight;
 if(state.ready&&!force)return state;
 state={loading:true,ready:false,days:force?{}:state.days,errors:{}};
 inflight=(async()=>{
  for(const day of DAYS){
   try{
    if(typeof fetcher!=='function')throw Error('取得機能が利用できません');
    const response=await fetcher('./data/live/'+day+'.json',{cache:'no-store'});
    if(!response?.ok)throw Error('HTTP '+(response?.status??'接続失敗'));
    const doc=await response.json();
    state.days[day]=summary(doc,day);
   }catch(e){delete state.days[day];state.errors[day]=e?.message||'データを取得できません';}
  }
  state.loading=false;state.ready=true;
  return state;
 })().finally(()=>{inflight=null;});
 return inflight;
}
function status(){return state.loading?'loading':state.ready?'ready':'idle'}
function render(){
 const found=DAYS.filter(day=>state.days[day]);
 const combined=EMPTY();
 let rows='',running=0;
 for(const day of DAYS){
  const d=state.days[day];
  if(!d){rows+='<tr><th scope="row">'+day.slice(5).replace('-','/')+'</th><td colspan="5">未取得・累積に含めない</td></tr>';continue;}
  for(const k of ['eligible','checked','hits','invested','paid','profit'])combined[k]+=d[k];
  running+=d.profit;
  rows+='<tr><th scope="row">'+day.slice(5).replace('-','/')+'</th><td>'+d.checked+' / '+d.eligible+'R</td><td>'+d.hits+'R</td><td>'+yen(d.invested)+'</td><td>'+yen(d.paid)+'</td><td class="'+(d.profit>=0?'cum-plus':'cum-minus')+'">'+money(d.profit)+'</td></tr>';
 }
 const completed=found.length===DAYS.length;
 return '<section class="card card-pad cumulative-settlement" aria-label="10月22日と23日の累積仮想収支">'+
  '<div class="section-head"><div><h2 class="section-title">📈 10/22・10/23 累積収支</h2><p class="cum-subtitle">発走前固定の研究用買い目 × 公式確認済み払戻だけ</p></div>'+
  '<button type="button" class="btn btn-white" data-action="reload-cumulative-results" '+(state.loading?'disabled':'')+'>'+ (state.loading?'読み込み中…':'↻ 再集計')+'</button></div>'+
  (found.length?
   '<div class="cum-total"><span>'+(completed?'2日間の累積仮想収支':'取得済み日だけの暫定累積')+'</span><strong class="'+(running>=0?'cum-plus':'cum-minus')+'">'+money(running)+'</strong>'+
   '<small>公式照合 '+combined.checked+'R／対象固定 '+combined.eligible+'R · 的中 '+combined.hits+'R · 回収率 '+(combined.invested?(combined.paid/combined.invested*100).toFixed(1)+'%':'—')+'</small></div>':
   '<p class="notice">まだ集計できる日付別の公式照合記録がありません。</p>')+
  '<div class="cum-table-wrap"><table class="cum-table"><thead><tr><th>日付</th><th>公式照合</th><th>的中</th><th>仮想投資</th><th>仮想払戻</th><th>日別収支</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
  (state.loading?'<p class="help">22日・23日の固定記録を読み込んでいます…</p>':'')+
  (Object.keys(state.errors).length?'<p class="notice warn">未取得：'+Object.entries(state.errors).map(([day])=>day.slice(5).replace('-','/')+'分').join('、')+'。欠損日は0円として扱わず、累積から除外しています。</p>':'')+
  '<p class="help">日別GitHub固定記録の最新バージョン（1レース1予想）で集計。公式未確認・中止・返還・矛盾・不正データは集計から除外。手入力や未予想レースは算入しません。正式BUY収支ではなく、全研究予想の仮想収支です。現在日の数字は含めません。</p></section>';
}
root.BoatCumulative={summary,load,render,status,dates:DAYS.slice()};
})(typeof window==='undefined'?globalThis:window);
