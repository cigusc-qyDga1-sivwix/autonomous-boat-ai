# BOAT LAB: new information signals trial — 2026-11-03

This project keeps numerical BOAT LAB's immutable pre-cutoff formal model unchanged. New indicators are **advisory or research-only** until a forward model comparison earns promotion.

## 1. In-meeting ST consistency (pre-cutoff descriptive feature)
- Source: `programs/race_cards/YYYY/MM/DD.csv` from BoatraceCSV, read **by the current forecast run** and validated against `event_day`, `racer_id`, `lane`, source URL, SHA256 and <=30-minute fetch freshness.
- Source spec: https://boatracecsv.github.io/docs/data/programs.html#race-cards
- Maximum 14 meeting slots; read only slots with an actual race number and a populated ST. Valid legal ST: `0.00..0.40`, negative ST is separate F risk, not a fast legal start; invalid/blank observations are dropped.
- Derive `meeting_st_legal_count`, `meeting_st_mean`, `meeting_st_sd` (population SD), `meeting_st_recent_mean` (last 3), `meeting_st_recent_minus_older` (requires 6), and `meeting_st_f_count`. Publish mean/SD only with >=3 valid starts. The difference is last 3 minus earlier 3+.
- These fields are recorded with the racer context and displayed as a **new trial diagnostic**. They are not assumed to be probabilities and do **not** alter formal weights, tickets, rankings or yen allocations. No historical data is backfilled into a pre-cutoff model.
- Need validation for a serious model: distribution by grade/venue/entry and shrinkage for small samples; match pre-cutoff SHA with later outcomes.

## 2. Prior-day conditional 2nd and 3rd course finish distribution
- Source: historical `results/realtime/YYYY/MM/DD.csv`, collected from **dates strictly before the target day**. Actual 1st/2nd/3rd boat numbers are mapped to **real entering courses** using `Nコース_艇番`. Exclude incomplete race keys, non-6-boat races, F/negative ST, duplicates and user-excluded 江戸川 from all cohorts.
- Source spec: https://boatracecsv.github.io/docs/data/results.html
- Group by (all 23 venues / venue code) × observed winning course, with a 20-cell ordered pair space for 2nd/3rd courses excluding the winner. Hold cohorts with <30 races; emit descriptive counts and Jeffreys 0.5 smoothing for larger cohorts. Realized historical method is summarized as an **outcome**, not assumed known for upcoming races.
- Output is separate `boatlabs.historical_finish_pair_priors.v0.1`, `RESEARCH_ONLY_NOT_FROZEN_NOT_READY_FOR_AUTOMATIC_PICKS`. It never writes to `app/data/live` or result settlement; no video inputs, payout lookups, betting or notifications.
- A separately scheduled GitHub Action builds a 21-day historical snapshot and uploads a JSON **artifact** only. It does not push any new picks, or treat a later download as a past frozen prediction.
- To introduce a shadow model later, first freeze the exact prior version and source-hashes before cutoff; map actual entering courses and prospective **hypothesized** scenarios, preserve same point count and virtual ¥50,000, and compare official outcomes prospectively. Never use the actual current race winning course/method/result as model input.

## 3. More signals — not yet activated in formal model
- Motor prior-meeting history and maintenance metadata already have a research collection path in `scripts/ingest_global_intelligence.py`. Verify past-meet cutoffs, motor identity across replacements, history availability, sample sizes and racer-strength confounding before using a feature. A career motor two-hit rate is not a direct description of present motor quality.
- Tide height and its *rate of change*, wind direction relative to each course, repairs or component changes should be added only from traceable authorized sources and actual observed/relevant timestamps. Do not convert tide height into unmeasured race-water current direction.
- The existing weather/motor/exhibition four-factor weights are hypotheses, not learned effect sizes.

## Acceptance criteria
1. All 6 racers match source identity, freshness and pre-cutoff. Missing fields remain missing.
2. A new historical-results research report contains **zero current-day result rows**. Every historical outcome is dated earlier than target event day.
3. Label fields are not visible to formal `prediction()` or `four-factor` inference, and no bet changes are made in this PR.
4. Test `python -m unittest discover -s tests -p 'test_racer_context.py'`, `python -m unittest discover -s tests -p 'test_finish_pair_research.py'`, and the repository test suite.
5. Once a forward shadow model exists, assess **100+ races minimum** across several days at identical stake/points, monitor winner/2nd/3rd omissions and virtual return. That threshold only starts evaluation; it does not guarantee significance or justify BUY.
