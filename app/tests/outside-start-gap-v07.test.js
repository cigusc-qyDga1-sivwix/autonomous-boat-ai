'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const win={};
vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),{window:win,Intl,Number});
const T=win.BoatTacticalModel;
const template=()=>({venue:'丸亀',weather_used:{wind_speed:2},racers:
 Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,national_win_rate:5.2,
  motor_top_2_percent:34,average_start_timing:.18,exhibition_st:.19,
  exhibition_time:6.76,original_exhibition:{}
 }))});
const original=template(),string=JSON.stringify(original);
const out=T.forecastOutsideStart(original),old=T.forecastCoupled(original);
assert.equal(JSON.stringify(original),string,'no mutations');
assert.equal(out.model,'tactical-outside-start-gap-v0.7-untrained');
assert.equal(old.model,'tactical-six-boat-coupling-v0.6-untrained');
assert.equal(out.metadata.start_v07.slit_signals.length,6);
assert.equal(out.metadata.start_v07.calibrated,false);
const laneShare=(m,c,role)=>m.role_coverage[c][role];
const outsideCount=m=>m.bets.filter(b=>{
 const [a,b2]=b.combination.split('-').map(Number);return a>=4||b2>=4;
}).length;
for(const lane of [4,5,6]){
 const src=template();
 // A strong outside competitor and a visibly late immediate inner course.
 src.racers[lane-1]={...src.racers[lane-1],national_win_rate:8.0,
  motor_top_2_percent:70,average_start_timing:.08,exhibition_st:.09,exhibition_time:6.58};
 src.racers[lane-2]={...src.racers[lane-2],average_start_timing:.26,
  exhibition_st:.27,national_win_rate:4.2};
 const prev=T.forecastCoupled(src),next=T.forecastOutsideStart(src);
 const signal=next.metadata.start_v07.slit_signals[lane-1];
 assert.equal(signal.lane,lane);
 assert.ok(signal.nearest_gap_sec>=.03,'positive gap against inside');
 assert.equal(signal.head_evidence,true,'outside 4-6 should all have attack hypotheses');
 assert.equal(signal.second_evidence,true,'outside 4-6 second branch should be assessed');
 assert.ok(next.head_course_shares[lane-1].relative_share>prev.head_course_shares[lane-1].relative_share,
  'start-based attacking gap raises head relative score for '+lane);
 const insideSecond=next.metadata.start_v07.second_given_inside_first;
 assert.equal(insideSecond.length,5);
 const other={...src,racers:src.racers.map((r,i)=>(
   i===lane-1||i===lane-2?
    {...r,average_start_timing:.18,exhibition_st:.18}:r
 ))};
 const neutral=T.forecastOutsideStart(other).metadata.start_v07.second_given_inside_first;
 assert.ok(insideSecond.find(x=>x.course===lane).conditional_relative_weight>
   neutral.find(x=>x.course===lane).conditional_relative_weight,
   'outer 2nd given 1st-course winner must improve when ST lead appears: '+lane);
 assert.ok(next.bets.some(b=>b.combination.split('-').slice(0,2).includes(String(lane))),
  'strong 4/5/6 must appear as head or second if a competitive 3-way combo exists: '+lane);
 assert.ok(next.bets.length>=4&&next.bets.length<=12);
 assert.equal(next.bets.reduce((n,b)=>n+b.virtual_yen,0),50000);
 assert.equal(new Set(next.bets.map(b=>b.combination)).size,next.bets.length);
}
const noGap=template();
noGap.racers[5]={...noGap.racers[5],exhibition_st:.36,average_start_timing:.26,
 national_win_rate:3,motor_top_2_percent:12};
const slow=T.forecastOutsideStart(noGap).metadata.start_v07.slit_signals[5];
assert.equal(slow.head_evidence,false);
assert.equal(slow.second_evidence,false);
const f=template();f.racers[4].exhibition_st=-.08;
const fsignal=T.forecastOutsideStart(f).metadata.start_v07.slit_signals[4];
assert.equal(fsignal.exhibition_f_ignored,true);
assert.ok(fsignal.estimated_st>=0,'F display must never be fast ST');
const shuffled=template(),actual=[2,4,5,1,6,3];
shuffled.racers.forEach((r,i)=>r.course=actual[i]);
const change=T.forecastOutsideStart(shuffled);
assert.equal(change.metadata.start_v07.slit_signals[3].lane,2,'actual course 4 is boat2');
assert.throws(()=>T.forecastOutsideStart({...shuffled,
 racers:shuffled.racers.map((r,i)=>({...r,course:i?2:1}))}),/実進入が未確認/);
const contaminated=T.forecastOutsideStart({...original,result:{finish:'6-5-4'},
 official_results:{'丸亀|1':{finish:'6-5-4'}},payout:{amount:12000}});
assert.equal(JSON.stringify(contaminated),JSON.stringify(out),'no outcome leakage');
assert.ok(outsideCount(out)>=0);
console.log('BOAT LAB start-gap v0.7 4/5/6 head and second branches, F, actual course, ledger safety: PASS');
