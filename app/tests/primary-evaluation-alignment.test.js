'use strict';
// Confirm main player ranking, first/second/third ratings and purchased tickets
// are read from the SAME frozen primary forecast, never a trial replay.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
let shadowCalls=0;
const window={BoatTacticalModel:{
 forecast:()=>{shadowCalls++;return {head_course_shares:[
   {lane:4,course:4,relative_share:.8},...Array.from({length:5},(_,i)=>({
    lane:[1,2,3,5,6][i],course:[1,2,3,5,6][i],relative_share:.04}))
 ]};},
 forecastRoleAware:()=>{shadowCalls++;throw Error('shadow should not run');}
}};
const ctx=vm.createContext({window,Number,Intl,console});
for(const file of ['app/racer-rating.js','app/racer-rating-panel.js','app/race-visual.js'])
 vm.runInContext(fs.readFileSync(file,'utf8'),ctx,{filename:file});
const r={
 model_role:'main',model_version:'four-factor-v1.8-adaptive-points-primary-untrained',
 phase:'exhibition',
 entry_exhibition_gate:{final_eligible:true,entry_watch:false},
 racers:Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,name:'選手'+(i+1),
  national_win_rate:6.0+.1*i,motor_top_2_percent:30+i,
  average_start_timing:.14,exhibition_time:6.8,
 })),
 head_course_shares:[.40,.20,.15,.10,.09,.06].map((x,i)=>({
  lane:i+1,course:i+1,relative_share:x})),
 bets:[{combination:'1-2-3',virtual_yen:30000},
       {combination:'2-1-4',virtual_yen:20000}],
 interaction_primary:{
  role_evaluation_source:'same_final_ranked_120_as_primary_bets',
  main_role_shares:Object.fromEntries([.40,.20,.15,.10,.09,.06].map((f,i)=>[
   String(i+1),{first:f,second:[.10,.30,.15,.15,.15,.15][i],
                       third:[.10,.10,.20,.20,.20,.20][i]}])),
  ticket_role_counts:{
   '1':{first:1,second:1,third:0},'2':{first:1,second:1,third:0},
   '3':{first:0,second:0,third:1},'4':{first:0,second:0,third:1},
   '5':{first:0,second:0,third:0},'6':{first:0,second:0,third:0}
  }
 }
};
const untouched=JSON.stringify(r);
const result=window.BoatRacerRating.rate(r);
assert.equal(result.model,r.model_version);
assert.equal(result.byLane[1].role_weights.first,.40);
assert.equal(result.byLane[2].role_weights.second,.30);
assert.equal(result.byLane[1].race_expectation,100);
assert.equal(result.byLane[1].ticket_role_counts.first,1);
assert.equal(result.byLane[4].ticket_role_counts.third,1);
assert.equal(result.byLane[5].ticket_role_counts.first,0);
assert.equal(shadowCalls,0);
const ranking=window.BoatRaceVisual.predictionAdvantage(r);
assert.equal(ranking.status,'main');
assert.equal(ranking.ranks[1].rank,1);
assert.equal(ranking.ranks[4].rank,4);
assert.equal(shadowCalls,0);
const table=window.BoatRacerRatingPanel.render(r);
for(const word of ['正式メインの1着評価トップ','モデル評価1/2/3着','買い目採用1/2/3着','相対重みと採用点数']){
 assert.ok(table.includes(word),'Missing main-only table label: '+word);
}
const entry=window.BoatRaceVisual.entryHTML(r);
assert.match(entry,/正式メイン保存済み1着評価/);
assert.equal(JSON.stringify(r),untouched,'historical snapshot and bets must be immutable');
// Providing a bogus separate trial model can never override main ratings.
const falseTrial={role_coverage:Object.fromEntries(Array.from({length:6},(_,i)=>[
  i+1,{first:.01,second:.01,third:.01}])),
 head_course_shares:Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,relative_share:i===3?.8:.04}))};
const still=window.BoatRacerRating.rate(r,{forecast:falseTrial});
assert.equal(still.byLane[1].race_expectation,100);
assert.equal(shadowCalls,0);
// Missing main role values do NOT quietly fall back to shadow ratings.
const broken=JSON.parse(JSON.stringify(r));
delete broken.interaction_primary.main_role_shares;
assert.equal(window.BoatRacerRating.rate(broken).byLane[1].race_expectation,null);
assert.equal(shadowCalls,0);
console.log('Saved main ratings and bought-ticket role counts aligned: PASS');
