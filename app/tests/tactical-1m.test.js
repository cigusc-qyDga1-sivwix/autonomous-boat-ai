const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const win={};vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),{window:win,Number,Intl});
const T=win.BoatTacticalModel;
assert.equal(Object.keys(T.RATE_BY_VENUE).length,24);
const venue=JSON.parse(fs.readFileSync('app/data/venue-profiles.json','utf8')).profiles;
for(const row of venue)assert.equal(T.RATE_BY_VENUE[row.name],row.course1_reference_rate,'24-venue prior must be source-compatible');
const original={
 venue:'唐津',cutoff_jst:'10:38',frozen_at_utc:'2026-10-23T00:20:00Z',
 weather_used:{wind_speed:2},
 racers:[7.13,5.99,7.14,5.76,6.61,7.20].map((n,i)=>({
 lane:i+1,course:i+1,name:'選手'+(i+1),
 national_win_rate:n,motor_top_2_percent:[35.29,50,38.89,50,33.33,35][i],
 average_start_timing:[.13,.16,.13,.17,.14,.14][i]
 })),
 bets:Array.from({length:8},(_,i)=>({combination:[
 '1-2-3','1-3-2','2-1-3','3-1-2','1-2-4','2-3-1','3-2-1','1-2-5'][i],virtual_yen:[7000,7000,6000,6000,6000,6000,6000,6000][i]}))
};
const source=JSON.stringify(original);
const predicted=T.forecast(original);
assert.equal(JSON.stringify(original),source,'no mutation of original frozen snapshot');
assert.equal(predicted.is_frozen,false);
assert.ok(predicted.bets.length>=4&&predicted.bets.length<=12);
assert.equal(predicted.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
assert.ok(new Set(predicted.bets.map(x=>x.combination)).size===predicted.bets.length);
assert.ok(predicted.head_course_shares.every(x=>x.relative_share>0));
assert.ok(predicted.bets.some(x=>x.head_course!==1),'scenario branching cannot silently become pure 1-head picks');
assert.ok(predicted.head_course_shares.some(x=>x.course===3&&x.relative_share>.10),'3 center attack is a meaningful branch');
const m3={...original,racers:original.racers.map((x,i)=>i===2?{...x,national_win_rate:9.0,motor_top_2_percent:80,average_start_timing:.09}:x)};
const strong=T.forecast(m3);
const share3=p=>p.head_course_shares.find(x=>x.course===3).relative_share;
assert.ok(share3(strong)>share3(predicted),'better athlete + motor + ST must increase course3 attack strength');
const poor1={...original,racers:original.racers.map((x,i)=>i===0?{...x,national_win_rate:3.0,motor_top_2_percent:15}:x)};
assert.ok(T.forecast(poor1).head_course_shares[0].relative_share<predicted.head_course_shares[0].relative_share);
const noExpo=T.forecast(original);
const expo={...original,racers:original.racers.map((r,i)=>({...r,exhibition_time:[6.72,6.60,6.50,6.75,6.70,6.74][i]}))};
assert.ok(T.forecast(expo).head_course_shares[2].relative_share>noExpo.head_course_shares[2].relative_share);
const swap={...original,racers:original.racers.map((x,i)=>({...x,course:i===0?2:i===1?1:i+1}))};
const swapped=T.forecast(swap);
assert.equal(swapped.head_course_shares[0].lane,2,'use actual course not boat number');
assert.match(fs.readFileSync('app/index.html','utf8'),/tactical-1m.js/);
assert.match(fs.readFileSync('app/app.js','utf8'),/tacticalTrialPanel\(r\)/);
console.log('Boat tactical conditional model: PASS');
