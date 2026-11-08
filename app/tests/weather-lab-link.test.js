'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const B=require('../weather-lab-link.js');

const day='2026-11-06';
const race={venue:'三国',race:3,cutoff_jst:'09:39'};
const evidence={
  race_code:'202611061003',venue_code:'10',race:3,
  collector_received_at_utc:'2026-11-06T00:28:00+00:00',
  source_captured_at_jst:'2026-11-06T09:26:00+09:00',
  weather_observed_at_jst:'2026-11-06T09:24:00+09:00',
  weather:{wave_cm:6},weather_evidence_sha256:'a'.repeat(64)
};
const feeds={
  frozen:{schema:B.SCHEMAS.frozen,event_date:day,records:[evidence]},
  wave:{schema:B.SCHEMAS.wave,event_date:day,races:[{
    venue_code:'10',race:3,weather:{wave_cm:9,wind_mps:15},
    weather_observed_at_jst:'2026-11-06T09:40:00+09:00'}]},
  regional:{schema:B.SCHEMAS.regional,event_date:day,
    retrieved_at_utc:'2026-11-06T00:25:00+00:00',
    venues:Array.from({length:24},(_,i)=>({
      code:String(i+1).padStart(2,'0'),
      hourly:[{valid_at_jst:'2026-11-06T10:00:00+09:00',wind_mps:7.45,air_c:18.8,
               wind_direction_degrees:292}],
    }))},
  tide:{schema:B.SCHEMAS.tide,event_date:day,stations:[
    {station_code:'TK',data_kind:'astronomical_tide_prediction_not_measured',on_course_station:false},
    {station_code:'OS',data_kind:'astronomical_tide_prediction_not_measured',on_course_station:false},
    {station_code:'ST',data_kind:'astronomical_tide_prediction_not_measured',on_course_station:false},
  ]},
};
assert.equal(B.nameCode('三国'),'10');
assert.equal(B.nameCode('江戸川'),'03');
assert.equal(B.nameCode('<script>'),null);
const verified=B.selectContext(feeds,race,day);
assert.equal(verified.valid,true);
assert.equal(verified.wave.cm,6,'first pre-cutoff wave witness wins over late latest reading');
assert.equal(verified.waveStatus,'precutoff_frozen');
assert.equal(verified.preCutoffEvidence,true);
assert.equal(verified.regional.wind_mps,7.45);
assert.equal(verified.regionalStatus,'model_retrieved_pre_cutoff');
assert.equal(verified.tideCount,3);
assert.equal(verified.flowStatus,'not_connected');
const html=B.renderContext(verified,race,day);
assert.match(html,/WEATHER LAB × BOAT LAB/);
assert.match(html,/波高/);
assert.match(html,/6cm/);
assert.match(html,/7.45m\/s/);
assert.match(html,/\.\/weather\/\?venue=10/);
assert.match(html,/場内との対応未検証/);
assert.match(html,/潮流の速さ・向き/);
assert.match(html,/正式買い目と評価には反映していません/);
assert.doesNotMatch(html,/(?:wind_mps|wind_direction_raw_code).*15/);

const withScenario=structuredClone(feeds);
withScenario.scenario={
  schema:B.SCHEMAS.scenario,event_date:day,
  records:[{
    race_code:'202611061003',venue_code:'10',race:3,
    recorded_at_utc:'2026-11-06T00:31:00+00:00',
    regional_retrieved_at_utc:'2026-11-06T00:25:00+00:00',
    wave_source_captured_at_jst:'2026-11-06T09:26:00+09:00',
    wave_observed_at_jst:'2026-11-06T09:24:00+09:00',
    nearby_model_wind_mps:7.45,on_course_wave_cm:6,
    status:'research_attention',
    signals:['nearby_model_wind_ge_6mps','on_course_wave_ge_5cm','wind_wave_joint_attention'],
    headwind_tailwind:'unverified_not_inferred',
    formal_prediction_modified:false,bets_changed:false,
    evidence_sha256:'b'.repeat(64),
  }],
};
const cue=B.selectContext(withScenario,race,day);
assert.equal(cue.scenarioStatus,'precutoff_research_only');
assert.equal(cue.scenario.attention,true);
assert.match(B.renderContext(cue,race,day),/気象展開チェック/);
assert.match(B.renderContext(cue,race,day),/買い目への自動補正なし/);
assert.match(B.renderContext(verified,race,day),/未固定/);
const lateScenario=structuredClone(withScenario);
lateScenario.scenario.records[0].recorded_at_utc='2026-11-06T00:39:00+00:00';
assert.equal(B.selectContext(lateScenario,race,day).scenario,null);
const tampered=structuredClone(withScenario);
tampered.scenario.records[0].signals=['fake_direction_bias'];
assert.equal(B.selectContext(tampered,race,day).scenario,null);
const late=structuredClone(feeds);
late.frozen.records[0].collector_received_at_utc='2026-11-06T00:39:00+00:00';
late.regional.retrieved_at_utc='2026-11-06T00:40:00+00:00';
const after=B.selectContext(late,race,day);
assert.equal(after.waveStatus,'reference_unfrozen');
assert.equal(after.wave.cm,9);
assert.equal(after.regionalStatus,'model_reference_after_cutoff');
assert.match(B.renderContext(after,race,day),/事前予想の根拠にはできません/);
const wrongDate=structuredClone(feeds);
wrongDate.wave.event_date='2026-11-05';
wrongDate.regional.event_date='2026-11-05';
wrongDate.tide.event_date='2026-11-05';
wrongDate.frozen.event_date='2026-11-05';
const missing=B.selectContext(wrongDate,race,day);
assert.equal(missing.wave,null);
assert.equal(missing.regional,null);
assert.equal(missing.tideCount,0);
assert.equal(missing.preCutoffEvidence,false);
const bad=structuredClone(feeds);
bad.frozen.records[0].weather.wave_cm=null;
assert.equal(B.selectContext(bad,race,day).waveStatus,'reference_unfrozen');
assert.equal(B.selectContext(feeds,{venue:'三国',race:3,cutoff_jst:'invalid'},day).valid,false);
assert.equal(B.selectContext(feeds,{venue:'不明',race:3,cutoff_jst:'09:39'},day).valid,false);
const app=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const controller=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
const weather=fs.readFileSync(path.join(__dirname,'../weather/weather.js'),'utf8');
assert.match(app,/weather-lab-link\.js/);
assert.match(app,/href="\.\/weather\/"/);
assert.ok(app.indexOf('weather-lab-link.js')<app.indexOf('app.js?v='),'bridge is available before app controller');
assert.match(controller,/BoatWeatherLabLink\?\.mount\(main,state\.raceDetail,data\.event_date\)/);
assert.match(weather,/requestedVenue/);
console.log('WEATHER LAB linked read-only to BOAT LAB race details (4 source + cutoff gates)');
