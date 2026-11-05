/* BOAT LAB compact results inspection: read-only pure UI for frozen forecasts.
 * Every official result is verified by the existing app's officialFor() checks.
 * No user-visible draft is counted as an official hit or official payout.
 */
(function(global){
'use strict';
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
}[c]));
const yen=value=>Number(value||0).toLocaleString('ja-JP')+'円';
const number=value=>Number(value||0).toLocaleString('ja-JP');
const dateOf=(date,time)=>Date.parse(date+'T'+time+':00+09:00');
const validTime=(date,time)=>typeof date==='string'&&
 /^\d{4}-\d{2}-\d{2}$/.test(date)&&typeof time==='string'&&
 /^\d{2}:\d{2}$/.test(time);
const filterDefs=[
 {id:'recent',name:'直近の全レース'},
 {id:'hit',name:'的中'},
 {id:'miss',name:'不的中'},
 {id:'awaiting',name:'公式未取得'},
 {id:'verified',name:'公式照合済み'},
 {id:'issue',name:'要確認'}
];
function rows(races,ctx,nowMs=Date.now()){
 const date=ctx.date;
 return races.map(r=>{
   const t=validTime(date,r.cutoff_jst)?dateOf(date,r.cutoff_jst):NaN;
   const official=ctx.officialFor(r);
   const issue=ctx.resultIssue(r);
   const c=ctx.compute(r);
   const recorded=!!(c.record&&!official&&!issue);
   const status=issue?'issue':official?'verified':recorded?'draft':
     Number.isFinite(t)&&nowMs>=t?'awaiting':'upcoming';
   return {race:r,cutoffMs:t,official:!!official,issue,status,
     hit:!!(official&&c.hit),finish:official?.finish||c.record?.finish||null,
     payout100:official?.payout_per_100??c.record?.payout_per_100??null,
     virtualPayout:official?c.payout:null,
     virtualProfit:official?c.profit:null,
     stake:c.stake,hasForecast:Array.isArray(r.bets)&&r.bets.length>0};
 }).sort((a,b)=>(a.cutoffMs||Infinity)-(b.cutoffMs||Infinity));
}
function summary(rows){
 const done=rows.filter(x=>x.status==='verified');
 return {
   total:rows.length,official:done.length,
   hit:done.filter(x=>x.hit).length,
   miss:done.filter(x=>!x.hit).length,
   awaiting:rows.filter(x=>x.status==='awaiting').length,
   issues:rows.filter(x=>x.status==='issue').length,
   upcoming:rows.filter(x=>x.status==='upcoming').length,
   drafts:rows.filter(x=>x.status==='draft').length
 };
}
function sortedFor(board,filter){
 const past=board.filter(x=>x.status!=='upcoming').sort((a,b)=>b.cutoffMs-a.cutoffMs);
 const upcoming=board.filter(x=>x.status==='upcoming').sort((a,b)=>a.cutoffMs-b.cutoffMs);
 switch(filter){
   case 'awaiting':return past.filter(x=>x.status==='awaiting');
   case 'verified':return past.filter(x=>x.status==='verified');
   case 'hit':return past.filter(x=>x.status==='verified'&&x.hit);
   case 'miss':return past.filter(x=>x.status==='verified'&&!x.hit);
   case 'issue':return past.filter(x=>x.status==='issue');
   default:return past.concat(upcoming);
 }
}
function label(x){
 if(x.status==='verified')return x.hit?'公式的中':'公式不的中';
 if(x.status==='issue')return '要確認';
 if(x.status==='draft')return '仮入力・未確定';
 if(x.status==='awaiting')return '公式未取得';
 return '締切前';
}
function financials(board){
 const done=board.filter(x=>x.status==='verified');
 const invested=done.reduce((sum,x)=>sum+(Number.isFinite(x.stake)&&x.stake>=0?x.stake:0),0);
 const paid=done.reduce((sum,x)=>sum+(Number.isFinite(x.virtualPayout)&&x.virtualPayout>=0?x.virtualPayout:0),0);
 return {invested,paid,profit:paid-invested,returnRate:invested>0?paid/invested:null};
}
function signedYen(value){return (value>=0?'+':'−')+yen(Math.abs(value));}
function moneyCell(cls,labelText,value){
 return '<span class="'+cls+'"><span>'+esc(labelText)+'</span><b>'+esc(value)+'</b></span>';
}
function render(races,ctx,opt={}){
 const board=rows(races,ctx,opt.nowMs??Date.now());
 const stats=summary(board),finance=financials(board);
 const filter=filterDefs.some(x=>x.id===opt.filter)?opt.filter:'recent';
 const selected=board.find(x=>x.race.venue===opt.venue&&x.race.race===Number(opt.race));
 const filtered=sortedFor(board,filter);
 const maxRows=opt.expanded?filtered.length:Math.min(18,filtered.length);
 const display=filtered.slice(0,maxRows);
 const next=board.filter(x=>x.status==='awaiting').sort((a,b)=>b.cutoffMs-a.cutoffMs)[0];
 const stamp=ctx.officialUpdatedAt||null;
 const latest=stamp?new Date(stamp):null;
 const freshness=latest&&!Number.isNaN(latest.getTime())?latest.toLocaleString('ja-JP',{
     timeZone:'Asia/Tokyo',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'未取得';
 const profitClass=finance.profit>=0?'is-positive':'is-negative';
 const isFinancial=stats.official>0&&finance.invested>0;
 let html='<section class="card card-pad quick-results quick-results-v2" aria-label="結果照合と仮想収支の一覧">'+
   '<div class="quick-results-heading"><div><span class="quick-results-kicker">⚡ ワンタップ結果照合</span>'+
   '<h2>照合・精算 <span>（結果一覧）</span></h2>'+
   '<p>的中レースを強調表示。公式照合済みの保存予想だけで仮想収支を集計します。</p></div>'+
   (next?'<button type="button" class="btn btn-soft" data-result-next="'+esc(next.race.venue)+'|'+next.race.race+
      '">直近の公式未取得：'+esc(next.race.venue)+' '+next.race.race+'R</button>':'')+
   '</div><div class="quick-results-overview">'+
   '<div class="quick-results-summary" aria-label="公式結果の照合サマリー">'+
   '<div class="quick-summary-cell"><span>公式照合済み</span><strong>'+number(stats.official)+'<small>件</small></strong></div>'+
   '<div class="quick-summary-cell quick-summary-hit"><span>✓ 的中</span><strong>'+number(stats.hit)+'<small>件</small></strong></div>'+
   '<div class="quick-summary-cell quick-summary-miss"><span>不的中</span><strong>'+number(stats.miss)+'<small>件</small></strong></div>'+
   '</div><div class="quick-results-finance '+(isFinancial?profitClass:'is-pending')+'" aria-label="公式照合済みの仮想収支と回収率">'+
   '<div class="quick-results-finance-main"><span>仮想収支</span><strong>'+(isFinancial?signedYen(finance.profit):'—')+'</strong></div>'+
   '<div class="quick-results-finance-rate"><span>仮想回収率</span><strong>'+
   (isFinancial?(finance.returnRate*100).toFixed(1)+'%':'—')+'</strong></div></div></div>'+
   '<p class="quick-results-fresh">公式照合データ確認：'+esc(freshness)+
   ' JST ／ 公式未取得 '+number(stats.awaiting)+'件 ／ 要確認 '+number(stats.issues)+'件 ／ 仮入力 '+
   number(stats.drafts)+'件 ／ 締切前 '+number(stats.upcoming)+'件。<b>未取得と仮入力は成績に含めません。</b></p>'+
   '<div class="quick-results-filters" role="group" aria-label="結果を絞り込む">'+
   filterDefs.map(x=>'<button type="button" data-result-filter="'+x.id+
       '" aria-pressed="'+String(x.id===filter)+'" class="'+(x.id===filter?'active':'')+'">'+
     esc(x.name)+'</button>').join('')+'</div>'+
   '<div class="quick-results-grid">';
 for(const x of display){
   const r=x.race,active=selected===x,verified=x.status==='verified';
   const statusCls=verified?(x.hit?'is-hit':'is-miss'):'is-'+x.status;
   const result=verified?
     '<span class="quick-results-result-row">'+
     '<span class="quick-results-result-label">結果</span>'+
     '<strong class="quick-results-combo">'+esc(x.finish)+'</strong>'+
     moneyCell('quick-results-value','100円払戻',yen(x.payout100))+
     moneyCell('quick-results-value','仮想投資',yen(x.stake))+
     moneyCell('quick-results-profit '+(x.virtualProfit>=0?'is-positive':'is-negative'),'仮想収支',signedYen(x.virtualProfit))+
     '</span>':
     x.status==='draft'?
       '<span class="quick-results-unresolved"><strong>仮入力：'+esc(x.finish)+'</strong><span>公式未確認・収支は集計外</span></span>':
     x.status==='issue'?
       '<span class="quick-results-unresolved"><strong>要確認</strong><span>公式不一致・返還等は集計外</span></span>':
       '<span class="quick-results-unresolved"><strong>'+
         esc(x.status==='upcoming'?'発走前':'未公表')+
         '</strong><span>未確定のため回収率に未算入</span></span>';
   html+='<button type="button" class="quick-results-race '+statusCls+' '+x.status+
    (active?' active':'')+
    '" data-result-quick="'+esc(r.venue)+'|'+r.race+'" aria-pressed="'+String(active)+'">'+
    '<span class="quick-results-racehead"><b>'+esc(r.venue)+' '+r.race+'R</b>'+
    '<small>'+esc(r.cutoff_jst)+' 締切</small></span>'+
    '<span class="quick-results-racestatus">'+(verified?(x.hit?'✓ ':'× '):'')+esc(label(x))+'</span>'+
    '<span class="quick-results-forecast">固定予想（上位2点）：'+
       esc((r.bets||[]).slice(0,2).map(b=>b.combination).join(' / '))+'</span>'+
    '<span class="quick-results-outcome">'+result+'</span></button>';
 }
 html+='</div>';
 if(!display.length)html+='<p class="muted text-sm">この区分のレースはありません。</p>';
 if(maxRows<filtered.length)html+='<button type="button" class="btn btn-soft quick-results-more" data-result-more="true">残り'+(filtered.length-maxRows)+'Rも表示</button>';
 else if(opt.expanded&&filtered.length>18)html+='<button type="button" class="btn btn-soft quick-results-more" data-result-more="false">18R表示に戻す</button>';
 if(selected){
   const x=selected;
   const explanation=x.status==='verified'?
     ('公式着順 '+x.finish+' ／ 3連単払戻 '+yen(x.payout100)+'/100円 ／ '+(x.hit?'🎯 的中':'不的中')+
      ' ／ 仮想払戻 '+yen(x.virtualPayout)+' ／ 仮想収支 '+signedYen(x.virtualProfit)):
     x.status==='draft'?'仮入力 '+x.finish+'。公式結果としては未計上':
     x.status==='issue'?'公式側の返還・補正・データ不一致を要確認。仮想収支は計上しません':
     x.status==='awaiting'?'締切後ですが、検証可能な公式払戻がまだ届いていません':'締切前のため、結果は未確定';
   html+='<div class="quick-results-selected" aria-live="polite"><b>選択中：'+
     esc(x.race.venue)+' '+x.race.race+'R</b><p>'+esc(explanation)+'</p></div>';
 }
 html+='<p class="quick-results-foot">収支・回収率は公式照合済みの仮想予想のみ。正式BUY成績とは別集計です。「結果を更新」は公開済み結果の再取得で、反映時刻を保証しません。発走前固定買い目は変更しません。</p></section>';
 return html;
}
global.BoatResultQuickboard={rows,summary,financials,sortedFor,render};
})(typeof window!=='undefined'?window:globalThis);
