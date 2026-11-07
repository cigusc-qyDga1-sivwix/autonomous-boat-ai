const assert=require('node:assert/strict');
require('../cumulative-settlement.js');
const api=globalThis.BoatCumulative;
const day='2026-11-07';
const resultURL='https://www.boatrace.jp/owpc/pc/race/raceresult?rno=7&jcd=11&hd=20261107';
const payURL='https://www.boatrace.jp/owpc/pc/race/pay?hd=20261107';
const bets=[
 {combination:'5-2-3',virtual_yen:10000},
 {combination:'4-1-2',virtual_yen:20000},
 {combination:'1-2-3',virtual_yen:10000},
 {combination:'6-5-2',virtual_yen:10000}
];
function ledger(){
 return {event_date:day,race_records:{'11-7':{
  venue:'びわこ',race:7,official_review:'refund',versions:[{
   venue:'びわこ',race:7,bets,
   cutoff_iso_jst:day+'T13:16:00+09:00',
   frozen_at_utc:day+'T03:00:00Z',sha256:'a'.repeat(64)
  }]
 }}};
}
const official={
 finish:'5-2-3',payout_per_100:3760,
 refunded_boats:[4],refund_reasons:{4:'F'},
 refund_source_url:resultURL,void_trifecta:false,
 verified:true,source:'boatrace_official_pay'
};
const report={
 date:day,status:'verified_by_server_fetch',
 evidence_type:'official_boatrace_pay_snapshot',
 source_url:payURL,retrieved_at_utc:'2026-11-07T05:10:00Z',
 results:{'11-7':official},reviews:{},cancellations:{}
};
const l=ledger();
assert.equal(api.summary(l,day).checked,0,'bare 返 review is not a loss');
assert.equal(api.overlayVerifiedPays(l,report,day),1);
const s=api.summary(l,day);
assert.equal(s.checked,1);
assert.equal(s.hits,1);
assert.equal(s.refundRaces,1);
assert.equal(s.voids,0);
assert.equal(s.refunded,20000);
assert.equal(s.paid,396000);
assert.equal(s.profit,346000);
assert.equal(api.overlayVerifiedPays(l,report,day),0,'no duplicate refund');
const voidRecord=ledger();
delete voidRecord.race_records['11-7'].official_review;
voidRecord.race_records['11-7'].official_pay={
 ...official,finish:null,payout_per_100:0,void_trifecta:true
};
const v=api.summary(voidRecord,day);
assert.equal(v.voids,1);
assert.equal(v.hits,0);
assert.equal(v.refunded,50000);
assert.equal(v.profit,0);
const noProof=ledger();
delete noProof.race_records['11-7'].official_review;
noProof.race_records['11-7'].official_pay={...official,refund_source_url:'https://fake.invalid'};
assert.equal(api.summary(noProof,day).checked,0);
const badFinish=ledger();
delete badFinish.race_records['11-7'].official_review;
badFinish.race_records['11-7'].official_pay={...official,finish:'4-2-3'};
assert.equal(api.summary(badFinish,day).checked,0);
console.log('BOAT LAB official F/scratch refunds cumulative: PASS');
