const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const window={};
const ctx=vm.createContext({window,Date,Intl,console});
vm.runInContext(fs.readFileSync('app/exhibition-direct.js','utf8'),ctx);
const api=window.BoatOriginalExhibitionDirect;
const DAY='2026-10-24',CUTOFF='2026-10-24T08:51:00+09:00';
const NOW=Date.parse('2026-10-24T08:50:00+09:00');
const race={venue:'三国',race:1,cutoff_jst:'08:51'};
const metrics=['一周','まわり足','直線'];
const columns=['レースコード','レース日','レース場','レース回','締切時刻','取得日時',
 '計測項目1','計測項目2','計測項目3'];
for(let lane=1;lane<=6;lane++)for(let k=1;k<=3;k++)columns.push('艇'+lane+'_値'+k);
function csv(day=DAY,record='202610241001'){
 const row=[record,day,'10','01R','08:51','2026-10-24T08:45:20+09:00',
  ...metrics];
 for(let lane=1;lane<=6;lane++)row.push(String(36+lane/10),String(5+lane/10),String(7+lane/10));
 return '\uFEFF'+columns.join(',')+'\r\n'+row.join(',')+'\r\n';
}
assert.equal(api.raceId(race,DAY),'202610241001');
const source=csv();
const parsed=api.parseCsv(source);
assert.equal(parsed.length,1);
assert.equal(parsed[0]['艇2_値2'],'5.2');
const found=api.extract(source,race,DAY,NOW);
assert.equal(found.count,18);
assert.equal(found.values[6].lap_time,36.6);
assert.equal(found.values[6].turn_time,5.6);
assert.equal(found.values[6].straight_time,7.6);
assert.equal(found.result,undefined,'result not projected');
assert.equal(found.payout,undefined,'payout not projected');
assert.equal(api.extract(csv(DAY,'202610241002'),race,DAY,NOW),null,'other race filtered');
assert.equal(api.extract(csv('2026-10-23'),race,DAY,NOW),null,'other date filtered');
const half=csv().replace(',一周,まわり足,直線',',半周ラップ,まわり足,直線');
assert.equal(api.extract(half,race,DAY,NOW).count,12,'half lap not relabeled as 1 lap');
assert.equal(api.extract(half,race,DAY,NOW).values[1].lap_time,undefined);
const future=csv().replace('2026-10-24T08:45:20+09:00','2026-10-24T08:55:20+09:00');
assert.equal(api.extract(future,race,DAY,NOW),null,'future and post-cutoff source rejected');
assert.throws(()=>api.parseCsv('a,b\n1,2'),/形式/);
const evil=csv().replace(',36.1,5.1,7.1',',999,5.1,7.1');
assert.equal(api.extract(evil,race,DAY,NOW).count,17);
assert.deepEqual(api.parseCsv('レースコード,取得日時,計測項目1\n"000,111",today,x')[0]['レースコード'],'000,111');
(async()=>{
 let calls=0,url='';
 const fetcher=async (u,init)=>{
  calls++;url=u;
  assert.equal(init.cache,'no-store');
  return {ok:true,text:async()=>source};
 };
 const result=await api.refresh(race,DAY,{fetcher,nowMs:NOW});
 assert.equal(result.state,'ready');
 assert.equal(api.get(race,DAY).values[1].turn_time,5.1);
 assert.match(url,/previews\/original_exhibition\/2026\/10\/24\.csv/);
 assert.doesNotMatch(url,/results|payout|odds/);
 await api.refresh(race,DAY,{fetcher,nowMs:NOW+5000});
 assert.equal(calls,1,'avoid rapid publisher polling within 18 seconds');
 await api.refresh(race,DAY,{fetcher,nowMs:NOW+10000,force:true});
 assert.equal(calls,2,'manual refresh bypasses automatic throttle');
 const whenOver=await api.refresh(race,DAY,{fetcher,nowMs:Date.parse(CUTOFF)+60000,force:true});
 assert.equal(whenOver.after_cutoff,true);
 assert.equal(calls,2,'no post-cutoff original CSV fetch');
 // Failed network/CORS should keep the last known eligible data.
 const failed=await api.refresh(race,DAY,{fetcher:async()=>{throw Error('CORS')},nowMs:NOW+12000,force:true});
 // Already past cutoff in previous simulation, so direct remains preserved.
 assert.equal(failed.state,'ready');
 const alt={...race,race:2,cutoff_jst:'09:25'};
 const first=await api.refresh(alt,DAY,{fetcher:async()=>{throw Error('CORS blocked')},
  nowMs:Date.parse('2026-10-24T09:20:00+09:00')});
 assert.equal(first.state,'error');
 assert.match(first.message,/CORS blocked/);
 assert.equal(api.get(alt,DAY),null);
 const pending=await api.refresh({...race,race:3,cutoff_jst:'09:25'},DAY,{
  fetcher:async()=>({ok:true,text:async()=>source}),nowMs:Date.parse('2026-10-24T09:20:00+09:00')});
 assert.equal(pending.state,'unpublished');
 console.log('BOAT LAB direct original-exhibition preview and 1-minute cutoff fetch: PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
