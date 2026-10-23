const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const day='2026-10-24';
const names=['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
const record={
 race_code:'202610241401',venue:'鳴門',race:1,source_observed_jst:'2026-10-24T08:24:00+09:00',
 boats:Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,exhibition_st:.12,exhibition_time:6.76,
   original_exhibition:[
    {metric:'一周',value:37+i*.1},{metric:'まわり足',value:5.7+i*.1},
    {metric:'直線',value:7.1+i*.1},
    {metric:'半周ラップ',value:40+i*.1}
   ]
 })),
 result:{finish:'6-5-4'},payout:{finish:'6-5-4',yen_per_100:43210}
};
let resolveLoad;
const mockedFetch=async url=>{
 if(url.includes('status-latest'))return {ok:true,json:async()=>({
  event_date:day,collected_at_utc:'2026-10-24T00:00:00Z',complete_sources:true
 })};
 if(url.includes(day+'.json'))return {ok:true,json:async()=>({
  schema:'boatlabs.exhibition_research.v1',event_date:day,
  created_at_utc:'2026-10-24T00:02:00Z',records:[record]
 })};
 throw Error('Unexpected '+url);
};
const win={};
const env=vm.createContext({window:win,fetch:mockedFetch,Date,Number,Intl,console});
vm.runInContext(fs.readFileSync('app/exhibition-audit.js','utf8'),env);
vm.runInContext(fs.readFileSync('app/forecast-reanalysis.js','utf8'),env);
const audit=win.BoatExhibitionAudit,recalc=win.BoatReanalysis;
const race={
 venue:'鳴門',race:1,frozen_at_utc:'2026-10-23T23:23:00Z',
 racers:Array.from({length:6},(_,i)=>({
   lane:i+1,course:i+1,
   national_win_rate:5.2,motor_top_2_percent:35,average_start_timing:.14,
   original_exhibition: i===0?{lap_time:36.5}:{}
 })),
 bets:[{combination:'1-2-3',virtual_yen:50000}]
};
(async()=>{
 await audit.load(day);
 const metrics=audit.metricsFor(race);
 assert.equal(metrics.date,day);
 assert.equal(metrics.values[1].turn_time,5.7);
 assert.equal(metrics.values[6].straight_time,7.6);
 assert.equal(metrics.values[1].lap_time,37);
 assert.equal(metrics.values[1].half_lap_time,undefined,'do not map half lap to full lap');
 assert.equal(metrics.result,undefined,'never expose race result to autofill');
 assert.equal(metrics.payout,undefined,'never expose payout to autofill');
 const original=JSON.stringify(race);
 const auto=recalc.autoExtra(race,metrics);
 assert.equal(auto.sources.frozen,1);
 assert.equal(auto.sources.research,17);
 assert.equal(auto.values[1].lap_time,36.5,'frozen value beats research');
 assert.equal(auto.values[2].lap_time,37.1);
 assert.equal(auto.complete.lap_time,true);
 assert.equal(auto.complete.turn_time,true);
 assert.equal(auto.complete.straight_time,true);
 const input=recalc.inputForm(race,recalc.mergeInput(auto.values,{}),auto);
 assert.match(input,/data-recalc-lane="1" data-recalc-metric="lap_time" value="36.5"/);
 assert.match(input,/data-recalc-lane="6" data-recalc-metric="straight_time" value="7.6"/);
 assert.match(input,/自動入力 18\/18項目/);
 assert.match(input,/取得・保存が締切前だったとは保証されません/);
 const merged=recalc.mergeInput(auto.values,{2:{lap_time:'',straight_time:'7.9'}});
 assert.equal(merged[2].lap_time,'','user clear must override fetch');
 assert.equal(merged[2].straight_time,'7.9','user override wins');
 const estimated=recalc.model(race,auto.values);
 assert.ok(estimated.used.some(x=>x.includes('1周')));
 assert.ok(estimated.used.some(x=>x.includes('回り足')));
 assert.ok(estimated.used.some(x=>x.includes('直線')));
 assert.equal(estimated.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
 assert.equal(JSON.stringify(race),original,'frozen predictions remain immutable');
 // Real course variation: only 2 categories and half-lap is not lap_time.
 const halfLap=record.boats.map(b=>({...b,original_exhibition:[
  {metric:'半周ラップ',value:35},{metric:'まわり足',value:6.0},
  {metric:'直線',value:7.0}]}));
 const second={...record,race_code:'202610241402',boats:halfLap};
 const w2={},c2=vm.createContext({window:w2,fetch:async url=>({
  ok:true,json:async()=>url.includes('status-latest')?{}:{
   schema:'boatlabs.exhibition_research.v1',event_date:day,records:[second]}
 }),Date,console});
 vm.runInContext(fs.readFileSync('app/exhibition-audit.js','utf8'),c2);
 await w2.BoatExhibitionAudit.load(day);
 const secondMetrics=w2.BoatExhibitionAudit.metricsFor({venue:'鳴門',race:2});
 assert.equal(secondMetrics.values[1].lap_time,undefined);
 assert.equal(secondMetrics.values[1].turn_time,6);
 const bad=recalc.autoExtra({...race,racers:race.racers.slice(0,5)},metrics);
 assert.equal(bad.missing,true);
 console.log('BOAT LAB auto original-exhibition fill and source safety: PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
