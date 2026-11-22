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
// Cutoff at 11:00 JST remains visible until 11:10:00 (read-only).
const cutoff=Date.parse('2026-11-17T11:00:00+09:00');
const eleven={cutoff_jst:'11:00'};
assert.equal(v2.POST_CUTOFF_GRACE_MS,600000);
assert.equal(v2.recentCutoff(eleven,'2026-11-17',cutoff-1),false);
assert.equal(v2.visibleAroundCutoff(eleven,'2026-11-17',cutoff-1),true);
assert.equal(v2.recentCutoff(eleven,'2026-11-17',cutoff),true);
assert.equal(v2.recentCutoff(eleven,'2026-11-17',cutoff+599999),true);
assert.equal(v2.recentCutoff(eleven,'2026-11-17',cutoff+600000),true);
assert.equal(v2.recentCutoff(eleven,'2026-11-17',cutoff+600001),false);
assert.equal(v2.visibleAroundCutoff(eleven,'2026-11-17',cutoff+600001),false);
assert.equal(v2.visibleAroundCutoff({cutoff_jst:'invalid'},'2026-11-17',cutoff),false);
assert.equal(v2.recentCutoff(eleven,'2026-11-16',cutoff),false);
assert.equal(v2.sumBets(r),50000,'grace-period display never rewrites stakes');

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


// Verified official dividends, with exact yen accounting for frozen virtual stakes.
assert.deepEqual(v2.virtualSettlement(r,source),{stakeYen:50000,payoutYen:165000,profitYen:115000,officialPayoutPer100:550});
assert.deepEqual(v2.virtualSettlement(r,{...source,official_results:{[key]:{...official,finish:'3-1-4'}}}),
  {stakeYen:50000,payoutYen:0,profitYen:-50000,officialPayoutPer100:550});
assert.deepEqual(v2.virtualSettlement({...r,bets:[...r.bets,{combination:'1-3-4',virtual_yen:1000}]},source),
  {stakeYen:51000,payoutYen:170500,profitYen:119500,officialPayoutPer100:550});
assert.equal(v2.virtualSettlement({...r,bets:[{combination:'1-3-4',virtual_yen:105}]},source),null);
assert.equal(v2.virtualSettlement({...r,bets:[{combination:'1-3-4',virtual_yen:-100}]},source),null);
assert.equal(v2.virtualSettlement({...r,bets:[{combination:'1-3-4',virtual_yen:0}]},source),null);
assert.equal(v2.virtualSettlement({...r,bets:[{combination:'1-3-4',virtual_yen:100},{combination:'invalid',virtual_yen:100}]},source),null);
assert.equal(v2.virtualSettlement(r,{...source,official_results:{[key]:{...official,refunded_boats:[5]}}}),null);
assert.equal(v2.virtualSettlement(r,{...source,settlement_alerts:{[key]:{status:'conflict'}}}),null);
assert.equal(v2.virtualSettlement(r,{...source,official_results:{[key]:{...official,verified:false}}}),null);
assert.equal(v2.virtualSettlement({...r,bets:[{combination:'1-3-4',virtual_yen:9007199254740900}]},source),null);

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
assert.match(css,/\.v2-settlement-main strong/);
assert.match(js,/metric\('仮想払戻総額'/);
assert.match(js,/公式3連単配当（100円あたり）/);
assert.match(js,/virtualSettlement\(r,state\.data\)/);
assert.match(css,/@media\(max-width:760px\)/);
assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
assert.match(html,/class="v2-skip" href="#content"/);
assert.match(css,/\.v2-race-deadline strong\{font-size:25px/);
assert.match(css,/\.v2-bottom-nav button small\{font-size:13px/);
assert.match(css,/\.v2-filter-label select,\.v2-search\{min-height:44px;font-size:16px/);
assert.match(js,/v2-race-deadline/);
assert.match(js,/function dailyLearning\(\)/);
assert.match(js,/dailyLearning\(\)\+/);
assert.match(css,/\.v2-learning\{/);
assert.match(js,/head_focus_learning/);
assert.match(js,/研究・未採用/);
assert.match(js,/function venueWeatherLearning\(\)/);
assert.match(js,/function onsiteWeatherCaptureStatus\(\)/);
assert.match(js,/function previewFeatureCoverage\(\)/);
assert.match(js,/previewFeatureCoverage\(\)\+/);
assert.match(js,/exhibition-preview-evidence\/latest\.json/);
assert.match(js,/重量調整/);
assert.match(html,/20261117-postcutoff10-v1/);
assert.match(js,/fetch\('\.\/data\/weather-research\/latest\.json'/);
assert.match(js,/onsiteWeatherCaptureStatus\(\)\+/);
assert.match(html,/studio-v2\.js\?v=20261122-settlement-v1/);
assert.match(html,/cumulative-settlement\.css/);
assert.match(html,/cumulative-settlement\.js\?v=20261122-fast-v1/);
assert.ok(html.indexOf('cumulative-settlement.js')<html.indexOf('studio-v2.js'),
  'the read-only cumulative helper must load before the results page');
assert.match(js,/function cumulativeResults\(\)/);
assert.match(js,/function refreshCumulative\(force=false\)/);
assert.match(js,/refreshCumulative\(true\)/);
assert.match(js,/cumulativeResults\(\)\+/);
assert.match(js,/venueWeatherLearning\(\)\+/);
assert.match(js,/id="weather-venue-filter"/);
assert.match(js,/state.weatherVenue=e.target.value;render\(\)/);
assert.match(js,/venue_weather_learning/);
assert.match(js,/site_wave_time_verified/);
assert.match(css,/\.v2-weather-study\{/);
assert.match(css,/\.v2-weather-select select\{min-height:44px/);
assert.match(html,/20261117-postcutoff10-v1/);

assert.match(js,/phase==='shadow'\?'shadow':'pending'/);

assert.ok(js.includes('recent.slice(0,6).map(raceCard)'));
assert.ok(js.includes('recentShown.map(raceCard)'));
assert.ok(js.includes('visibleAroundCutoff(r,state.data.event_date,nowMs())'));
assert.match(js,/締切後10分｜保存済み予想/);
assert.match(js,/新規投票不可/);
assert.ok(css.includes('.v2-race.is-closed-recent{opacity:1'));
assert.ok(css.includes('.v2-recent-note'));
const homeSource=js.slice(js.indexOf('function home(){'),js.indexOf('function filterRaces(){'));
assert.ok(homeSource.indexOf('v2-section-heading')<homeSource.indexOf('v2-metrics'),'homepage displays near-term races before metrics');
assert.match(css,/--ink:#142a3e/);
assert.match(css,/--white:#fff/);
assert.match(js,/cache:'no-store'/);
assert.match(html,/canonical-exhibition-feed\.js\?v=20261116-canonical-v1/);
assert.ok(html.indexOf('canonical-exhibition-feed.js')<html.indexOf('studio-v2.js'),'canonical helper loads first');
assert.match(js,/const client=root\.BoatCanonicalExhibitionFeed;/);
assert.match(js,/client\.check\(\{current:state\.data\}\)/);
assert.match(js,/setInterval\(\(\)=>\{if\(!document\.hidden\)void pollCanonicalForecast\(\)\},60000\)/);
assert.match(js,/if\(!rollback\)\{state\.data=data;state\.source='Pages';\}/);
assert.match(js,/if\(state\.data\)void pollCanonicalForecast\(\)/);

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
