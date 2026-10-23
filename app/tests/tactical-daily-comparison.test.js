const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const scope={window:{}};vm.runInNewContext(fs.readFileSync('app/tactical-1m.js','utf8'),scope);
const model=scope.window.BoatTacticalModel;
const fixture=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const rows=fixture.forecast_races;
assert.ok(rows.length>30,'Need meaningful daily saved races');
const source=JSON.stringify(rows);
let different=0,alternativeHeads=0,researchTopOtherThan1=0,oldTopOtherThan1=0,nonInsideHeads=0;
const topVenues={};
for(const r of rows){
 const trial=model.forecast(r);
 if(trial.differs_from_frozen)different++;
 if(trial.top[0]!=='1'){researchTopOtherThan1++;topVenues[r.venue]=(topVenues[r.venue]||0)+1;}
 if(r.bets[0].combination[0]!=='1')oldTopOtherThan1++;
 if(trial.bets.some(b=>b.head_course!==1)){alternativeHeads++;}
 nonInsideHeads+=trial.bets.filter(b=>b.head_course!==1).length;
 assert.equal(trial.bets.reduce((s,b)=>s+b.virtual_yen,0),50000);
 assert.ok(trial.bets.length>=4&&trial.bets.length<=12);
}
assert.equal(JSON.stringify(rows),source,'cannot rewrite frozen forecast evidence');
assert.ok(different>=10,'the new experiment must differ from at least ten old tickets');
assert.ok(alternativeHeads>rows.length*.5,'must evaluate outside first-turn head paths regularly');
console.log('Daily tactical comparison: '+JSON.stringify({total:rows.length,different,alternativeHeads,
  nonInsideHeads,researchTopOtherThan1,oldTopOtherThan1,topVenues}));
