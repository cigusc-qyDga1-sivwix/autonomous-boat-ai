/* Stable local demo data for tests; never depend on today's GitHub live feed. */
const fs=require('node:fs');
const raw=JSON.parse(fs.readFileSync('app/data/2026-10-22.json','utf8'));
raw.mode='auto-live';
raw.updated_at_utc='2026-10-22T05:00:00+00:00';
raw.listed_races=raw.forecast_races.length;
raw.unforecast_races=[];
raw.venue_weather={};
raw.settlement_alerts={};
raw.official_pay_info={
  source_url:'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022',
  retrieved_at_utc:'2026-10-22T05:00:00+00:00',
  confirmed_forecast_results:1
};
for(const [i,r] of raw.forecast_races.entries()){
  r.phase='baseline';r.model_version='heuristic-0.2-untrained';
  r.sha256='fixed-test-hash-'+i;
  r.frozen_at_utc='2026-10-22T00:00:00+00:00';
  r.racers=Array.from({length:6},(_,j)=>({lane:j+1,course:j+1,name:'選手'+(j+1),
    national_win_rate:5.1,motor_top_2_percent:31,average_start_timing:.16}));
}
const sample=raw.forecast_races[0];
const key=raw.event_date+'|'+sample.venue+'|'+sample.race;
const first=sample.bets[0];
raw.official_results={
 [key]:{finish:first.combination,payout_per_100:2350,virtual_stake:50000,
   virtual_payout:first.virtual_yen*2350/100,source:'boatrace_official_pay',
   verified:true,snapshot_sha256:sample.sha256,
   recorded_at:'2026-10-22T05:00:00+00:00'}
};
module.exports=raw;
