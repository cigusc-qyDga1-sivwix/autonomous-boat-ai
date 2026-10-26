# Venue layout experiment v1.2 — 2026-10-27

**Scope: Toda, Fukuoka and Karatsu ONLY. Edogawa excluded.** No automatic promotion to main.

- **Toda:** Official summer 2026 course-specific first-place distribution is blended at 35% with the existing weak prior (trial only). 3rd/4th course head weight gets an additional capped 5% only if estimated pre-race ST, go and turn evidence support a center attack. Source: https://www.boatrace-toda.jp/data/suimen_guide.html
- **Fukuoka:** Officially documented one-mark offset and narrow inner lane motivate the same conditional center attack test. **No tidal coefficient** because measured tide data have not been connected. Source: https://www.boatrace.jp/owpc/pc/site/place/stadium/br22/index.html
- **Karatsu:** Pit layout changed in December 2025; enter by **actual exhibition course**. 2nd/3rd/4th-course adjustment is allowed only for complete exhibition and a comparative ST/go/turn edge. **No guessed wind direction**. Source: https://www.boatrace-karatsu.jp/modules/datafile/?page=index_suimen
- **Conditional 2nd/3rd:** Head-course evidence gate must pass; then follower gets at most 4% and inner survivor at most 2.5%, with no guaranteed outside quota.
- **Exclusions:** Edogawa and the remaining 20 venues do not receive new layout correction. No additions based solely on track identity, tide calendar or race results.
- **Safety:** `forecastVenueLayoutTrial(input)` is an opt-in new function, with model ID `four-factor-venue-layout-v1.2-untrained`; `forecastFourFactorOpen(input)` stays unchanged. This does not alter Python's official pre-cutoff bridge, live ledger, immutable SHA256 records, displayed main picks, historical data, settlement, or real purchases.
- **Evaluation:** Scores are relative *uncalibrated* trial scores, not calibrated win probabilities. Run identical forward pre-cutoff comparisons by venue/condition with no hindsight. Assess 1st/2nd/3rd omissions, hit rate, and virtual returns before promotion.

Test commands:
```sh
node --check app/tactical-1m.js
node app/tests/venue-layout-trial.test.js
node app/tests/four-factor.test.js
python -m pytest -q
```
