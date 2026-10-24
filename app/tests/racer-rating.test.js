'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const win={};const ctx=vm.createContext({window:win,Number,Intl,console});
for(const file of ['app/tactical-1m.js','app/racer-rating.js','app/racer-rating-panel.js','app/race-visual.js']){
 vm.runInContext(fs.readFileSync(file,'utf8'),ctx,{filename:file});
}
const R=win.BoatRacerRating,P=win.BoatRacerRatingPanel;
assert.equal(R.WEIGHTS.racer,.45);
assert.equal(R.WEIGHTS.motor,.30);
assert.equal(R.WEIGHTS.course_fit,.25);
assert.equal(R.WEIGHTS.racer+R.WEIGHTS.motor+R.WEIGHTS.course_fit,1);
const source=()=>({
 venue:'唐津',model_role:'main',phase:'exhibition',
 frozen_at_utc:'2026-10-24T05:00:00Z',cutoff_jst:'14:45',
 entry_exhibition_gate:{final_eligible:true,entry_watch:false},
 weather_used:{wind_speed:2},
 racers:[5.7,6.4,6.0,6.2,8.9,6.1].map((value,i)=>({
  lane:i+1,course:i+1,name:'レーサー'+(i+1),
  national_win_rate:value,
  motor_top_2_percent:[28,31,34,37,73,40][i],
  average_start_timing:[.17,.16,.15,.14,.095,.16][i],
  exhibition_time:[6.9,6.79,6.71,6.69,6.52,6.76][i],
  original_exhibition:{turn_time:[5.91,5.84,5.73,5.70,5.49,5.80][i]}
 })),
 bets:[{combination:'1-2-3',virtual_yen:50000}],result:{finish:'1-2-3'}
});
const frozen=source(),unchanged=JSON.stringify(frozen);
const result=R.rate(frozen);
assert.equal(result.status,'ready');
assert.equal(result.rows.length,6);
assert.equal(result.model,'tactical-outside-start-gap-v0.7-untrained');
assert.equal(JSON.stringify(frozen),unchanged,'no source snapshot mutation');
assert.equal(result.provisional,false);
const r5=result.byLane[5];
assert.ok(r5.athlete>result.byLane[1].athlete,'strong racer must have higher athlete score');
assert.ok(r5.motor>result.byLane[1].motor,'strong motor contributes');
assert.ok(r5.course_fit>=R.BASE_COURSE[4],
 'strong outer starts must allow positive compatibility despite historical outer handicap');
