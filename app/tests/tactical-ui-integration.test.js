const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const win={};const ctx=vm.createContext({window:win,Number,Intl});
vm.runInContext(fs.readFileSync('app/tactical-1m.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/race-visual.js','utf8'),ctx);
const races=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8')).forecast_races;
const r=races.find(x=>x.venue==='唐津'&&x.racers?.length===6)||races.find(x=>x.racers?.length===6); // today's venues may not include 唐津
assert.ok(r);
const original=JSON.stringify(r);
const model=win.BoatTacticalModel.forecast(r),view=win.BoatRaceVisual;
const html=view.animationHTML(r);
assert.ok(view.tacticalOptions(r).length>0);
assert.equal(view.tacticalOptions(r)[0].combo,
  r.model_role==='main'?r.legacy_control.bets[0].combination:model.top,
  'v0.7 main keeps old model only in shadow animation choices');
assert.ok(view.choices(r).some(x=>x.kind==='tactical'));
assert.match(html,/戦法別 v5/);
assert.match(html,r.model_role==='main'?/旧モデルの検証用買い目/:/戦法モデルの候補/);
assert.match(html,r.model_role==='main'?/旧モデル比較/:/未固定/);
assert.match(html,/data-sim-kind="tactical"/);
assert.match(html,/data-sim-kind="forecast"/);
assert.match(html,/1Mの外/);
assert.equal(JSON.stringify(r),original,'app must not alter existing fixed prediction');
const css=fs.readFileSync('app/styles.css','utf8');
assert.match(css,/boat-sim-tactical/);
assert.match(css,/boat-tactical-trial/);
const index=fs.readFileSync('app/index.html','utf8');
assert.ok(index.indexOf('tactical-1m.js')<index.indexOf('race-visual.js'));
assert.ok(index.indexOf('race-visual.js')<index.indexOf('app.js'));
console.log('New tactical predictions are connected to live app replay and fixed picks remain intact: PASS');
