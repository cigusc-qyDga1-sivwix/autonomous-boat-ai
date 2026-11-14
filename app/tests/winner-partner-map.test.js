'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const component = fs.readFileSync('app/winner-partner-map.js', 'utf8');
const sandbox = {window:{}};
vm.runInNewContext(component, sandbox);
const map = sandbox.window.BoatWinnerPartnerMap;
assert.equal(typeof map.render, 'function');
assert.equal(map.render(null), '');
assert.equal(map.render({bets: []}), '');
const race = {
  scenario:'1逃げ・4攻め <script>alert(1)</script>',
  phase:'exhibition',
  bets:[
    {combination:'1-2-3', virtual_yen:20000},
    {combination:'1-2-4', virtual_yen:10000},
    {combination:'1-4-2', virtual_yen:5000},
    {combination:'4-1-2', virtual_yen:15000}
  ]
};
const before=JSON.stringify(race);
const formal=map.render(race,{formal:true});
assert.match(formal,/1着から読む紐マップ/);
assert.match(formal,/✅ 正式・発走前固定/);
assert.match(formal,/1着 ① の紐/);
assert.match(formal,/1着 ④ の紐/);
assert.match(formal,/2着 ②/);
assert.match(formal,/3着候補/);
assert.match(formal,/仮想50,000円/);
assert.match(formal,/&lt;script&gt;/);
assert.ok(!formal.includes('<script>'));
assert.equal((formal.match(/class="wpm-head"/g)||[]).length,2);
assert.equal(JSON.stringify(race),before,'render must not change saved forecast');
const provisional=map.render(race,{formal:false});
assert.match(provisional,/暫定・研究表示/);
assert.match(provisional,/正式予想ではありません/);
const groups=map.groups(race.bets);
assert.equal(groups.length,2);
assert.equal(groups[0].head,1);
assert.equal(groups[0].count,3);
assert.equal(groups[0].second.get(2).third.length,2);
console.log('Winner→2nd→3rd frozen ticket display: PASS');
