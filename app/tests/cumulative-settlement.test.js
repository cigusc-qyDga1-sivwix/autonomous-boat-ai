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
// Settlement must honor the policy frozen with the original prediction.
const all=[];
for(let a=1;a<=6;a++)for(let b=1;b<=6;b++)for(let c=1;c<=6;c++)
 if(new Set([a,b,c]).size===3)all.push(`${a}-${b}-${c}`);
function widened(day,count,model){
 const record=rec(day,1,'1-2-3',1000);
 const snapshot=record.versions[0];
 if(model)snapshot.model_version=model;
 const base=Math.floor(500/count),extra=500-base*count;
 snapshot.bets=all.slice(0,count).map((combination,i)=>
  ({combination,virtual_yen:100*(base+Number(i<extra))}));
 return ledger(day,{'14-1':record});
}
const pointFree='four-factor-v1.5-point-free-untrained';
for(const count of [1,20,120]){
 const doc=widened('2026-10-28',count,pointFree),before=JSON.stringify(doc);
 const s=api.summary(doc,'2026-10-28');
 assert.equal(s.checked,1,'point-free predictions must remain in historical totals');
 assert.equal(s.invested,50000);
 assert.equal(s.paid,doc.race_records['14-1'].versions[0].bets[0].virtual_yen*10);
 assert.equal(JSON.stringify(doc),before,'settlement never rewrites historical tickets');
}
assert.equal(api.summary(widened('2026-10-28',20),'2026-10-28').checked,0,
 'point-free exception requires its recorded model');
assert.equal(api.summary(widened('2026-10-27',20),'2026-10-27').checked,0,
 'legacy bounds stay in force for old predictions');
assert.equal(api.summary(widened('2026-10-29',20),'2026-10-29').checked,1,
 '20-point predictions are eligible after the recorded rollout');
assert.equal(api.summary(widened('2026-10-29',21),'2026-10-29').checked,0,
 'current bounds do not permit arbitrary wider predictions');
(async()=>{
 const day04='2026-11-04',day05='2026-11-05';
 const l04=ledger(day04,{
  '14-1':rec(day04,1,'1-2-3',1000),
  '14-2':rec(day04,2,'4-5-6',720),
  '14-3':rec(day04,3,null,null)
 });
 const l05=ledger(day05,{'14-1':rec(day05,1,'4-5-6',720)});
 assert.deepEqual(api.daysThrough(new Date('2026-11-03T23:00:00+09:00')),[],
  'dates before November 4 are excluded from the reporting period');
 const docs={[day04]:l04,[day05]:l05};
 await api.load(false,async url=>({ok:true,json:async()=>docs[url.match(/\d{4}-\d\d-\d\d/)[0]]}),new Date('2026-11-05T10:00:00+09:00'));
 const html=api.render();
 assert.match(html,/11\/04〜11\/05 累積収支/);
 assert.match(html,/−50,000円/);
 assert.match(html,/公式照合 3R/);
 assert.match(html,/150,000円/);
 assert.match(html,/100,000円/);
 assert.equal(api.status(),'ready');
 await api.load(true,async url=>url.includes(day05)?{ok:false,status:404}:{ok:true,json:async()=>l04},new Date('2026-11-05T10:00:00+09:00'));
 const partial=api.render();
 assert.match(partial,/取得済み日だけの暫定累積/);
 assert.match(partial,/未取得・累積に含めない/);
 assert.doesNotMatch(partial,/−50,000円/);

 const day06='2026-11-06',day07='2026-11-07';
 const l06=ledger(day06,{'14-1':rec(day06,1,'1-2-3',500)});
 const l07=ledger(day07,{'14-1':rec(day07,1,null,null)});
 assert.deepEqual(api.daysThrough(new Date('2026-11-06T15:15:00Z')),
  [day04,day05,day06,day07],'JST rollover includes today');
 const seen=[];
 await api.load(true,async url=>{
  const date=url.match(/\d{4}-\d\d-\d\d/)[0];seen.push(date);
  return {ok:true,json:async()=>({[day04]:l04,[day05]:l05,[day06]:l06,[day07]:l07})[date]};
 },new Date('2026-11-07T07:30:00+09:00'));
 assert.deepEqual(seen,[day04,day05,day06,day07,day07], 'latest-day verified-pay endpoint is also checked');
 const today=api.render();
 assert.match(today,/11\/04〜11\/07 累積収支/);
 assert.match(today,/11\/06/);assert.match(today,/11\/07/);
 assert.match(today,/公式照合 4R/);
 assert.match(today,/200,000円/,'only verified races count as invested');
 await api.load(true,async url=>url.includes(day06)?{ok:false,status:404}:
  {ok:true,json:async()=>({[day04]:l04,[day05]:l05,[day07]:l07})[url.match(/\d{4}-\d\d-\d\d/)[0]]},
  new Date('2026-11-07T07:45:00+09:00'));
 assert.match(api.render(),/未取得・累積に含めない/);

 // Same-day daily ledger is stale, but server-verified official pay snapshot
 // is newer: only legitimate matching fixed bets are counted once.
 const l25stale=ledger(day07,{'14-1':rec(day07,1,null,null)});
 const verifiedPay={
  date:day07,status:'verified_by_server_fetch',
  evidence_type:'official_boatrace_pay_snapshot',
  source_url:'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261107',
  retrieved_at_utc:'2026-11-07T07:54:53Z',
  results:{'14-1':{finish:'1-2-3',payout_per_100:1000}}
 };
 const newCount=api.overlayVerifiedPays(l25stale,verifiedPay,day07);
 assert.equal(newCount,1);
 assert.equal(api.summary(l25stale,day07).checked,1);
 assert.equal(api.summary(l25stale,day07).paid,100000);
 assert.equal(api.overlayVerifiedPays(l25stale,verifiedPay,day07),0,'no double count');
 const changed={...verifiedPay,results:{'14-1':{finish:'4-5-6',payout_per_100:3000}}};
 assert.equal(api.overlayVerifiedPays(l25stale,changed,day07),0,'conflicts cannot overwrite official results');
 const badSource={...verifiedPay,source_url:'https://fake.example/race/pay'};
 assert.equal(api.overlayVerifiedPays(ledger(day07,{'14-1':rec(day07,1,null,null)}),badSource,day07),0);
 const fetched=[];
 await api.load(true,async url=>{
  fetched.push(url);
  if(url.includes('official-pay'))return {ok:true,json:async()=>verifiedPay};
  const d=url.match(/\d{4}-\d\d-\d\d/)[0];
  return {ok:true,json:async()=>({[day04]:l04,[day05]:l05,[day06]:l06,
   [day07]:ledger(day07,{'14-1':rec(day07,1,null,null)})})[d]};
 },new Date('2026-11-07T17:09:00+09:00'));
 assert.equal(fetched.filter(url=>url.includes('official-pay')).length,1);
 assert.match(api.render(),/11\/07/);
 assert.match(api.render(),/公式照合 5R/,'today direct pay must enter cumulative');
 console.log('BOAT LAB dynamic Nov04-to-today verified cumulative settlement: PASS');
})().catch(err=>{console.error(err);process.exitCode=1});

