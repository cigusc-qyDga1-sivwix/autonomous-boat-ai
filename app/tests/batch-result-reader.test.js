const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const day='2026-10-22';
const races=[];
for(const venue of ['大村','住之江'])for(let race=1;race<=12;race++)
  races.push({venue,race,sha256:venue+'-'+race,
    frozen_at_utc:'2026-10-22T04:00:00+00:00',cutoff_jst:'16:00',
    bets:[{combination:'1-2-3',virtual_yen:50000}]});
const ctx={date:day,races,officialResults:{},alerts:{}};
let payload=null,requests=[];
const window={BoatResultReader:{parseOfficialUrl(raw){
  const url=new URL(raw);
  if(url.hostname!=='www.boatrace.jp' ||url.pathname!=='/owpc/pc/race/pay')
    throw Error('公式の払戻URLを貼ってね');
  const hd=url.searchParams.get('hd');
  if(!/^\d{8}$/.test(hd))throw Error('URLに日付がありません');
  return {date:hd.slice(0,4)+'-'+hd.slice(4,6)+'-'+hd.slice(6),url:raw,type:'pay'};
}}};
const fetch=async(url,opts)=>{
  requests.push({url,opts});
  if(!payload)return {ok:false};
  return {ok:true,json:async()=>payload};
};
const env=vm.createContext({window,fetch,URL,console,Date});
vm.runInContext(fs.readFileSync('app/batch-result-reader.js','utf8'),env);
const R=window.BoatBatchReader;
const ocr=['大村'];
for(let n=1;n<=12;n++)ocr.push(n+'R 1-2-3 ¥'+(1200+10*n).toLocaleString('ja-JP'));
const parsed=R.parseLineRows(ocr.join('\n'),ctx,'');
assert.equal(parsed.rows.length,12);
assert.equal(parsed.rows[0].venue,'大村');
assert.equal(parsed.rows[0].finish,'1-2-3');
assert.equal(parsed.rows[0].payout_per_100,1210);
assert.equal(parsed.rows[11].race,12);
assert.equal(R.parseLineRows('住之江\n1R 3-1-2 ¥2,640\n2R 2-1-3 ¥1,310',ctx,'').rows.length,2);
const differentDay=R.parseLineRows('2026/10/21\n大村\n1R 1-2-3 ¥1,230',ctx,'');
assert.equal(differentDay.rows.length,0);
const refund=R.parseLineRows('大村\n1R 1-2-3 ¥1,230 返還',ctx,'');
assert.match(refund.rows[0].review,/返還/);
const ambiguous=R.parseLineRows('大村\n1R 1-2-3 ¥1,230 2-1-3 ¥2,340',ctx,'');
assert.match(ambiguous.rows[0].review,/複数/);
const noVenue=R.parseLineRows('1R 1-2-3 ¥1,230\n2R 2-1-3 ¥1,450',ctx,'大村');
assert.equal(noVenue.rows.length,2);
const multi=R.parseLineRows('大村 住之江\n1R 1-2-3 ¥1,230',ctx,'');
assert.equal(multi.rows.length,0,'multi-venue heading must never guess a single venue');

function official(){
  const results={};
  for(const [vi,venue] of ['大村','住之江'].entries()){
    const code=vi===0?24:12;
    for(let i=1;i<=12;i++)results[code+'-'+i]={finish:'1-2-3',payout_per_100:1000+10*i};
  }
  return {status:'verified_by_server_fetch',evidence_type:'official_boatrace_pay_snapshot',
    date:day,source_url:'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022',
    retrieved_at_utc:'2026-10-22T09:00:00+00:00',results,reviews:{},cancellations:{},conflicts:{}};
}
const info={date:day,type:'pay'};
const daily=R.officialRows(official(),ctx,info);
assert.equal(daily.proposed.length,24);
assert.equal(daily.officialTotal,24);
assert.ok(daily.proposed.some(x=>x.venue==='大村'&&x.race===12));
assert.ok(daily.proposed.some(x=>x.venue==='住之江'&&x.race===1));
assert.throws(()=>R.officialRows({...official(),date:'2026-10-21'},ctx,info),/日付/);
const evidence=official();
evidence.reviews['24-4']={reason:'refund'};
evidence.results['24-4']={finish:'3-1-2',payout_per_100:4000};
const review=R.officialRows(evidence,ctx,info);
assert.ok(review.proposed.find(x=>x.venue==='大村'&&x.race===4).review);
R.parseText(ocr.join('\n'),ctx);
let state=R.snapshot();
assert.equal(state.rows.length,12);
assert.equal(state.rows[0].kind,'image');
assert.equal(state.rows[0].summary,'照合候補');
assert.equal(state.rows[0].checked,true);

async function testURL(){
  payload=official();
  await R.readURL('https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022',ctx,()=>{});
  const snap=R.snapshot();
  assert.equal(snap.rows.length,24);
  assert.equal(snap.rows.filter(x=>x.matched).length,24);
  assert.equal(snap.rows.filter(x=>x.checked).length,24);
  assert.equal(snap.kind,'url');
  assert.ok(requests[0].url.includes('./data/live/official-pay/2026-10-22.json?refresh='));
  assert.equal(requests[0].opts.cache,'no-store');
  await R.readURL('https://www.boatrace.jp/owpc/pc/race/pay',ctx,()=>{});
  assert.equal(R.snapshot().rows.length,24,'bare official pay URL should resolve displayed date');
  await R.readURL('https://www.boatrace.jp/owpc/pc/race/pay?hd=20261021',ctx,()=>{});
  assert.equal(R.snapshot().rows.length,0);
  assert.match(R.snapshot().message,/対象日/);
  payload={...official(),date:'2026-10-21'};
  await R.readURL('https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022',ctx,()=>{});
  assert.equal(R.snapshot().rows.length,0);
  assert.match(R.snapshot().message,/形式|日付/);
  console.log('BOAT LAB whole-day multi-venue result intake tests: PASS');
}
testURL().catch(e=>{console.error(e);process.exitCode=1});
