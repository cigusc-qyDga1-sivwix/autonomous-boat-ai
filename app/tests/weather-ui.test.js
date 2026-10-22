const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const base=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const fixture=JSON.parse(JSON.stringify(base));
const race=fixture.forecast_races.find(r=>r.racers?.length===6);
assert.ok(race);
fixture.venue_weather={[race.venue]:{
  wind_speed:7.3,wind_direction_degrees:245,wind_gust:12.2,
  precipitation_mm:1.5,air_temperature:22.1,
  forecast_hour_jst:fixture.event_date+'T16:00+09:00',
  site_observed:false,source:'open-meteo',
  issued_at_utc:'2026-10-22T06:00:00+00:00',
  source_label:'近隣気象予報'
}};
fixture.weather_venue_count=1;
fixture.weather_fixed_race_count=1;
fixture.weather_backtest={
  races:1,weather_hits:1,control_hits:0,weather_payout:51000,
  control_payout:0,virtual_stake_per_model:50000,
  weather_minus_control_yen:51000
};
race.weather_used={...fixture.venue_weather[race.venue],forecast_hour_jst:fixture.event_date+'T15:00+09:00'};
race.weather_adjustment={applied:true,why:'風速7.3m/sの試験補正'};
let elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast']){
 elements.set(id,{innerHTML:'',textContent:'',classList:{add(){},remove(){},toggle(){}},
 addEventListener(){},setAttribute(){},removeAttribute(){}});
}
const listeners={};
const document={hidden:false,getElementById:id=>elements.get(id),querySelectorAll:()=>[],
 addEventListener:(name,fn)=>{(listeners[name]||=[]).push(fn)}};
const localStorage={getItem(){return null},setItem(){},removeItem(){}};
const window={scrollTo(){}};
const context=vm.createContext({
  document,window,localStorage,
  fetch:async()=>({ok:true,json:async()=>fixture}),
  navigator:{},location:{protocol:'file:'},Date,Intl,console,setTimeout,clearTimeout,Blob,URL
});
vm.runInContext(fs.readFileSync('app/venue-board.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),context);
function click(targetSelector,attrs){
 const target={closest:s=>s===targetSelector?{dataset:attrs}:null};
 for(const cb of listeners.click||[])cb({target});
}
setTimeout(()=>{
 const home=elements.get('main').innerHTML;
 assert.match(home,/Weather data by Open-Meteo\.com/);
 assert.match(home,/周辺気象予報/);
 assert.match(home,/風7\.3m\/s/);
 click('[data-open-venue]',{openVenue:race.venue});
 const list=elements.get('main').innerHTML;
 assert.match(list,/最終取得時点の周辺予報/);
 assert.match(list,/気象補正試験/);
 assert.match(list,/風7\.3m\/s/);
 click('[data-race]',{race:race.venue+'|'+race.race});
 const detail=elements.get('main').innerHTML;
 assert.match(detail,/レース気象と試験補正/);
 assert.match(detail,/発走前に取得した周辺気象予報/);
 assert.match(detail,/風速7\.3m\/sの試験補正/);
 assert.match(detail,/Weather data by Open-Meteo\.com/);
 assert.match(detail,/降水量/);
 click('[data-view]',{view:'analysis'});
 const analysis=elements.get('main').innerHTML;
 assert.match(analysis,/気象補正あり・なしの発走前比較/);
 assert.match(analysis,/公式照合 <b>1R/);
 assert.match(analysis,/気象あり的中 <b>1R/);
 assert.match(analysis,/気象なし的中 <b>0R/);
 console.log('BOAT LAB all-venue weather UI and AB test: PASS');
},140);
