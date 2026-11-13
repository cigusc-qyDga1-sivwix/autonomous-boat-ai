'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {summarize}=require('../exhibition-evidence.js');
function stats(n,hits,payout){
 return {verified_races:n,hits,head_miss:n-hits,second_miss:0,third_miss:0,virtual_stake_yen:n*50000,virtual_payout_yen:payout};
}
function report(date='2026-11-13'){
 const withMetric=stats(2,1,65000),withoutMetric=stats(2,0,0);
 return {event_date:date,venue_metric_ablation:{
  protocol:'venue-shadow-v0.2-one-metric-removed',
  shadow_only_not_formal:true,read_only_official_result_audit:true,
  same_race_same_time_same_50000yen_budget:true,matched_point_count_only:true,
  verified_full_shadow_races:2,per_metric:{
   exhibition_time:{matched_verified_races:2,with_metric:withMetric,without_metric:withoutMetric,
    by_venue:{三国:{matched_verified_races:2,with_metric:withMetric,without_metric:withoutMetric}}},
   straight_time:{matched_verified_races:2,with_metric:withMetric,without_metric:withoutMetric,
    by_venue:{三国:{matched_verified_races:2,with_metric:withMetric,without_metric:withoutMetric}}}
  }
 }};
}
test('separate metric cohorts without double counting a race',()=>{
 const data=summarize([report()]);
 assert.equal(data.verifiedShadowRaces,2);
 assert.equal(data.metrics.exhibition_time.with.races,2);
 assert.equal(data.metrics.straight_time.with.races,2);
 assert.equal(data.metrics.exhibition_time.with.payout,65000);
 assert.equal(data.metrics.exhibition_time.without.payout,0);
 assert.equal(data.metrics.straight_time.byVenue.三国.with.hits,1);
});
test('deduplicate dates, add only distinct confirmed days',()=>{
 const data=summarize([report(),report(),report('2026-11-14')]);
 assert.equal(data.daysLoaded,2);
 assert.equal(data.skippedReports,1);
 assert.equal(data.verifiedShadowRaces,4);
 assert.equal(data.metrics.exhibition_time.with.races,4);
});
test('reject formal or mismatched-time comparisons and invalid stake',()=>{
 const invalid=report();
 invalid.venue_metric_ablation.shadow_only_not_formal=false;
 const bad=report('2026-11-14');
 bad.venue_metric_ablation.per_metric.exhibition_time.with_metric.virtual_stake_yen=1234;
 const data=summarize([invalid,bad]);
 assert.equal(data.daysApplicable,1);
 assert.equal(data.verifiedShadowRaces,2);
 assert.equal(data.metrics.exhibition_time,undefined);
 assert.equal(data.metrics.straight_time.with.races,2);
});
test('missing and malformed records never become losing races',()=>{
 const data=summarize([null,{event_date:'2026-11-13'},{event_date:'2026-11-14',venue_metric_ablation:{}}]);
 assert.equal(data.daysLoaded,2);
 assert.equal(data.daysApplicable,0);
 assert.equal(data.verifiedShadowRaces,0);
 assert.deepEqual(data.metrics,{});
});
