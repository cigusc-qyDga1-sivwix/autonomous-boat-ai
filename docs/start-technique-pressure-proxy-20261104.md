# Result-based ST × winning-technique proxy (2026-11-04)

The official result-side start timing, actual course, and winning technique can flag **possible** tactical interactions and races to review, but **cannot identify deliberate defensive marking or count its occurrences**. For example, an outer winner with an ST advantage may have simply accelerated earlier; close STs still cannot establish that an inner boat obstructed another.

`scripts/start_technique_pressure_proxy.py` parses BoatraceCSV-style realtime result rows in a research-only path. `interpret` yields per-inner-boat ST comparisons for outer makuri/makurizashi winners, separates invalid/missing/F starts, and explicitly sets `confirmed_mark_count=null` and `eligible_as_same_race_forecast_input=false`. `summarize` counts categories, not confirmed marks.

Source: https://boatracecsv.github.io/docs/data/results.html — realtime results contain 1st through 6th finishing lanes, winning technique, course-entry lane and start timing, including negative F and missing ST markers.

## Separation / next work
- **Historical labels**: collect with source SHA, official race identity, event date and result publication timestamp; never pass same-race labels into a pre-cutoff model.
- **Forward features**: aggregate past result proxies into racer/course priors using *race dates strictly before the forecast* and fit associations on earlier training windows. Current postrace result outputs remain isolated.
- **Causality**: only validated video/manual annotations can establish whether a boat actually blocked, marked, or occupied another path. Avoid subjective intent claims.
- **Validation**: compare an ST-only baseline, ST+winning-technique historical proxy, and video-labeled interactions on held-out future races. Monitor calibration and 3rd-place omissions, not only hit rate.
- **Data rights**: obey provider terms and minimize copying; don't scrape restricted feeds.
- **Status**: this PR adds analytical logic and unit tests, **not an automatic live fetch or formal prediction coefficient**.
