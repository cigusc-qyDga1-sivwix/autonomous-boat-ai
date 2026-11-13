/* BOAT LAB: prospective exhibition metric ablation evidence (research only).
 * Only compare same-race/same-time/same-budget verified SHADOW pairs.
 * No prediction mutation, odds, results feedback, or auto promotion.
 */
(function (root) {
  'use strict';
  const NAMES = Object.freeze({
    exhibition_time: '展示タイム',
    lap_time: '一周タイム',
    half_lap_time: '半周ラップ',
    turn_time: 'まわり足',
    straight_time: '直線タイム'
  });
  const TARGET = 100;
  function fresh() {
    return { races:0, hits:0, headMiss:0, secondMiss:0, thirdMiss:0, stake:0, payout:0 };
  }
  function validStats(s, n) {
    return s && typeof s === 'object' &&
      Number.isSafeInteger(s.verified_races) && s.verified_races === n &&
      Number.isSafeInteger(s.hits) && s.hits >= 0 && s.hits <= n &&
      Number.isSafeInteger(s.virtual_stake_yen) &&
      s.virtual_stake_yen === n * 50000 &&
      Number.isSafeInteger(s.virtual_payout_yen) && s.virtual_payout_yen >= 0 &&
      ['head_miss','second_miss','third_miss'].every(k=>
        Number.isSafeInteger(s[k]) && s[k] >= 0 && s[k] <= n);
  }
  function add(dest, data) {
    dest.races += data.verified_races;
    dest.hits += data.hits;
    dest.headMiss += data.head_miss;
    dest.secondMiss += data.second_miss;
    dest.thirdMiss += data.third_miss;
    dest.stake += data.virtual_stake_yen;
    dest.payout += data.virtual_payout_yen;
  }
  function newMetric() {
    return { with: fresh(), without: fresh(), byVenue: {}, days:0 };
  }
  function summarize(reports) {
    const result={daysLoaded:0,daysApplicable:0,skippedReports:0,
      verifiedShadowRaces:0,metrics:{},latestDate:null,target:TARGET};
    const seen=new Set();
    for (const report of reports) {
      const date=report?.event_date;
      if (typeof date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(date)||seen.has(date)) {
        result.skippedReports++;continue;
      }
      seen.add(date);
      result.daysLoaded++;
      if (!result.latestDate || date>result.latestDate)result.latestDate=date;
      const a=report.venue_metric_ablation;
      if (!a || a.protocol!=='venue-shadow-v0.2-one-metric-removed' ||
          a.shadow_only_not_formal!==true || a.read_only_official_result_audit!==true ||
          a.same_race_same_time_same_50000yen_budget!==true ||
          a.matched_point_count_only!==true || !a.per_metric ||
          !Number.isSafeInteger(a.verified_full_shadow_races) ||
          a.verified_full_shadow_races<0)continue;
      result.daysApplicable++;
      // Day-level count is unique across metrics; NEVER sum per-metric race totals.
      result.verifiedShadowRaces+=a.verified_full_shadow_races;
      for (const [key,row] of Object.entries(a.per_metric)) {
        if (!Object.hasOwn(NAMES,key)||!Number.isSafeInteger(row?.matched_verified_races)||
            row.matched_verified_races<=0)continue;
        const n=row.matched_verified_races;
        if (!validStats(row.with_metric,n)||!validStats(row.without_metric,n))continue;
        if (!result.metrics[key])result.metrics[key]=newMetric();
        const dst=result.metrics[key];
        add(dst.with,row.with_metric);add(dst.without,row.without_metric);dst.days++;
        for (const [venue,sub] of Object.entries(row.by_venue||{})) {
          if (!venue || venue==='江戸川' || !Number.isSafeInteger(sub?.matched_verified_races) ||
              sub.matched_verified_races<=0 ||
              !validStats(sub.with_metric,sub.matched_verified_races) ||
              !validStats(sub.without_metric,sub.matched_verified_races))continue;
          if (!dst.byVenue[venue])dst.byVenue[venue]={with:fresh(),without:fresh()};
          add(dst.byVenue[venue].with,sub.with_metric);
          add(dst.byVenue[venue].without,sub.without_metric);
        }
      }
    }
    return result;
  }
  root.BoatExhibitionEvidence={summarize,NAMES,TARGET};
  if (typeof module!=='undefined'&&module.exports)module.exports=root.BoatExhibitionEvidence;
})(typeof window!=='undefined'?window:globalThis);
