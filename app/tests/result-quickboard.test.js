const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const context={window:{},Date,Number,Intl,Math};
vm.runInNewContext(fs.readFileSync('app/result-quickboard.js','utf8'),context);
const Q=context.window.BoatResultQuickboard;
const date='2026-10-23',at=Date.parse(date+'T15:04:00+09:00');
const raw=[
 [1,'鳴門','10:15','3-2-1'],[2,'鳴門','11:15','1-2-3'],
 [3,'唐津','12:10','2-1-3'],[4,'唐津','13:10','1-3-2'],
 [5,'唐津','14:30','3-1-2'],[6,'唐津','16:00','1-2-3']
].map(([race,venue,cutoff_jst,combination])=>({
 race,venue,cutoff_jst,classification:'WATCH',sha256:'abc-'+race,
 bets:[{combination,virtual_yen:50000}]
}));
const original=JSON.stringify(raw);
const verified=new Map([[1,{finish:'3-2-1',payout_per_100:2300,source:'boatrace_official_pay',verified:true}],
 [2,{finish:'2-1-3',payout_per_100:4100,source:'boatrace_official_pay',verified:true}]]);
const draft={finish:'2-1-3',payout_per_100:4500,source:'manual'};
const ctx={
 date,officialUpdatedAt:'2026-10-23T05:58:00Z',
 officialFor:r=>verified.get(r.race)||null,
 resultIssue:r=>r.race===4?{reason:'result conflict',status:'conflict'}:null,
 compute:r=>{
   const record=verified.get(r.race)||(r.race===3?draft:null);
   const bet=r.bets[0],hit=!!record&&bet.combination===record.finish;
   const payout=record?(hit?bet.virtual_yen*record.payout_per_100/100:0):null;
   return {record,hit,stake:bet.virtual_yen,payout,profit:record?payout-bet.virtual_yen:null};
 }
};
const board=Q.rows(raw,ctx,at);
const c=Q.summary(board);
assert.deepEqual(JSON.parse(JSON.stringify(c)),{
 total:6,official:2,hit:1,miss:1,awaiting:1,issues:1,upcoming:1,drafts:1
});
assert.equal(board.find(r=>r.race.race===1).virtualPayout,1150000);
assert.equal(board.find(r=>r.race.race===2).virtualProfit,-50000);
assert.equal(board.find(r=>r.race.race===3).official,false);
assert.equal(board.find(r=>r.race.race===5).status,'awaiting');
assert.equal(board.find(r=>r.race.race===6).status,'upcoming');
const html=Q.render(raw,ctx,{nowMs:at,venue:'鳴門',race:1,filter:'recent'});
assert.match(html,/ワンタップ結果照合/);
assert.match(html,/1,150,000円/);
assert.match(html,/公式未取得は不的中として数えません/);
assert.match(html,/公式不的中/);
assert.match(html,/仮入力・未確定/);
assert.match(html,/data-result-quick="唐津\|5"/);
assert.match(html,/data-result-next="唐津\|5"/);
assert.match(html,/aria-pressed="true"/);
assert.match(html,/100円払戻/);
const pending=Q.render(raw,ctx,{nowMs:at,filter:'awaiting'});
assert.match(pending,/唐津 5R/);
assert.doesNotMatch(pending,/鳴門 1R/);
const hits=Q.render(raw,ctx,{nowMs:at,filter:'hit'});
assert.match(hits,/鳴門 1R/);
assert.doesNotMatch(hits,/鳴門 2R/);
const issues=Q.render(raw,ctx,{nowMs:at,filter:'issue'});
assert.match(issues,/唐津 4R/);
assert.doesNotMatch(issues,/data-result-quick="唐津\\|5"/);
assert.equal(JSON.stringify(raw),original,'rendering must not change immutable forecast records');
console.log('BOAT LAB quick official result status, filter and payout rendering: PASS');
