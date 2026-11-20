# BOAT LAB relative-wind research shadow v0.1

**Status:** research only, untrained, forward-only. No change to main 3連単,
virtual stakes, settlement, historical SHA, or formal model. Activates only on
newly generated pre-cutoff **exhibition** snapshots with an eligible six-boat
entry and on-site preview wind from `boatrace_preview`.

The source's `wind_direction_number` is **already relative to the
start-to-first-mark axis**, unlike real geographic bearings. Do not re-rotate
by venue's north/south direction. Official code definitions:
https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/codes.md

- Codes 3-7: tailwind; 11-15: headwind.
- 1, 2, 8-10, 16: crosswind; 17: calm. No score adjustment.
- Under 2 m/s, unknown, malformed, nearby forecasts, or other sources:
  no trial forecast. Never use result-stage weather.
- Actual six-course entry is distinct from frame number; F/invalid
  exhibition ST gets **no quick-start bonus**.
- 120 canonical outcomes are reweighted conservatively, bounded to 0.10
  log-score per outcome, then renormalized. Tailwind tests course-2 sashi
  and 1-2 retention; headwind tests course-3/4 attack and course-4
  follower. These are *hypotheses*, not measured causal factors.
- Generates alternate tickets using the same pre-cutoff
  `interaction_primary` policy; stores `relative_wind_shadow` with
  A/B ticket-change flags and timestamp. Formal `bets` are unchanged.
- Only compare like-for-like races with the same point count and virtual
  budget. Measure hit rate, first-place miss, second/third-place misses,
  ROI, sample size, venue and wind band; never call a backfilled estimate
  a forward result.

**Remaining validation:** Source API may publish previews with delay. The
collector freezes the response time before cutoff but does not independently
prove the provider's original observation time. Venue/course coefficients
and 2m/s threshold are provisional. Do not promote without sufficient
prospective evidence and verified data freshness.

Run offline: `python -m unittest discover -s tests -p test_relative_wind_shadow.py -v`
