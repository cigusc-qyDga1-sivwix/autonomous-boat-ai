'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const bridge=require('../../scripts/main_v07_bridge.js');
const raw=require('./fixtures/frozen-official-data.js');
const race=JSON.parse(JSON.stringify(raw.forecast_races[0]));
const feature={venue:race.venue,racers:race.racers,phase:race.phase,
 weather_used:race.weather_used||null,
 venue_profile:race.venue_profile||null,
 frozen_at_utc:race.frozen_at_utc};
const model=bridge.run(feature);
assert.equal(model.model_version,'tactical-outside-start-gap-v0.7-untrained');
assert.ok(bridge.validBets(model.bets));
const prior=race.bets;
race.bets=model.bets;
race.model_version=model.model_version;
race.model_role='main';
race.legacy_control={model_version:'heuristic-0.7-venue-priors-test-untrained',
 model_role:'shadow_validation',bets:prior,sha256:'old-shadow-hash',frozen_at_utc:race.frozen_at_utc};
const win={};const ctx=vm.createContext({window:win,Number,Intl});
vm.runInContext(fs.readFileSync('app/tactical-1m.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/race-visual.js','utf8'),ctx);
const V=win.BoatRaceVisual,html=V.animationHTML(race);
assert.equal(V.tacticalOptions(race)[0].combo,prior[0].combination);
assert.match(html,/メインv0\.7 発走前固定/);
assert.match(html,/旧モデルの検証用買い目/);
assert.ok(html.includes('data-sim-pick="'+model.bets[0].combination+'"'));
assert.match(html,/v0\.7本線/);
assert.match(fs.readFileSync('app/app.js','utf8'),/legacyControlPanel\(r\)/);
assert.match(fs.readFileSync('app/app.js','utf8'),/main_vs_legacy/);
assert.match(fs.readFileSync('app/venue-board.js','utf8'),/メインv0\.7 固定/);
const before=JSON.stringify(race);
V.animationHTML(race);
assert.equal(JSON.stringify(race),before,'UI may not rewrite canonical frozen tickets');
console.log('Canonical v0.7 Node parity and UI first, archived old shadow secondary: PASS');
