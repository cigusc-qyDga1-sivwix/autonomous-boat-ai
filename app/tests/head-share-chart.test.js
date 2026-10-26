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
assert.ok(app.indexOf('BoatHeadShareChart?.render(r)')<app.indexOf('    ${ticketBlock}'),'chart immediately above main tickets');
const index=fs.readFileSync('app/index.html','utf8');assert.match(index,/head-share-chart\.css/);assert.match(index,/head-share-chart\.js/);
console.log('Head share pie: immutable saved values, 100% rounding, lane/course mapping, zero/missing guards, escaping and ticket placement: PASS');
