'use strict';
const assert=require('node:assert/strict');
const bridge=require('../../scripts/main_four_factor_bridge.js');
const model=globalThis.BoatTacticalModel;
assert.equal(model.ticketMaxPoints({frozen_at_utc:'2026-10-28T14:59:59Z'}),12);
assert.equal(model.ticketMaxPoints({frozen_at_utc:'2026-10-28T15:00:00Z'}),20);
assert.equal(model.ticketMaxPoints({}),12);
const input={
 "venue": "三国",
 "phase": "exhibition",
 "frozen_at_utc": "2026-10-29T00:00:00Z",
 "weather_used": {
  "wind_speed": 10,
  "wave_height": 10
 },
 "racers": [
  {
   "lane": 1,
   "course": 1,
   "national_win_rate": 3.850201426073909,
   "motor_top_2_percent": 38.9635287609417,
   "average_start_timing": 0.1041707951342687,
   "exhibition_time": 6.941816172096878,
   "exhibition_st": 0.029143372736871245
  },
  {
   "lane": 2,
   "course": 2,
   "national_win_rate": 5.992960879346356,
   "motor_top_2_percent": 50.71623699972406,
   "average_start_timing": 0.1970900488900952,
   "exhibition_time": 6.730770617723465,
   "exhibition_st": 0.12844666983000935
  },
  {
   "lane": 3,
   "course": 3,
   "national_win_rate": 6.507809771690518,
   "motor_top_2_percent": 42.6839411619585,
   "average_start_timing": 0.2303928058128804,
   "exhibition_time": 6.7880156817846,
   "exhibition_st": 0.04857485024258495
  },
  {
   "lane": 4,
   "course": 4,
   "national_win_rate": 5.4953408318106085,
   "motor_top_2_percent": 43.64886592142284,
   "average_start_timing": 0.19347243743250148,
   "exhibition_time": 6.718206747807562,
   "exhibition_st": 0.09066078593023122
  },
  {
   "lane": 5,
   "course": 5,
   "national_win_rate": 7.797852816991508,
   "motor_top_2_percent": 34.98379857861437,
   "average_start_timing": 0.18824905913788825,
   "exhibition_time": 6.734857838321477,
   "exhibition_st": 0.1688796229660511
  },
  {
   "lane": 6,
   "course": 6,
   "national_win_rate": 3.0407790194731206,
   "motor_top_2_percent": 47.144098521675915,
   "average_start_timing": 0.15937502136221154,
   "exhibition_time": 6.980915016308426,
   "exhibition_st": 0.1309739866759628
  }
 ],
 "venue_tactics_trial": true
};
const original=structuredClone(input);
const result=bridge.run(input);
assert(result.bets.length>12&&result.bets.length<=20);
assert.deepEqual(result.four_factor.ticket_bounds,{min:4,max:20,effective_from_jst:'2026-10-29'});
assert.equal(result.bets.reduce((n,b)=>n+b.virtual_yen,0),50000);
assert(result.bets.every(b=>b.virtual_yen>=1000&&b.virtual_yen%1000===0));
assert.deepEqual(input,original);
const before=bridge.run({...input,frozen_at_utc:'2026-10-28T14:59:59Z'});
assert(before.bets.length<=12);
assert.equal(before.four_factor.ticket_bounds,undefined);
const all=[];for(let a=1;a<=6;a++)for(let b=1;b<=6;b++)for(let c=1;c<=6;c++)if(new Set([a,b,c]).size===3)all.push(`${a}-${b}-${c}`);
const bets=all.slice(0,20).map((combination,i)=>({combination,virtual_yen:i<10?3000:2000}));
assert(bridge.validBets(bets,20));assert(!bridge.validBets(bets));
assert(!bridge.validBets([...bets,{combination:all[20],virtual_yen:1000}],20));
console.log('Ticket bound JST boundary, >12 generation, bridge allocation and historical compatibility: PASS');