assert.equal(result.rows.filter(x=>x.ability!==null).length,6);
assert.equal(result.rows.filter(x=>x.race_expectation!==null).length,6);
assert.equal(Math.max(...result.rows.map(x=>x.race_expectation)),100,'highest per-race relative expectation 100');
for(const x of result.rows){
 assert.ok(Number.isInteger(x.ability)&&x.ability>=0&&x.ability<=100);
 assert.ok(Number.isInteger(x.race_expectation)&&x.race_expectation>=0&&x.race_expectation<=100);
 assert.equal(x.ability,Math.round(.45*x.athlete+.30*x.motor+.25*x.course_fit));
 assert.ok(x.role_weights&&x.role_weights.first>=0&&x.role_weights.first<=1);
 assert.ok(x.role_weights.second>=0&&x.role_weights.second<=1);
 assert.ok(x.role_weights.third>=0&&x.role_weights.third<=1);
}
const panel=P.render(frozen);
assert.equal((panel.match(/class="boat-ability-card"/g)||[]).length,6);
for(const phrase of ['6艇の能力値','活躍期待指数','選手力45%','モーター30%','進入相性25%','1着 ','2着 ','3着 ','実測入着確率ではありません','金銭期待値とは異なります','SHA']){
 assert.ok(panel.includes(phrase),'must explain '+phrase);
}
assert.match(win.BoatRaceVisual.entryHTML(frozen),/出走表/);
assert.match(fs.readFileSync('app/app.js','utf8'),/BoatRacerRatingPanel\?\.render\(r\)/);
assert.match(fs.readFileSync('app/index.html','utf8'),/racer-rating\.js/);
assert.match(fs.readFileSync('app/service-worker.js','utf8'),/racer-rating-panel\.js/);
// Individual fields with special characters must not inject markup.
const htmlCase=source();htmlCase.racers[4].name='<script>alert(1)</script>';
assert.doesNotMatch(P.render(htmlCase),/<script>/);
assert.match(P.render(htmlCase),/&lt;script&gt;/);
// True course != lane: should always calculate by actual position.
const swapped=source();
swapped.racers[0].course=5;swapped.racers[4].course=1;
const swap=R.rate(swapped);
assert.equal(swap.byLane[1].course,5);
assert.equal(swap.byLane[5].course,1);
assert.equal(swap.byLane[1].course_confirmed,true);
// Historical achievements may be missing, so leave ability score blank.
const missing=source();
missing.racers[4].national_win_rate=null;
missing.racers[3].motor_top_2_percent=null;
const sparse=R.rate(missing);
assert.equal(sparse.byLane[5].athlete,null);
assert.equal(sparse.byLane[5].ability,null);
assert.equal(sparse.byLane[4].motor,null);
assert.equal(sparse.byLane[4].ability,null);
assert.match(P.render(missing),/—/);
// Race course entry not confirmed: no faux "compatibility" number.
const unconfirmed=source();
unconfirmed.racers[4].course=4;
const pending=R.rate(unconfirmed);
assert.equal(pending.provisional,true);
assert.ok(pending.rows.every(x=>x.course_fit===null&&x.ability===null));
assert.match(P.render(unconfirmed),/進入未確認/);
// Even if lane/course values look valid, baseline before entrance verification
// must not pretend that lane=course is a confirmed tactical fit.
const baseline=source();
baseline.phase='baseline';
baseline.entry_exhibition_gate={final_eligible:false,entry_watch:false};
const heldCourse=R.rate(baseline);
assert.equal(heldCourse.provisional,true);
assert.ok(heldCourse.rows.every(x=>x.course_fit===null&&x.ability===null));
// Older exhibition snapshots with explicit six-course data remain usable.
const legacyExhibition=source();
delete legacyExhibition.entry_exhibition_gate;
assert.equal(R.rate(legacyExhibition).provisional,false);
// Guard against mistakenly treating exhibition false starts as good average ST.
const flying=source();flying.racers[4].exhibition_st=-.01;
const flagged=R.rate(flying);
assert.ok(flagged.byLane[5].ability!==null);
// Correct display hold state for watched front attachment.
const watch=source();
watch.entry_exhibition_gate={entry_watch:true,final_eligible:false};
const held=R.rate(watch);
assert.equal(held.status,'hold');
assert.equal(held.model,null);
assert.ok(held.rows.every(x=>x.race_expectation===null&&x.role_weights===null));
assert.match(P.render(watch),/展示進入確認待ち/);
// The expectation model NEVER uses finish/payout/official outcome fields.
const withoutOutcome=source();delete withoutOutcome.result;
const withOutcome={...withoutOutcome,
 result:{finish:'5-6-4',decision:'まくり'},
 payout:{yen_per_100:1234567},official_results:{fake:'5-6-4'},odds:{'5-6-4':999}};
assert.deepEqual(JSON.parse(JSON.stringify(R.rate(withoutOutcome))),
 JSON.parse(JSON.stringify(R.rate(withOutcome))),'future race outcomes and odds cannot change evaluations');
// No fake monetary EV or calibrated probability.
assert.doesNotMatch(P.render(withoutOutcome),/予想的中確率99|期待回収率120/);
console.log('BOAT LAB 6-racer ability and per-race role expectation model: PASS');
