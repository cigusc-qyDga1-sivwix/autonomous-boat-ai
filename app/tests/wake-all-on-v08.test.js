'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const win={};
const ctx=vm.createContext({window:win,Number,Intl});
for(const path of ['app/wake-study.js','app/race-visual.js']){
 vm.runInContext(fs.readFileSync(path,'utf8'),ctx,{filename:path});
}
const W=win.BoatWakeStudy,V=win.BoatRaceVisual;
const mk=()=>({venue:'唐津',
  model_role:'main',
  racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,
    average_start_timing:.17-i*.008,
    original_exhibition:{turn_time:5.8-i*.025}})),
  bets:[{combination:'4-5-6',virtual_yen:50000}]
});
const race=mk(),original=JSON.stringify(race);
const outer=W.analysis('4-5-6',race);
assert.equal(outer.status,'hypothesis');
assert.equal(outer.head_course,4);
assert.equal(outer.calibrated,false);
assert.equal(outer.evidence_quality,'unmeasured_schematic_only');
const risk=outer.exposures.filter(x=>x.phase==='1M');
assert.deepEqual(Array.from(risk.map(x=>x.lane).sort((a,b)=>a-b)),[1,2,3],
 '4 course winner puts 1/2/3 inside lanes under study');
assert.ok(outer.exposures.some(x=>x.phase==='2M+'),'study wake after turn one too');
assert.ok(outer.exposures.every(x=>x.risk>=0&&x.risk<=1));
assert.ok(outer.exposures.every(x=>x.note&&!x.note.includes('確定')));
const escape=W.analysis('1-2-3',race);
assert.equal(escape.exposures.filter(x=>x.phase==='1M').length,0,
 'inside winner has no automatically crossed inner boats');
assert.ok(escape.exposures.filter(x=>x.phase==='2M+').length>=2,
 '2M wake of leaders is studied for 2nd/3rd even in an escape');
const center=W.analysis('3-5-1',race);
assert.ok(center.exposures.some(x=>x.phase==='1M'&&x.lane===2));
assert.ok(center.exposures.some(x=>x.lane===1&&x.note.includes('残存')),
 'inner survivor must remain credible');
const sixth=W.analysis('6-5-1',race);
assert.ok(sixth.exposures.some(x=>x.phase==='1M'&&x.lane===2),
 '6th course can create a crossing scenario');
const reset=mk();reset.racers[1].course=4;reset.racers[3].course=2;
const swapped=W.analysis('2-5-6',reset);
assert.equal(swapped.head_course,4);
assert.ok(swapped.exposures.some(x=>x.phase==='1M'&&x.lane===4));
assert.ok(!swapped.exposures.some(x=>x.phase==='1M'&&x.lane===2),
 'use actual entry course rather than boat number');
assert.equal(W.analysis('1-1-3',race).status,'unknown');
assert.equal(JSON.stringify(race),original,'do not mutate pre-race record');
const after={...race,result:{finish:'4-5-6'},payout:12600,
 official_results:{'r':'4-5-6'},odds:{'4-5-6':15}};
assert.deepEqual(JSON.parse(JSON.stringify(W.analysis('4-5-6',race))),
 JSON.parse(JSON.stringify(W.analysis('4-5-6',after))),
 'actual results and odds must not leak into wake research');
const html=V.animationHTML(race);
assert.match(html,/data-sim-wake-toggle aria-pressed="true"/);
assert.match(html,/全レース初期ON/);
assert.match(html,/data-sim-wake-info/);
assert.match(V.stageTexts('4-5-6',race,true)[1],/引き波の影響を受ける可能性/);
assert.match(V.stageTexts('1-2-3',race,true)[2],/2M以降の追走艇/);
assert.doesNotMatch(V.stageTexts('1-2-3',race,true)[1],/が引き波の影響を受ける可能性/);
assert.match(fs.readFileSync('app/index.html','utf8'),/wake-study\.js/);
assert.match(fs.readFileSync('app/service-worker.js','utf8'),/wake-study\.js/);
console.log('BOAT LAB wake ON by default: scenarios 1–6, safe caveats, 1M/2M split and no outcome leakage: PASS');
