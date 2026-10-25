const assert=require('node:assert/strict');
require('../cumulative-settlement.js');
const api=globalThis.BoatCumulative;
const bets=[
 {combination:'1-2-3',virtual_yen:10000},
 {combination:'1-3-2',virtual_yen:10000},
 {combination:'2-1-3',virtual_yen:10000},
 {combination:'2-3-1',virtual_yen:10000},
 {combination:'3-1-2',virtual_yen:10000}
];
function rec(day,n,finish,payout){
 return {venue:'鳴門',race:n,versions:[{
  venue:'鳴門',race:n,sha256:'a'.repeat(64),bets,
  cutoff_iso_jst:day+'T08:35:00+09:00',
  frozen_at_utc:new Date(Date.parse(day+'T00:00:00Z')-3600000).toISOString(),
  classification:'WATCH'
 }],official_pay:finish?{source:'boatrace_official_pay',verified:true,
   finish,payout_per_100:payout}:null};
}
function ledger(day,races){return {event_date:day,race_records:races}}
const day22='2026-10-22',day23='2026-10-23';
const l22=ledger(day22,{
 '14-1':rec(day22,1,'1-2-3',1000),
 '14-2':rec(day22,2,'4-5-6',720),
 '14-3':rec(day22,3,null,null)
});
const l23=ledger(day23,{'14-1':rec(day23,1,'4-5-6',720)});
const sum22=api.summary(l22,day22);
assert.equal(sum22.eligible,3);
assert.equal(sum22.checked,2);
assert.equal(sum22.hits,1);
assert.equal(sum22.invested,100000);
assert.equal(sum22.paid,100000);
assert.equal(sum22.profit,0);
assert.equal(api.summary(l23,day23).profit,-50000);
assert.throws(()=>api.summary(l22,day23),/不正/);
const altered=structuredClone(l22);
altered.race_records['14-1'].versions[0].frozen_at_utc=day22+'T01:00:00Z';
assert.equal(api.summary(altered,day22).checked,1,'late snapshots are excluded');
const conflict=structuredClone(l22);
conflict.race_records['14-1'].official_conflict={reason:'corrected'};
assert.equal(api.summary(conflict,day22).checked,1,'conflicts are quarantined');
const manual=structuredClone(l22);
manual.race_records['14-1'].official_pay.source='manual';
assert.equal(api.summary(manual,day22).checked,1,'manual data never contributes');
const mismatch=structuredClone(l22);
mismatch.race_records['14-1'].official_pay.snapshot_sha256='b'.repeat(64);
assert.equal(api.summary(mismatch,day22).checked,1,'snapshot mismatch never contributes');
(async()=>{
 const docs={[day22]:l22,[day23]:l23};
 await api.load(false,async url=>({ok:true,json:async()=>docs[url.match(/\d{4}-\d\d-\d\d/)[0]]}),new Date('2026-10-23T10:00:00+09:00'));
 const html=api.render();
 assert.match(html,/10\/22〜10\/23 累積収支/);
 assert.match(html,/−50,000円/);
 assert.match(html,/公式照合 3R/);
 assert.match(html,/150,000円/);
 assert.match(html,/100,000円/);
 assert.equal(api.status(),'ready');
 await api.load(true,async url=>url.includes(day23)?{ok:false,status:404}:{ok:true,json:async()=>l22},new Date('2026-10-23T10:00:00+09:00'));
 const partial=api.render();
 assert.match(partial,/取得済み日だけの暫定累積/);
 assert.match(partial,/未取得・累積に含めない/);
 assert.doesNotMatch(partial,/−50,000円/);

 const day24='2026-10-24',day25='2026-10-25';
 const l24=ledger(day24,{'14-1':rec(day24,1,'1-2-3',500)});
 const l25=ledger(day25,{'14-1':rec(day25,1,null,null)});
 assert.deepEqual(api.daysThrough(new Date('2026-10-24T15:15:00Z')),
  [day22,day23,day24,day25],'JST rollover includes today');
 const seen=[];
 await api.load(true,async url=>{
  const date=url.match(/\d{4}-\d\d-\d\d/)[0];seen.push(date);
  return {ok:true,json:async()=>({[day22]:l22,[day23]:l23,[day24]:l24,[day25]:l25})[date]};
 },new Date('2026-10-25T07:30:00+09:00'));
 assert.deepEqual(seen,[day22,day23,day24,day25]);
 const today=api.render();
 assert.match(today,/10\/22〜10\/25 累積収支/);
 assert.match(today,/10\/24/);assert.match(today,/10\/25/);
 assert.match(today,/公式照合 4R/);
 assert.match(today,/200,000円/,'only verified races count as invested');
 await api.load(true,async url=>url.includes(day24)?{ok:false,status:404}:
  {ok:true,json:async()=>({[day22]:l22,[day23]:l23,[day25]:l25})[url.match(/\d{4}-\d\d-\d\d/)[0]]},
  new Date('2026-10-25T07:45:00+09:00'));
 assert.match(api.render(),/未取得・累積に含めない/);

 // Same-day daily ledger is stale, but server-verified official pay snapshot
 // is newer: only legitimate matching fixed bets are counted once.
 const l25stale=ledger(day25,{'14-1':rec(day25,1,null,null)});
 const verifiedPay={
  date:day25,status:'verified_by_server_fetch',
  evidence_type:'official_boatrace_pay_snapshot',
  source_url:'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261025',
  retrieved_at_utc:'2026-10-25T07:54:53Z',
  results:{'14-1':{finish:'1-2-3',payout_per_100:1000}}
 };
 const newCount=api.overlayVerifiedPays(l25stale,verifiedPay,day25);
 assert.equal(newCount,1);
 assert.equal(api.summary(l25stale,day25).checked,1);
 assert.equal(api.summary(l25stale,day25).paid,100000);
 assert.equal(api.overlayVerifiedPays(l25stale,verifiedPay,day25),0,'no double count');
 const changed={...verifiedPay,results:{'14-1':{finish:'4-5-6',payout_per_100:3000}}};
 assert.equal(api.overlayVerifiedPays(l25stale,changed,day25),0,'conflicts cannot overwrite official results');
 const badSource={...verifiedPay,source_url:'https://fake.example/race/pay'};
 assert.equal(api.overlayVerifiedPays(ledger(day25,{'14-1':rec(day25,1,null,null)}),badSource,day25),0);
 const fetched=[];
 await api.load(true,async url=>{
  fetched.push(url);
  if(url.includes('official-pay'))return {ok:true,json:async()=>verifiedPay};
  const d=url.match(/\d{4}-\d\d-\d\d/)[0];
  return {ok:true,json:async()=>({[day22]:l22,[day23]:l23,[day24]:l24,
   [day25]:ledger(day25,{'14-1':rec(day25,1,null,null)})})[d]};
 },new Date('2026-10-25T17:09:00+09:00'));
 assert.equal(fetched.filter(url=>url.includes('official-pay')).length,1);
 assert.match(api.render(),/10\/25/);
 assert.match(api.render(),/公式照合 5R/,'today direct pay must enter cumulative');
 console.log('BOAT LAB dynamic Oct22-to-today verified cumulative settlement: PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
