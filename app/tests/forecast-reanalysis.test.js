const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context={window:{},Date,Intl};
vm.runInNewContext(fs.readFileSync('app/forecast-reanalysis.js','utf8'),context);
const engine=context.window.BoatReanalysis;
const mkRace=()=>({
  venue:'徳山',race:8,cutoff_jst:'13:30',
  racers:Array.from({length:6},(_,i)=>({
    lane:i+1,course:i+1,name:'選手'+(i+1),
    national_win_rate:[6.6,6.1,5.4,5.3,4.5,5.2][i],
    motor_top_2_percent:[33,40,35,27,41,32][i],
    average_start_timing:[.16,.13,.15,.15,.14,.19][i],
    exhibition_time:[6.77,6.74,6.79,6.70,6.81,6.85][i],
    exhibition_st:[.12,.13,.07,.09,.16,.18][i]
  }))
});
const race=mkRace();
const original=JSON.stringify(race);
const base=engine.model(race,{});
assert.equal(base.bets.length,8);
assert.equal(base.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
assert.equal(new Set(base.bets.map(x=>x.combination)).size,8);
assert.ok(base.used.includes('展示タイム'));
assert.ok(base.used.includes('展示ST'));
assert.match(base.method,/未訓練/);
assert.equal(JSON.stringify(race),original,'never mutate frozen race');
const complete={};
for(let lane=1;lane<=6;lane++)complete[lane]={
  lap_time:38.1+.11*lane,
  turn_time:5.4+.17*lane,
  straight_time:7+.06*lane
};
const extra=engine.model(race,complete);
assert.equal(extra.used.length,5);
assert.equal(extra.bets.length,8);
assert.equal(extra.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
assert.equal(JSON.stringify(race),original,'extra data does not alter original');
const partial=engine.model(race,{1:{lap_time:37.9}});
assert.equal(partial.used.some(x=>x.includes('1周')),false);
assert.ok(partial.skipped.some(x=>x.includes('6艇分未入力')));
const fRace=mkRace();fRace.racers[0].exhibition_st=-.12;
const flying=engine.model(fRace,{});
assert.ok(flying.skipped.some(x=>x.includes('展示F')));
assert.ok(!flying.used.includes('展示ST'));
assert.throws(()=>engine.model(race,{1:{lap_time:1}}),/30〜50秒/);
assert.throws(()=>engine.model({racers:[]},{}),/6艇分/);
assert.match(engine.inputForm(race,{}),/data-recalc-lane="6"/);
assert.equal((engine.inputForm(race,{}).match(/data-recalc-lane=/g)||[]).length,18);
assert.match(engine.resultHTML(base,false),/展開を再評価した3連単8点/);
assert.match(engine.resultHTML(base,true),/締切後の事後シミュレーション/);
assert.ok(!fs.readFileSync('app/forecast-reanalysis.js','utf8').includes('fetch('));
console.log('BOAT LAB scenario reanalysis pure model tests: PASS');
