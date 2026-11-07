'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const policy=require('../ticket-policy.js');
const win={BoatTicketPolicy:policy};
const context=vm.createContext({window:win,Intl,Date});
vm.runInContext(fs.readFileSync('app/ui-console.js','utf8'),context);
const ui=win.BoatLabUIConsole;
assert.ok(ui?.render,'Race Desk renderer must load');

const day='2026-11-07';
const six=Array.from({length:6},(_,i)=>({
  lane:i+1,course:i+1,exhibition_st:.13,exhibition_time:6.7+i*.01
}));
const base={
  venue:'多摩川',race:1,cutoff_jst:'10:30',phase:'exhibition',
  classification:'WATCH',sha256:'a'.repeat(64),
  frozen_at_utc:'2026-11-07T01:23:00+00:00',
  racers:six,bets:[{combination:'1-2-3',virtual_yen:50000}],
  entry_exhibition_gate:{final_eligible:true},
};
const provisional={
  ...base,race:2,cutoff_jst:'10:45',phase:'baseline',
  frozen_at_utc:'2026-11-07T01:20:00+00:00',sha256:'b'.repeat(64)
};
const skipped={
  ...base,race:3,cutoff_jst:'10:50',classification:'SKIP',
  frozen_at_utc:'2026-11-07T01:21:00+00:00',sha256:'c'.repeat(64)
};
const data={
  mode:'auto-live',event_date:day,
  updated_at_utc:'2026-11-07T01:22:30+00:00',
  forecast_races:[base,provisional,skipped],
  official_results:{
    [day+'|多摩川|1']:{
      source:'boatrace_official_pay',verified:true,
      finish:'1-3-2',snapshot_sha256:base.sha256}
  },
  settlement_alerts:{}
};
const now=new Date('2026-11-07T01:25:00+00:00'); // 10:25 JST
const before=JSON.stringify(data);
const s=ui.summarize(data,now,policy);
assert.equal(s.current,true);
assert.equal(s.forecast,3);
assert.equal(s.formal,1,'SKIP and pre-exhibition are not formal');
assert.equal(s.frozenExhibition,2,'stored exhibition and formal tickets differ');
assert.equal(s.verified,1,'official result checks do not imply prediction eligibility');
assert.equal(s.progress,33);
assert.equal(s.freshness,'recent');
assert.deepEqual(Array.from(s.upcoming,x=>x.race),[1,2]);
const html=ui.render(data,now,policy);
assert.match(html,/今日のレースデスク/);
assert.match(html,/展示後の正式買い目/);
assert.match(html,/展示版の固定予想/);
assert.match(html,/公式結果照合済み/);
assert.match(html,/aria-valuenow="33"/);
assert.match(html,/data-race="多摩川\|1"/);
assert.match(html,/data-race="多摩川\|2"/);
assert.match(html,/正式未確定/);
assert.match(html,/展示反映/);
assert.match(html,/実投票|正式買い目/);
assert.equal(JSON.stringify(data),before,'UI must never mutate forecast or official result');

const noPolicy=ui.summarize(data,now,null);
assert.equal(noPolicy.formal,0,'without proof policy, fail closed');
const falseGate={...data,forecast_races:[
  {...base,entry_exhibition_gate:{final_eligible:false}},
  provisional,skipped]};
assert.equal(ui.summarize(falseGate,now,policy).formal,0,
  'explicit entry-exhibition failure blocks the formal dashboard claim');
const falseInput={...data,forecast_races:[
  {...base,exhibition_input_check:{verified_before_freeze:false}},
  provisional,skipped]};
assert.equal(ui.summarize(falseInput,now,policy).formal,0,
  'explicit six-boat input audit failure blocks the formal claim');
assert.match(ui.render({...data,forecast_races:[skipped]},now,policy),
  /SKIP・研究用/, 'SKIP must not be described as just awaiting exhibition');
assert.doesNotMatch(ui.render(data,now,null),/bl-desk-race-state is-formal/);
const conflict={...data,settlement_alerts:{[day+'|多摩川|1']:{reason:'correction'}}};
assert.equal(ui.summarize(conflict,now,policy).verified,0,'reviewed official results are not verified');
const stale=ui.summarize(data,new Date('2026-11-08T01:25:00Z'),policy);
assert.equal(stale.current,false);
assert.equal(stale.freshness,'old');
assert.equal(stale.upcoming.length,0);
assert.match(ui.render(data,new Date('2026-11-08T01:25:00Z'),policy),/過去日の記録/);
const imported=ui.summarize({...data,mode:'manual'},now,policy);
assert.equal(imported.freshness,'import');

const xss={...data,forecast_races:[{
  ...provisional,venue:'<img src=x onerror=alert(1)>',race:1
}]};
assert.doesNotMatch(ui.render(xss,now,policy),/<img src=x onerror/);
assert.match(ui.render(xss,now,policy),/&lt;img/);
const index=fs.readFileSync('app/index.html','utf8');
const app=fs.readFileSync('app/app.js','utf8');
const sw=fs.readFileSync('app/service-worker.js','utf8');
const style=fs.readFileSync('app/premium-ui.css','utf8');
assert.match(index,/premium-ui\.css\?v=20261107-exhibition-colors-v1/);
assert.match(index,/ui-console\.js\?v=20261107-racedesk-v1/);
assert.match(app,/BoatLabUIConsole\?\.render\(data\)/);
assert.match(app,/state\.view==='overview'/);
assert.match(app,/<div class="tablewrap"><table class="bets-table">/);
assert.match(sw,/boat-lab-static-v69/);
assert.match(sw,/\.\/ui-console\.js/);
assert.match(sw,/\.\/premium-ui\.css/);
assert.match(style,/@media\(max-width:370px\)/);
assert.match(style,/prefers-reduced-motion/);
assert.match(style,/bl-desk-stat-hero/);
assert.match(style,/ticket-status-pending/);
console.log('BOAT LAB premium Race Desk: source-safe, no hindsight, mobile CSS and navigation PASS');
