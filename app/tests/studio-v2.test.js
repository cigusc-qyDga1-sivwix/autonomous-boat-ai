'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const v2=require('../studio-v2.js');
const policy=require('../ticket-policy.js');
const html=fs.readFileSync('app/studio-v2.html','utf8');
const css=fs.readFileSync('app/studio-v2.css','utf8');
const js=fs.readFileSync('app/studio-v2.js','utf8');

const sample={
  event_date:'2026-11-16',mode:'auto-live',updated_at_utc:'2026-11-16T09:20:00Z',
  forecast_races:[{
    venue:'若松',race:8,cutoff_jst:'18:45',classification:'WATCH',phase:'exhibition',
    sha256:'a'.repeat(64),frozen_at_utc:'2026-11-16T09:30:00Z',
    entry_exhibition_gate:{final_eligible:true},
    exhibition_input_check:{verified_before_freeze:true},
    racers:[1,2,3,4,5,6].map(i=>({lane:i,course:i,exhibition_st:.12,exhibition_time:6.83})),
    bets:[{combination:'1-3-4',virtual_yen:30000},{combination:'1-4-3',virtual_yen:20000}]
  }],
  official_results:{}
};
const r=sample.forecast_races[0];
assert.equal(v2.frozenStatus(r,sample,policy),true);
assert.equal(v2.racePhase(r,sample,policy),'formal');
assert.equal(v2.frozenStatus({...r,classification:'SKIP'},sample,policy),false);
assert.equal(v2.frozenStatus({...r,phase:'baseline'},sample,policy),false);
assert.equal(v2.frozenStatus({...r,exhibition_input_check:{}},sample,policy),false);
assert.equal(v2.frozenStatus({...r,entry_exhibition_gate:{final_eligible:false}},sample,policy),false);
assert.equal(v2.frozenStatus({...r,frozen_at_utc:'2026-11-16T09:44:59Z'},sample,policy),false);
assert.equal(v2.frozenStatus({...r,sha256:'wrong'},sample,policy),false);
assert.equal(v2.frozenStatus(r,{...sample,mode:'manual'},policy),false);
assert.equal(v2.frozenStatus(r,sample,null),false);
assert.equal(v2.sumBets(r),50000);
assert.equal(v2.money(50000),'50,000円');
assert.equal(v2.validCombo('1-3-4'),true);
assert.equal(v2.validCombo('1-1-3'),false);
assert.equal(v2.validClock('24:12'),false);
assert.equal(v2.jstDay(new Date('2026-11-15T15:30:00Z')),'2026-11-16');
assert.equal(v2.cutoffMs('2026-11-16','18:45')-Date.parse('2026-11-16T09:45:00Z'),0);
assert.equal(v2.normalize(sample).forecast_races.length,1);
assert.throws(()=>v2.normalize({...sample,mode:'manual'}),/正式な自動予想/);
assert.equal(v2.normalize({...sample,forecast_races:[]}).forecast_races.length,0);

const key=sample.event_date+'|'+r.venue+'|'+r.race;
const official={source:'boatrace_official_pay',verified:true,finish:'1-3-4',
  payout_per_100:550,snapshot_sha256:r.sha256};
const source={...sample,official_results:{[key]:official}};
assert.deepEqual(v2.officialOutcome(r,source),{
  finish:'1-3-4',hit:true,payoutPer100:550,source:'boatrace_official_pay'});
assert.equal(v2.officialOutcome(r,{...source,official_results:{[key]:{...official,finish:'3-1-4'}}}).hit,false);
assert.equal(v2.officialOutcome(r,{...source,official_results:{[key]:{...official,verified:false}}}),null);
assert.equal(v2.officialOutcome(r,{...source,official_results:{[key]:{...official,snapshot_sha256:'b'.repeat(64)}}}),null);
assert.equal(v2.officialOutcome(r,{...source,official_results:{[key]:{...official,refunded_boats:[5]}}}),null);
assert.equal(v2.officialOutcome(r,{...source,settlement_alerts:{[key]:{status:'conflict'}}}),null);
assert.equal(v2.officialOutcome(r,{...source,official_results:{[key]:{...official,source:'user_input'}}}),null);

assert.match(html,/<meta name="color-scheme" content="light">/);
assert.match(html,/name="apple-mobile-web-app-status-bar-style" content="black-translucent"/);
assert.match(html,/studio-v2\.css/);
assert.match(html,/studio-v2\.js/);
assert.match(html,/src="\.\/ticket-policy\.js"/);
assert.doesNotMatch(html,/src="\.\/app\.js"/);
assert.doesNotMatch(html,/premium-ui\.css|high-contrast-safe\.css|midnight-racing\.css/);
assert.match(html,/id="race-dialog"/);
assert.match(html,/data-tab="home"/);
assert.match(html,/data-tab="forecasts"/);
assert.match(html,/data-tab="results"/);
assert.match(html,/data-tab="research"/);
assert.match(css,/\.v2-bottom-nav/);
assert.match(css,/@media\(max-width:760px\)/);
assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
assert.match(html,/class="v2-skip" href="#content"/);
assert.match(css,/\.v2-race-deadline strong\{font-size:25px/);
assert.match(css,/\.v2-bottom-nav button small\{font-size:13px/);
assert.match(css,/\.v2-filter-label select,\.v2-search\{min-height:44px;font-size:16px/);
assert.match(js,/v2-race-deadline/);
assert.match(js,/phase==='shadow'\?'shadow':'pending'/);
const homeSource=js.slice(js.indexOf('function home(){'),js.indexOf('function filterRaces(){'));
assert.ok(homeSource.indexOf('v2-section-heading')<homeSource.indexOf('v2-metrics'),'homepage displays near-term races before metrics');
assert.match(css,/--ink:#142a3e/);
assert.match(css,/--white:#fff/);
assert.match(js,/cache:'no-store'/);
assert.match(js,/setInterval\(\(\)=>\{if\(!document\.hidden&&!state\.loading\)void load\(\)\},300000\)/);
assert.match(js,/document\.addEventListener\('visibilitychange'/);
assert.match(js,/showModal\(\)/);
assert.doesNotMatch(js,/fetch\([^)]*boatrace\.jp/);
assert.doesNotMatch(js,/localStorage\.setItem|fetch\([^)]*method:'POST'/);

// Contrast ratios are for NORMAL TEXT, not oversized decorative typography.
function lum(hex){
 const rgb=hex.replace('#','');
 const values=[0,2,4].map(i=>parseInt(rgb.slice(i,i+2),16)/255)
  .map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);
 return values[0]*.2126+values[1]*.7152+values[2]*.0722;
}
const ratio=(a,b)=>{const l=[lum(a),lum(b)].sort((x,y)=>y-x);return (l[0]+.05)/(l[1]+.05)};
for(const [label,fg,bg] of [
  ['ink on canvas','#142a3e','#f3f6fa'],
  ['body ink on white','#142a3e','#ffffff'],
  ['muted text on white','#506b7d','#ffffff'],
  ['confirmed chip','#075d49','#dcf6e8'],
  ['provisional chip','#7e4f0d','#fff0d0'],
  ['active tab','#ffffff','#0b6a64'],
  ['brand on navy','#ffffff','#101f34'],
  ['action button','#ffffff','#0b6871'],
]){
 assert.ok(ratio(fg,bg)>=4.5,label+' contrast below AA: '+ratio(fg,bg).toFixed(2));
}
console.log('BOAT LAB 2.0 preview: read-only model boundaries, official only, WCAG text contrast PASS');
