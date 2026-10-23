const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const window={};
const sandbox=vm.createContext({window});
for(const name of ['app/venue-geometry.js','app/race-visual.js','app/tactical-preview.js'])
 vm.runInContext(fs.readFileSync(name,'utf8'),sandbox);
const api=window.BoatRaceVisual;
const race={venue:'尼崎',race:5,bets:[{combination:'1-2-3',virtual_yen:50000}],
 racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,name:'TEST'+(i+1),
 average_start_timing:.15,national_win_rate:5,motor_top_2_percent:35}))};
const frozen=JSON.stringify(race);
const cfg=api.tactics.defaults(race);
cfg.boats[1].kind='sashi';
cfg.boats[2].kind='makuri';
const calc=(relativeWind,wind)=>api.tactics.analyze(race,{...cfg,relativeWind,wind});
const h=calc('head',7),t=calc('tail',7),unknown=calc('unknown',7),weak=calc('tail',2);
assert.ok(h.boats[2].windBias.delta>0,'headwind center makuri gets small trial nudge');
assert.ok(h.boats[0].windBias.delta<0,'headwind slow start risk');
assert.ok(t.boats[1].windBias.delta>0,'tailwind sashi window gets a nudge');
assert.ok(t.boats[2].windBias.delta<0,'tailwind outer sweep risk');
assert.equal(unknown.boats.reduce((v,b)=>v+b.windBias.delta,0),0,'unknown direction never guessed');
assert.ok(weak.boats.every(b=>b.windBias.delta===0),'below 3m/s no nudge');
assert.match(h.note,/向かい風/);assert.match(t.note,/追い風/);
assert.notEqual(api.tactics.trajectory(h.boats[2],h.rank[3],h),api.tactics.trajectory(t.boats[2],t.rank[3],t));
for(const b of h.boats.concat(t.boats))assert.ok(Math.abs(b.windBias.delta)<=.06);
assert.equal(JSON.stringify(race),frozen,'No modification to frozen forecast or stakes');
console.log('Head/tail scenario cues, mild/unknown safeguards, immutable forecasts: PASS');