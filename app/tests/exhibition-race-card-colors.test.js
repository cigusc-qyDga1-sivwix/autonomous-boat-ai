'use strict';
/* Green cards are exclusively for formal pre-cutoff six-boat exhibitions.
 * A raw preview, a good result, or an experimental shadow must not colour
 * provisional, SKIP or late race forecasts as confirmed.
 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const racers=Array.from({length:6},(_,i)=>({
 lane:i+1,course:i+1,exhibition_st:.11+i*.01,exhibition_time:6.60+i*.01
}));
const base={
 venue:'多摩川',race:1,cutoff_jst:'11:30',phase:'exhibition',
 classification:'WATCH',model_role:'main',
 model_version:'four-factor-v2.2-linked-primary-untrained',
 sha256:'a'.repeat(64),frozen_at_utc:'2026-11-07T02:15:00Z',
 racers,bets:[{combination:'1-2-3',virtual_yen:50000}],
 scenario:'展示STと6艇展開を反映',
 entry_exhibition_gate:{final_eligible:true},
 exhibition_input_check:{verified_before_freeze:true}
};
function race(n,change={}){
 return {...base,race:n,cutoff_jst:['','11:30','11:45','12:00','12:15','12:30','12:45'][n],...change};
}
const records=[
 race(1),
 race(2,{phase:'baseline',entry_exhibition_gate:{final_eligible:false}}),
 race(3,{entry_exhibition_gate:{final_eligible:false}}),
 race(4,{classification:'SKIP'}),
 race(5,{exhibition_input_check:{verified_before_freeze:false}}),
 race(6,{frozen_at_utc:'2026-11-07T05:00:00Z'}),
];
const data={
 mode:'auto-live',event_date:'2026-11-07',forecast_races:records,unforecast_races:[],
 venue_metadata:{多摩川:{grade:'一般',event_day:3}},venue_weather:{},
 official_results:{'2026-11-07|多摩川|1':{
  source:'boatrace_official_pay',verified:true,hit:true,
  finish:'1-2-3',payout_per_100:800,snapshot_sha256:base.sha256}},
 updated_at_utc:'2026-11-07T02:15:00Z',
};
const before=JSON.stringify(data);
const win={};
const ctx=vm.createContext({window:win,Date,Number,Map,Set,Intl});
for(const path of ['app/ticket-policy.js','app/venue-board.js','app/race-timeline.js']){
 vm.runInContext(fs.readFileSync(path,'utf8'),ctx);
}
const formal=win.BoatTicketPolicy.classify(records[0],data.event_date);
assert.equal(formal.formal,true);
assert.equal(win.BoatTicketPolicy.classify(records[1],data.event_date).formal,false);
assert.equal(win.BoatTicketPolicy.classify(records[4],data.event_date).formal,true,
 'policy alone may not verify the input audit; card must require both');
const html=win.BoatVenueBoard.renderVenue(data,'多摩川',{now:'11:00',favorites:[]});
const attrs=[...html.matchAll(/class="venue-race(?: venue-race-(?:available|empty))?" data-exhibition-status="([^"]+)"/g)].map(m=>m[1]);
assert.equal(attrs.length,12,'All 12 slots remain visible');
assert.equal(attrs.filter(x=>x==='formal').length,1,'Only 1 verified formal exhibition');
assert.equal(attrs.filter(x=>x==='pending').length,5,'All other forecast cards are neutral');
assert.equal(attrs.filter(x=>x==='unavailable').length,6,'Missing forecasts must stay grey');
assert.match(html,/展示入力確認済/);
assert.match(html,/公式 的中/);
assert.equal(win.BoatVenueBoard.renderVenue({...data,mode:'manual'},'多摩川',{now:'11:00'}).includes('data-exhibition-status="formal"'),false,
 'Manual imports must not be marketed as canonical formal exhibition');
const timeline=win.BoatRaceTimeline.render(data,new Date('2026-11-07T02:00:00Z'));
assert.equal((timeline.match(/data-exhibition-status="formal"/g)||[]).length,1);
assert.match(timeline,/公式結果確認済/,'official result may take precedence over green colour');
assert.match(timeline,/6艇展示反映・正式予想固定/);
assert.equal((timeline.match(/data-exhibition-status="pending"/g)||[]).length,5);
assert.equal(JSON.stringify(data),before,'Read-only UI must not mutate SHA evidence');
const app=fs.readFileSync('app/app.js','utf8');
const style=fs.readFileSync('app/premium-ui.css','utf8');
assert.match(app,/class="race-tile" data-exhibition-status=/,
 'Nationwide race-list cards must also be colour keyed');
assert.match(app,/exhibitionFormal\?'formal':'pending'/);
assert.match(app,/exhibitionFormal\?'✅ 展示反映済'/);
assert.match(style,/\.venue-race\[data-exhibition-status="formal"\]/);
assert.match(style,/\.race-tile\[data-exhibition-status="formal"\]/);
assert.match(style,/\.timeline-race\[data-exhibition-status="formal"\]/);
assert.match(style,/#ddf9ef/);
console.log('Exhibition formal card colours: venue 12R, nationwide list, timeline, official result, SKIP, late, manual PASS');
