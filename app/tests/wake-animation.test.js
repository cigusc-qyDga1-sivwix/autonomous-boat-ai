'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const win={};
vm.runInNewContext(fs.readFileSync('app/race-visual.js','utf8'),{window:win,Number,Intl});
const V=win.BoatRaceVisual;
const r={racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1})),
 bets:[{combination:'4-5-6',virtual_yen:50000}]};
assert.deepEqual(Array.from(V.wakeAffected('4-5-6',r)),[1,2,3],
 'strong makuri can wash out all inside craft as an explicit scenario');
assert.deepEqual(Array.from(V.wakeAffected('4-5-1',r)),[2,3],
 'inner survivor scenario must remain visually possible');
assert.deepEqual(Array.from(V.wakeAffected('1-2-3',r)),[],
 'escape scenario must never inherit makuri washout');
const swapped={...r,racers:r.racers.map((row,i)=>({...row,
 course:[1,4,5,3,6,2][i]}))};
assert.deepEqual(Array.from(V.wakeAffected('4-5-6',swapped)),[],
 '4 boat is not automatically 4 course after pre-attachment');
assert.deepEqual(Array.from(V.wakeAffected('2-3-5',swapped)),[1,4,6],
 'new 4-course boat 2 can expose inner 1,4,6; use actual course');
const html=V.animationHTML(r);
assert.match(html,/data-sim-wake/);
assert.match(html,/引き波・失速の仮説/);
assert.doesNotMatch(V.stageTexts('4-5-6',r)[1],/着外まで下がる仮説/,
 'default must not assume that the boats physically crossed any wake');
assert.match(V.stageTexts('4-5-6',r,true)[1],/着外まで下がる仮説/,
 'only an explicitly enabled counterfactual depicts a washout');
assert.match(html,/data-sim-wake-toggle/);
assert.match(html,/初期OFF/);
assert.doesNotMatch(V.stageTexts('1-2-3',r)[1],/着外まで下がる仮説/);
assert.match(html,/実際の進入や艇間の航跡・速度を再現したものではありません/);
console.log('4C makuri wake washout scenario and animation caveats: PASS');
