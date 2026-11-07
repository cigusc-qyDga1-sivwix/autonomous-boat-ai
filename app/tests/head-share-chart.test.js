'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const chart=require('../head-share-chart.js');
const fixture=()=>({venue:'唐津',race:1,phase:'baseline',sha256:'a'.repeat(64),
 racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,name:'選手'+(i+1)})),
 head_course_shares:[.541,.0662,.0751,.0092,.3041,.0044].map((share,i)=>({lane:i+1,course:i+1,relative_share:share}))});
const r=fixture(),before=JSON.stringify(r),rows=chart.data(r);
assert.equal(rows.length,6);assert.ok(Math.abs(rows.reduce((n,x)=>n+x.percent,0)-100)<1e-10);
assert.equal(rows[0].percent,54.1);assert.equal(rows[4].percent,30.4);
const html=chart.render(r);assert.match(html,/実際の1着確率・的中率ではありません/);assert.match(html,/展示前・暫定/);
assert.match(html,/role="img"/);assert.match(html,/<desc /);assert.match(html,/1号艇/);assert.match(html,/6号艇/);
assert.equal((html.match(/<li>/g)||[]).length,6);assert.equal(JSON.stringify(r),before);
const betting=fixture();betting.bets=[{combination:'6-5-4',virtual_yen:50000}];assert.deepEqual(chart.data(betting),rows,'never use selected bets as head probabilities');
const swapped=fixture();[swapped.racers[0].course,swapped.racers[5].course]=[6,1];
[swapped.head_course_shares[0].course,swapped.head_course_shares[5].course]=[6,1];
assert.equal(chart.data(swapped)[0].lane,1);assert.equal(chart.data(swapped)[0].course,6);assert.equal(chart.data(swapped)[0].name,'選手1');
const reversed=fixture();reversed.head_course_shares.reverse();reversed.racers.reverse();assert.deepEqual(chart.data(reversed),rows);
for(const mutate of [x=>delete x.head_course_shares,x=>x.head_course_shares.pop(),x=>x.head_course_shares[0].relative_share=-.1,
 x=>x.head_course_shares[0].relative_share=NaN,x=>x.head_course_shares[0].relative_share='0.541',
 x=>x.head_course_shares[0].lane=2,x=>x.head_course_shares[0].course=2,x=>x.racers[0].course=6,
 x=>x.head_course_shares[0]=null,x=>x.racers[0]=null,x=>x.sha256='missing',x=>x.head_course_shares.forEach(r=>r.relative_share=0),x=>x.head_course_shares.forEach(r=>r.relative_share=.5)]){
 const bad=fixture();mutate(bad);assert.equal(chart.data(bad),null);assert.match(chart.render(bad),/表示できません/);
}
const equal=fixture();equal.head_course_shares.forEach(x=>x.relative_share=.1667);
assert.ok(Math.abs(chart.data(equal).reduce((n,x)=>n+x.percent,0)-100)<1e-10,'rounded source shares total 100.0%');
const one=fixture();one.head_course_shares.forEach((x,i)=>x.relative_share=i===2?1:0);
assert.equal(chart.data(one)[2].percent,100);assert.equal((chart.render(one).match(/<li>/g)||[]).length,6);
assert.match(chart.render(one),/0\.0<small>％/);assert.doesNotMatch(chart.render(one),/NaN|Infinity/);
const unsafe=fixture();unsafe.racers[0].name='<script>alert(1)</script>';
assert.ok(chart.render(unsafe).includes('&lt;script&gt;'));assert.ok(!chart.render(unsafe).includes('<script>'));
const expo=fixture();expo.phase='exhibition';assert.match(chart.render(expo),/展示情報反映/);
assert.match(chart.render(expo),/実際の1着確率・的中率ではありません/);
const live=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
for(const race of live.forecast_races){
 if(!race.head_course_shares)continue;
 const data=chart.data(race);assert.ok(data,'saved input accepted: '+race.venue+race.race);
 assert.ok(Math.abs(data.reduce((n,x)=>n+x.percent,0)-100)<1e-9);
}
const app=fs.readFileSync('app/app.js','utf8');
assert.ok(app.indexOf('    ${ticketBlock}')>=0&&
 app.indexOf('    ${ticketBlock}')<app.indexOf('BoatHeadShareChart?.render(r)'),
 'formal tickets must be visible before the long rating chart on mobile');
