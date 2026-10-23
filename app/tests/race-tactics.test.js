const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const window={};
vm.runInNewContext(fs.readFileSync('app/race-visual.js','utf8'),{window,Number,Intl});
const V=window.BoatRaceVisual;
const resultSample='3-2-1'; // 2026-10-23 Karatsu 1R result, NOT a pre-race forecast.
const roles=V.rolesFor(resultSample);
assert.equal(roles[0].role,'escape','1M inside boat attempts first turn even when not winner');
assert.equal(roles[1].role,'sashi','course 2 boat has distinct inside passing hypothesis');
assert.equal(roles[2].role,'makuri-zashi','winner 3 with 2 second and 1 third can represent makuri-zashi');
assert.equal(roles[3].role,'makuri','course 4 has wider attack');
assert.match(V.stageTexts(resultSample)[0],/先マイ/);
assert.match(V.stageTexts(resultSample)[1],/まくり差し/);
assert.notEqual(V.path(1,3,'makuri-zashi',3,roles[0].role,1),
                V.path(3,1,'makuri-zashi',3,roles[2].role,3));
assert.notEqual(V.path(2,2,'makuri-zashi',3,roles[1].role,2),
                V.path(4,4,'makuri-zashi',3,roles[3].role,4));
const forcedFirst=V.rolesFor('1-2-3');
assert.equal(forcedFirst[0].role,'escape');
const swap={racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i===0?2:i===1?1:i+1}))};
const moved=V.rolesFor('3-2-1',swap);
assert.equal(moved[1].role,'escape','inside course occupant is the inside turner, not lane-number heuristic');
assert.equal(moved[0].role,'sashi');
const mock={racers:swap.racers.map(x=>({...x,name:'選手'+x.lane,national_win_rate:5,motor_top_2_percent:30})),
            bets:[{combination:resultSample,virtual_yen:50000}]};
const html=V.animationHTML(mock);
assert.match(html,/data-sim-roles/);
assert.match(html,/先マイ/);
assert.match(html,/差し/);
assert.match(html,/まくり/);
assert.match(html,/実際の進入/);
console.log('Boat LAB tactical first-mark animation invariant tests: PASS');
