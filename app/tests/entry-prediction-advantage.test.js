const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const window={BoatTacticalModel:{forecast:()=>({
 head_course_shares:[
  {course:1,lane:4,relative_share:.38},
  {course:2,lane:1,relative_share:.22},
  {course:3,lane:5,relative_share:.17},
  {course:4,lane:2,relative_share:.11},
  {course:5,lane:6,relative_share:.07},
  {course:6,lane:3,relative_share:.05}
 ]})}};
const ctx=vm.createContext({window,Number,Intl});
vm.runInContext(fs.readFileSync('app/race-visual.js','utf8'),ctx);
const visual=window.BoatRaceVisual;
const source={
 venue:'鳴門',
 racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,
  name:'選手'+(i+1),national_win_rate:7.3-i/10,motor_top_2_percent:30+i*2})),
 bets:[{combination:'1-2-3',virtual_yen:50000}],
 entry_exhibition_gate:{final_eligible:true,entry_watch:false}
};
const frozen=JSON.stringify(source);
const rating=visual.predictionAdvantage(source);
assert.equal(rating.status,'trial');
assert.equal(rating.ranks[4].rank,1);
assert.equal(rating.ranks[4].mark,'◎');
assert.equal(rating.ranks[1].rank,2);
assert.equal(rating.ranks[5].mark,'▲');
assert.equal(rating.ranks[2].mark,'△');
assert.equal(rating.ranks[6].mark,'☆');
assert.equal(rating.ranks[3].mark,'－');
const html=visual.entryHTML(source);
assert.match(html,/boat-entry-advantage-1/);
assert.match(html,/boat-entry-top-advantage/);
assert.match(html,/AI優位/);
assert.match(html,/的中確率でもありません/);
for(const mark of ['◎','○','▲','△','☆','－'])assert.ok(html.includes(mark));
assert.equal((html.match(/boat-entry-advantage boat-entry-advantage-/g)||[]).length,6);
assert.equal(JSON.stringify(source),frozen,'do not change frozen predictions');
const watch={...source,entry_exhibition_gate:{entry_watch:true,final_eligible:false}};
assert.equal(visual.predictionAdvantage(watch).status,'hold');
assert.equal((visual.entryHTML(watch).match(/boat-entry-rank-pending/g)||[]).length,6);
assert.doesNotMatch(visual.entryHTML(watch),/boat-entry-advantage-1/);
const tentative={...source,entry_exhibition_gate:{final_eligible:false,entry_watch:false}};
assert.match(visual.entryHTML(tentative),/暫定順位/);
window.BoatTacticalModel.forecast=()=>({head_course_shares:[
 {lane:2,relative_share:.5},{lane:2,relative_share:.25},
 {lane:3,relative_share:.1},{lane:4,relative_share:.07},
 {lane:5,relative_share:.05},{lane:6,relative_share:.03}
]});
assert.equal(visual.predictionAdvantage(source).status,'unknown');
assert.equal((visual.entryHTML(source).match(/boat-entry-rank-pending/g)||[]).length,6);
window.BoatTacticalModel.forecast=()=>{throw Error('bad input')};
assert.equal(visual.predictionAdvantage(source).status,'unknown');
console.log('BOAT LAB six-lane entry advantage marks, forecast hygiene and pre-entry safety: PASS');
