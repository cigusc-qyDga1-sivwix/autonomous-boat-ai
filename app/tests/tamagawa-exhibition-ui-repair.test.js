// 2026-11-07 Tama 1R: research delivery must never hide independently
// frozen six-boat exhibition values. Visual/policy data stay separated.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const day='2026-11-07';
const racers=[
 [1,.18,6.60],[2,.14,6.62],[3,.07,6.73],
 [4,.01,6.70],[5,.04,6.70],[6,.09,6.62]
].map(([i,st,time])=>({lane:i,course:i,exhibition_st:st,exhibition_time:time}));
const race={
 venue:'多摩川',race:1,cutoff_jst:'10:30',phase:'exhibition',
 frozen_at_utc:'2026-11-07T01:25:00+00:00',
 sha256:'a'.repeat(64),
 classification:'WATCH',model_role:'main',model_version:'four-factor-v2.2-linked-primary-untrained',
 bets:[{combination:'1-2-3',virtual_yen:50000}],
 racers,
 entry_exhibition_gate:{final_eligible:true},
 exhibition_input_check:{verified_before_freeze:true},
 exhibition_origin:{source:'OpenAPI',observed_at_jst:'2026-11-07T10:20:00+09:00'}
};
const result={source:'boatrace_official_pay',verified:true,finish:'1-3-2',
 payout_per_100:1200,hit:false,snapshot_sha256:race.sha256};
const window={};
const ctx=vm.createContext({window,Date,Number,Map,Set,fetch:async url=>({
 ok:true,json:async()=>String(url).includes('status-latest')?
  {event_date:day,collected_at_utc:'2026-11-07T01:27:00+00:00',complete_sources:true}:
  {event_date:day,schema:'boatlabs.exhibition_research.v1',created_at_utc:'2026-11-07T01:27:22+00:00',records:[{
   race_code:'202611070501',source_observed_jst:'2026-11-07T10:20:22+09:00',
   boats:racers.map(b=>({lane:b.lane,course:b.course,exhibition_st:b.exhibition_st,
    exhibition_time:b.exhibition_time,original_exhibition:[]}))}]}
})});
vm.runInContext(fs.readFileSync('app/exhibition-audit.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/ticket-policy.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('app/venue-board.js','utf8'),ctx);

(async()=>{
 const audit=window.BoatExhibitionAudit;
 const early=audit.panel(race);
 assert.match(early,/展示6艇を正式予想へ反映済み/);
 assert.match(early,/6\.6/);
 assert.doesNotMatch(early,/研究記録にまだありません/);
 assert.equal(window.BoatTicketPolicy.classify(race,day).formal,true);
 const dataset={
  event_date:day,mode:'auto-live',forecast_races:[race],unforecast_races:[],
  official_results:{[day+'|多摩川|1']:result},venue_metadata:{多摩川:{grade:'一般'}},
  venue_weather:{}
 };
 const venue=window.BoatVenueBoard.renderVenue(dataset,'多摩川',{now:'10:35',favorites:[]});
 assert.match(venue,/公式 不的中/);
 assert.match(venue,/展示入力確認済/);
 assert.match(venue,/多摩川/);
 const before=JSON.stringify(race);
 await audit.load(day);
 const panel=audit.panel(race);
 assert.match(panel,/展示6艇を正式予想へ反映済み/);
 assert.match(panel,/取得済み展示（研究記録）/);
 assert.equal(JSON.stringify(race),before,'never edit frozen data from research');
 const baseline={...race,phase:'baseline',entry_exhibition_gate:{final_eligible:false}};
 const notFormal=audit.panel(baseline);
 assert.match(notFormal,/固定予想には未反映/);
 assert.doesNotMatch(notFormal,/展示6艇を正式予想へ反映済み/);
 const html=fs.readFileSync('app/index.html','utf8');
 const css=fs.readFileSync('app/styles.css','utf8');
 assert.match(html,/<details class="quick-links-menu">/);
 assert.match(html,/<button id="reload-btn"/);
 assert.match(html,/<nav class="bottom-nav"/);
 assert.match(css,/.quick-links-panel/);
 assert.match(css,/max-height:min\(75dvh,560px\)/);
 assert.ok((html.match(/<details class="quick-links-menu">/g)||[]).length===1);
 console.log('Tamagawa 1R frozen exhibition and responsive header regression PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
