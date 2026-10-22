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
assert.ok(base.bets.length>=4&&base.bets.length<=12);
assert.equal(base.point_count,base.bets.length);
assert.match(base.point_reason,/相対重み/);
assert.equal(base.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
assert.equal(new Set(base.bets.map(x=>x.combination)).size,base.bets.length);
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
assert.ok(extra.bets.length>=4&&extra.bets.length<=12);
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
assert.match(engine.resultHTML(base,false),new RegExp('展開を再評価した3連単'+base.bets.length+'点'));
assert.match(engine.resultHTML(base,true),/締切後の事後シミュレーション/);
assert.ok(!fs.readFileSync('app/forecast-reanalysis.js','utf8').includes('fetch('));
console.log('BOAT LAB scenario reanalysis pure model tests: PASS');


// Full 4–12 adaptive range: head concentration chooses the breadth.
assert.equal(engine.pointCount([20,1,1,1,1,1]).count,4);
assert.equal(engine.pointCount([1,1,1,1,1,1]).count,12);
assert.ok(engine.pointCount([3,2,1.8,1.5,1.4,1.2]).count>=4);
const four=engine.allocateBets(['1-2-3','1-2-4','1-2-5','1-2-6'].map((combination,i)=>({combination,weight:1/(i+1)})));
assert.equal(four.length,4);
assert.equal(four.reduce((sum,b)=>sum+b.virtual_yen,0),50000);
const combos=[];
for(let a=1;a<=6;a++)for(let b=1;b<=6;b++)if(a!==b)for(let c=1;c<=6;c++)if(c!==a&&c!==b)combos.push([a,b,c].join('-'));
const twelve=engine.allocateBets(combos.slice(0,12).map((combination,i)=>({combination,weight:12-i})));
assert.equal(twelve.length,12);
assert.equal(twelve.reduce((sum,b)=>sum+b.virtual_yen,0),50000);
assert.ok(twelve[0].virtual_yen>twelve.at(-1).virtual_yen);
assert.ok(four.every(b=>b.virtual_yen>=1000));
assert.ok(twelve.every(b=>b.virtual_yen>=1000));
