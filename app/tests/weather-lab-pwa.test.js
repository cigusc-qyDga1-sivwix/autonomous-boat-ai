'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const UI=require('../weather/weather.js');
const dir=path.resolve(__dirname,'../weather');
const at=Date.parse('2026-11-05T00:38:00Z');
function race(mod={}){
 return {
   venue_code:'10',venue:'三国',race:3,race_code:'202611051003',
   cutoff_jst:'09:39',weather:{wind_mps:2,wave_cm:2,wind_direction_raw_code:4,air_c:13,water_c:15},
   source_captured_at_jst:'2026-11-05T09:32:00+09:00',
   weather_observed_at_jst:'2026-11-05T09:30:00+09:00',
   ...mod
 };
}
const venue={name:'三国',code:'10',race_snapshots:1};
const doc={schema:'weather_lab.water_surface_monitor.v1',event_date:'2026-11-05',
 collected_at_utc:'2026-11-05T00:35:00Z',provider:{fetch_status:'ok'},
 venues:Array.from({length:24},(_,i)=>({name:['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'][i],code:String(i+1).padStart(2,'0'),race_snapshots:i===9?1:0})),
 races:[race()]};
assert.equal(UI.quality(race(),at),'fresh','recent observation and capture are fresh');
assert.equal(UI.quality(race(),Date.parse('2026-11-05T04:00:00Z')),'stale','age is recalculated now; frozen collection status never wins');
assert.equal(UI.quality(race({weather_observed_at_jst:null}),at),'unknown');
assert.equal(UI.quality(race({weather:{wave_cm:null}}),at),'incomplete');
assert.equal(UI.quality(race({weather:{wave_cm:2}}),at),'fresh');
assert.equal(UI.quality(null,at),'missing');
assert.equal(UI.summary(doc,at).venues,1);
assert.equal(UI.summary(doc,at).fresh,1);
assert.equal(UI.summary(doc,Date.parse('2026-11-05T05:00:00Z')).fresh,0);
assert.equal(UI.venueView(doc.venues[2],doc,at).quality,'missing','no venue observations is not zero wind');
assert.equal(UI.venueView(venue,doc,at).quality,'fresh');
const card=UI.renderVenueCard(UI.venueView(venue,doc,at),null);
assert.match(card,/三国/);assert.match(card,/2/);assert.match(card,/新鮮/);
const empty=UI.renderVenueCard(UI.venueView(doc.venues[2],doc,at),null);
assert.match(empty,/データなし/);assert.match(empty,/BOAT LABの予想対象外/);
const output=UI.renderRace(race(),at);
assert.doesNotMatch(output,/風速/);
assert.match(output,/波高/);
assert.doesNotMatch(output,/風向コード/);
assert.doesNotMatch(output,/向かい風|追い風|潮流.+cm/,'unverified wind direction and tide must not be fabricated');
const stale=UI.renderRace(race(),Date.parse('2026-11-05T05:00:00Z'));
assert.match(stale,/古い記録は現在の状況を示しません/);
const escaped=UI.renderVenueCard(UI.venueView({...venue,name:'<img src=x onerror=alert(1)>'},doc,at),null);
assert.ok(!escaped.includes('<img'),'untrusted source text must be escaped');
assert.match(escaped,/&lt;img/);
const html=fs.readFileSync(path.join(dir,'index.html'),'utf8');
const css=fs.readFileSync(path.join(dir,'weather.css'),'utf8');
const sw=fs.readFileSync(path.join(dir,'service-worker.js'),'utf8');
const js=fs.readFileSync(path.join(dir,'weather.js'),'utf8');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.webmanifest'),'utf8'));
assert.match(html,/weather\.js/);assert.match(html,/weather\.css/);assert.match(html,/ホーム画面に追加/);
assert.equal(manifest.display,'standalone');assert.equal(manifest.scope,'./');
assert.match(css,/max-width:720px/);
assert.match(sw,/weather-lab-shell-/);
assert.match(sw,/url\.origin!==self\.location\.origin\)return/);
assert.match(js,/weather-lab-data\/weather_lab\/data\/latest\.json/);
assert.doesNotMatch(js,/boatlabs\.forecast|localStorage|autonomous_daily|BUY|10000000/);
const model={schema:'weather_lab.regional_jma_forecast.v1',event_date:'2026-11-05',
retrieved_at_utc:'2026-11-05T00:35:00Z',
venues:Array.from({length:24},(_,i)=>({code:String(i+1).padStart(2,'0'),model_current:{wind_mps:7,valid_at_jst:'2026-11-05T09:30:00+09:00'}}))};
assert.equal(UI.regionalEntry(model,'10',at).model.wind_mps,7);
assert.match(UI.renderVenueCard({...UI.venueView(venue,doc,at),regional:UI.regionalEntry(model,'10',at)},null),/場内実測ではない/);
const regionalCard=UI.renderVenueCard({...UI.venueView(venue,doc,at),regional:UI.regionalEntry(model,'10',at)},null);
assert.match(regionalCard,/regional-forecast/);
assert.match(regionalCard,/場内実測ではない/);
assert.match(regionalCard,/風 7m\/s/);
assert.match(html,/id="stat-regional"/);
assert.match(html,/weather\.js\?v=3/);
assert.match(sw,/CACHE=PREFIX\+"v3"/);
assert.match(js,/!it\.rows\.length&&!it\.regional/);
assert.match(js,/stat-regional/);
const tideDoc={schema:'weather_lab.jma_tide_reference.v1',event_date:'2026-11-05',stations:[
{station_code:'TK',station_name:'東京',high_tides:[{time_jst:'14:53',height_cm_datum:181}],low_tides:[{time_jst:'08:47',height_cm_datum:77}]}]};
assert.match(UI.tidePanel(tideDoc,at),/14:53 181cm/);
assert.match(UI.tidePanel(tideDoc,at),/流速・流向/);
assert.match(UI.tidePanel(null,at),/未取得/);
assert.match(js,/data\\/tide\\/latest\\.json/);
console.log('WEATHER LAB PWA UI tests passed (dynamic freshness, 24 sites, no fabricated values, independent installation)');
