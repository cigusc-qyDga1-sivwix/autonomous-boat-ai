'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const F=require('../four-factor.js');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const fixture=()=>({venue:'大村',phase:'exhibition',frozen_at_utc:'2026-10-27T00:00:00Z',weather_used:{wind_speed:2,wave_height:1},
 racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,national_win_rate:5,average_start_timing:.17,motor_top_2_percent:30,
 exhibition_st:.15,exhibition_time:6.8,racer_context:{values:{national_top3:50,local_win:5,frame_win:5,frame_st:.17,motor_top3:50}}}))});
const a=fixture(),base=F.evaluate(a);
assert.equal(Object.values(F.WEIGHTS).reduce((s,x)=>s+x,0),1);
for(const r of base.rows){assert.equal(r.combined_multiplier,1);for(const f of Object.values(r.factors))assert.equal(f.applied_multiplier,1);}
const strong=fixture();strong.racers[4].national_win_rate=8;
const b=F.evaluate(strong);assert.ok(b.rows[4].factors.athlete.applied_multiplier>1);
assert.ok(b.rows[4].combined_multiplier>base.rows[4].combined_multiplier);
const machine=fixture();machine.racers[2].motor_top_2_percent=70;
const m=F.evaluate(machine);assert.equal(m.rows[2].factors.athlete.applied_multiplier,1);assert.ok(m.rows[2].factors.motor.applied_multiplier>1);
const missing=fixture();missing.racers[0].racer_context=null;
const n=F.evaluate(missing);assert.equal(n.rows[0].available.frame,false);assert.ok(Number.isFinite(n.rows[0].combined_multiplier));
const flying=fixture();flying.racers[3].exhibition_st=-.2;
const unmeasured=fixture();unmeasured.racers[3].exhibition_st=null;
assert.equal(F.evaluate(flying).rows[3].factors.exhibition.applied_multiplier,F.evaluate(unmeasured).rows[3].factors.exhibition.applied_multiplier);
const provisional=fixture();provisional.phase='baseline';provisional.racers[0].exhibition_time=5.0;provisional.racers[0].exhibition_st=0;
for(const x of F.evaluate(provisional).rows)assert.equal(x.factors.exhibition.applied_multiplier,1,'baseline ignores every exhibition value');
const changed=fixture();changed.racers[0].course=4;changed.racers[3].course=1;changed.racers[0].racer_context.values.frame_win=9;
assert.equal(F.evaluate(changed).rows[0].frame_context_used,false,'frame 1 history cannot represent an actual 4-course entry');
const storm=JSON.parse(JSON.stringify(strong));storm.weather_used={wind_speed:10,wave_height:12};
const c=F.evaluate(storm);assert.ok(c.rows[4].combined_multiplier<b.rows[4].combined_multiplier,'roughness flattens, does not arbitrarily boost outsiders');
const expo=fixture();expo.racers[0].exhibition_time=5.5;expo.racers[0].exhibition_st=0;
assert.ok(F.evaluate(expo).rows.every(x=>x.factors.exhibition.applied_multiplier<=Math.exp(.10)+1e-9));
const original=JSON.stringify(strong),result=bridge.run(strong);
assert.equal(result.model_version,'four-factor-v1.1-untrained');assert.ok(bridge.validBets(result.bets));assert.equal(JSON.stringify(strong),original);
assert.deepEqual(result,bridge.run({...strong,result:{finish:'6-5-4'},odds:{x:999},payout:99999}),'no outcome/odds leakage');
const win={};const ctx=vm.createContext({window:win,Number,Intl});
for(const p of ['app/four-factor.js','app/tactical-1m.js'])vm.runInContext(fs.readFileSync(p,'utf8'),ctx);
const browser=win.BoatTacticalModel.forecastFourFactorOpen(strong);
assert.deepEqual(JSON.parse(JSON.stringify(browser.bets)),result.bets,'browser/server parity');
assert.match(F.panel({four_factor:result.four_factor}),/選手60・モーター25・展示10・気象5/);
assert.equal(F.panel({}),'', 'past snapshots acquire no new factor scores');
console.log('Four-factor base weights, missing/F guards, real-course mapping, weather, no leakage, browser/server parity and allocation: PASS');

require('../racer-rating.js');require('../racer-rating-panel.js');
const saved={...strong,model_role:'main',model_version:result.model_version,four_factor:result.four_factor,
 entry_exhibition_gate:{final_eligible:true},role_coverage:result.role_coverage,head_course_shares:result.head_course_shares};
const ability=globalThis.BoatRacerRating.rate(saved).rows.map(x=>x.ability);
const changedMotor=JSON.parse(JSON.stringify(saved));changedMotor.racers[0].motor_top_2_percent=90;
assert.deepEqual(globalThis.BoatRacerRating.rate(changedMotor).rows.map(x=>x.ability),ability,'pure player ability display excludes motor');
assert.match(globalThis.BoatRacerRatingPanel.render(saved),/選手基礎/);
assert.match(globalThis.BoatRacerRatingPanel.render(saved),/モーター・展示・気象は含めません/);
