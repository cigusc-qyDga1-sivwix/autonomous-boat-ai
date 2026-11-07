'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const root={};vm.runInNewContext(fs.readFileSync('app/official-direct-refresh.js','utf8'),{window:root,Date,Number});
const api=root.BoatOfficialDirect;
const day='2026-10-25',sha='a'.repeat(64);
const races=[
 {venue:'児島',race:1,sha256:sha,cutoff_jst:'10:00',
  bets:[{combination:'1-2-3',virtual_yen:50000}]},
 {venue:'児島',race:2,sha256:'b'.repeat(64),cutoff_jst:'18:00'}
];
const doc=()=>{
 return {date:day,status:'verified_by_server_fetch',
   evidence_type:'official_boatrace_pay_snapshot',
   source_url:'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261025',
   retrieved_at_utc:'2026-10-25T06:30:00+00:00',
   results:{'16-1':{finish:'1-2-3',payout_per_100:790},
            '16-2':{finish:'4-2-3',payout_per_100:1800}},
   reviews:{},cancellations:{},conflicts:{}};
};
const late=new Date('2026-10-25T16:35:00+09:00');
const first=api.merge(doc(),day,races,{}, {}, late);
assert.equal(first.available,true);
assert.equal(first.added,1,'future cutoff must not appear settled');
assert.equal(first.results[day+'|児島|1'].finish,'1-2-3');
assert.equal(first.results[day+'|児島|1'].snapshot_sha256,sha);
assert.equal(first.results[day+'|児島|2'],undefined);
assert.equal(api.merge(doc(),day,races,first.results,first.alerts,late).added,0,
 'repeat must not double count');
const allFinished=api.merge(doc(),day,races,{}, {},new Date('2026-10-25T19:00:00+09:00'));
assert.equal(allFinished.added,2);
const previous=JSON.parse(JSON.stringify(first.results));
const changed=doc();changed.results['16-1'].finish='2-1-3';
const conflict=api.merge(changed,day,races,previous,{},late);
assert.equal(conflict.added,0);
assert.equal(conflict.conflicts,1);
assert.match(conflict.alerts[day+'|児島|1'].reason,/一致しません/);
assert.equal(previous[day+'|児島|1'].finish,'1-2-3','no existing data mutation');
const hold=doc();hold.cancellations['16-1']={reason:'中止'};
assert.equal(api.merge(hold,day,races,{}, {},late).added,0,'cancelled race must not settle');
assert.ok(api.merge(hold,day,races,{}, {},late).alerts[day+'|児島|1']);
for(const [field,value] of [
 ['status','not_verified'],['date','2026-10-24'],
 ['source_url','https://example.org/incorrect-source']]){
 const bad=doc();bad[field]=value;
 assert.throws(()=>api.merge(bad,day,races,{}, {},late),/検証できません/);
}
const wrong=doc();wrong.results['16-1'].payout_per_100=999;
assert.equal(api.merge(wrong,day,races,{}, {},late).added,0);
const ref=doc();ref.results['16-1']={
 finish:'1-2-3',payout_per_100:790,
 refunded_boats:[4],refund_reasons:{4:'F'},void_trifecta:false,
 refund_source_url:'https://www.boatrace.jp/owpc/pc/race/raceresult?rno=1&jcd=16&hd=20261025'
};
const refunded=api.merge(ref,day,races,{},{
 [day+'|児島|1']:{status:'review',reason:'返還待ち'}
},late);
assert.equal(refunded.added,1,'verified refund resolves provisional review');
assert.equal(refunded.results[day+'|児島|1'].refunded_boats[0],4);
assert.equal(refunded.alerts[day+'|児島|1'],undefined);
const voidRecord=doc();voidRecord.results['16-1']={
 ...ref.results['16-1'],finish:null,payout_per_100:0,void_trifecta:true
};
assert.equal(api.merge(voidRecord,day,races,{}, {},late).results[day+'|児島|1'].void_trifecta,true);
const invalidReturn=doc();
invalidReturn.results['16-1']={...ref.results['16-1'],refund_source_url:'https://wrong.invalid'};
assert.equal(api.merge(invalidReturn,day,races,{}, {},late).added,0);
const source=JSON.stringify(races);
api.merge(doc(),day,races,{}, {},late);
assert.equal(JSON.stringify(races),source,'never alter bets, SHA or race input');
let call;
(async()=>{
 const fetched=await api.refresh(day,races,{}, {},async(url,opts)=>{
  call={url,opts};return {ok:true,json:async()=>doc()};
 },late);
 assert.equal(fetched.added,1);
 assert.match(call.url,/official-pay\/2026-10-25\.json\?refresh=/);
 assert.equal(call.opts.cache,'no-store');
 console.log('BOAT LAB independent verified official-pay browser refresh: PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