const index=fs.readFileSync('app/index.html','utf8');assert.match(index,/head-share-chart\.css/);assert.match(index,/head-share-chart\.js/);
console.log('Head share pie: immutable saved values, 100% rounding, lane/course mapping, zero/missing guards, escaping and ticket placement: PASS');
const mismatched=fixture();
mismatched.bets=[{combination:'5-1-2',virtual_yen:30000},{combination:'1-5-2',virtual_yen:20000}];
const saved=JSON.stringify(mismatched),summary=chart.ticketSummary(mismatched);
assert.equal(summary.leadersDiffer,true);
assert.deepEqual(summary.ratingLeaders,[1]);assert.deepEqual(summary.stakeLeaders,[5]);
assert.equal(summary.rows[0].percent,54.1,'raw rating must never be rewritten as 40% stake');
assert.equal(summary.rows[0].headCount,1);assert.equal(summary.rows[0].stake,20000);
assert.equal(summary.rows[0].stakePercent,40);assert.equal(summary.rows[4].stakePercent,60);
const compared=chart.render(mismatched);
for(const text of ['評価1位','頭の配分最多','同じ保存予想','54.1％','20,000円','40.0％','30,000円','60.0％','2・3着の条件と点数制限'])assert.ok(compared.includes(text),text);
assert.equal(JSON.stringify(mismatched),saved);
const tied=structuredClone(mismatched);tied.bets.forEach(b=>b.virtual_yen=25000);
assert.equal(chart.ticketSummary(tied).leadersDiffer,false,'equal top stakes do not count as an inversion');
for(const mutate of [r=>r.bets[0].virtual_yen=NaN,r=>r.bets[0].virtual_yen=30001,
 r=>r.bets[0].combination='5-5-2',r=>r.bets.push({...r.bets[0]}),r=>delete r.bets]){
 const bad=structuredClone(mismatched);mutate(bad);
 assert.equal(chart.ticketSummary(bad),null);assert.match(chart.render(bad),/比較は保留/);
}
const primary=structuredClone(mismatched);primary.model_role='main';
primary.interaction_primary={role_evaluation_source:'same_final_ranked_120_as_primary_bets',
 main_role_shares:Object.fromEntries(primary.head_course_shares.map(x=>[x.lane,{first:x.relative_share}])),
 ticket_role_counts:Object.fromEntries(Array.from({length:6},(_,i)=>[i+1,{first:[1,0,0,0,1,0][i]}]))};
assert.equal(chart.data(primary)[0].percent,54.1);assert.ok(chart.ticketSummary(primary));
const contradictory=structuredClone(primary);contradictory.interaction_primary.main_role_shares['1'].first=.9;
assert.equal(chart.data(contradictory),null,'contradictory primary source must not silently display');
const absentRole=structuredClone(primary);delete absentRole.interaction_primary.main_role_shares;
assert.equal(chart.data(absentRole),null);
const staleCounts=structuredClone(primary);staleCounts.interaction_primary.ticket_role_counts['1'].first=8;
assert.equal(chart.ticketSummary(staleCounts),null,'do not display stale saved ticket counts');
let inversions=0;
for(const race of live.forecast_races){
 const actual=chart.ticketSummary(race);assert.ok(actual,'valid live comparison: '+race.venue+race.race);
 if(actual.leadersDiffer)inversions++;
 assert.equal(actual.rows.reduce((s,x)=>s+x.headCount,0),race.bets.length);
 assert.equal(actual.rows.reduce((s,x)=>s+x.stake,0),50000);
}
console.log('Head chart comparison: distinct rating/stake, ties, primary-source conflicts and actual ticket totals PASS; live inversions='+inversions);
