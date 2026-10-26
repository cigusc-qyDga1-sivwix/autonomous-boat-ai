# Conditional statistical ranking v1 — research shadow

The production v1.1 chaser fix removed manual follower templates; it did not learn
coefficients. This separate model fits three regularized conditional multinomial
choice models from observed outcomes: P(first), P(second | first), and
P(third | first,second). Multiplying them ranks all 120 distinct trifectas.
No named maneuver, compulsory neighbor, rescue ticket or lane quota is imposed.
Repeated ticket shapes remain legitimate when supported by inputs and fitted data.

## Inputs and training

Use one latest eligible immutable snapshot per race, SHA-verified and captured
at least 120 seconds before cutoff, plus a date-matched verified official unique
finish and payout. Raw source snapshots are never enriched with later player
statistics. Exclude current/future event dates from training. Invalid exhibition
snapshots cannot be treated as formal data. Deduplicate by date/race. Names,
results, actual race ST, payouts and odds are excluded from features. Payout is
used only to evaluate held-out virtual outcomes.

Learned features: relative player win rate, average ST, motor top-2 rate, legal
exhibition ST/time, missing indicators, actual saved entry course (baseline entry
is explicitly unconfirmed), and interactions between ability/course, neighboring
ST, motor/wave, player/wind and hypothetical 1st/2nd candidates. These are
associations, not measured boat trajectories or causal effects. Athlete-specific
course 1st/2nd/3rd histories, technique success and full motor histories are still
unavailable in these frozen records. No claim that those have been learned.

Fixed L2=0.03 and fixed within-race scaling are used without tuning on these test
dates. Numeric coefficients are fitted by L-BFGS-B; no manual 60/25/10/5 mixture
is applied in this model. Softmax scores are uncalibrated. A source-matched 4–12
point count and virtual ¥50,000 budget make the comparison interpretable; neither
point count nor money allocation has been optimized for expected return.

## Initial evidence, October 27

736 official-settled races had at least one saved version. After validating safe
original snapshots, 735 races on October 22–26 remained (one excluded). The first
day has 99 eligible races, below the preset 100 training minimum; the first tested
day is October 24, trained on October 22–23. Later folds train on earlier dates
only. Thus the matched evaluation covers 472 races on October 24–26.

| Reconstructed dated test | Learned | Archived production snapshots |
|---|---:|---:|
| Trifecta hits |224 / 472 (47.46%)|205 / 472 (43.43%)|
| Virtual return |70.37%|77.31%|
| Head misses |102|64|
| Second-place misses after head captured |70|103|
| Third-place misses after pair captured |76|100|

The archived comparison includes the models actually frozen on those days, not a
pure v1.1 control. Among 90 complete exhibition snapshots, the reconstructed
learned hit rate was 47.78% versus 38.89%, and virtual return 66.95% versus 50.57%.
This small subgroup does not override the worse overall return or justify promotion.

These are retrospective chronological reconstructions made now, **not** predictions
made on those past days. Official labels are available now; their historical
collection latency is not simulated. The design was informed by prior discussed
results. Five dates and repeated athletes/venues provide very limited independent
evidence; no claim of hidden profitable patterns or statistical significance is made.

## Prospective operation

Keep production v1.1 unchanged. A separately SHA-fixed research shadow records
all 120 scores, chosen tickets, actual capture time, source snapshot SHA, model
SHA and prior-day training cutoff before the race (180-second live margin).
Identical source/model pairs are not frozen twice; old versions are append-only.
The source can be older than the shadow capture, so this is a **same-input**
comparison, not a claim the models were originally frozen at the same instant.

Model artifacts are content-addressed under `app/data/statistical/models/`.
Daily 04:10 JST best-effort training refreshes after prior-day official settlement;
the forecast loop freezes comparisons for new source versions. A failed research
step must not stop primary collection. The app labels these picks as research,
separate from formal tickets. Prospective official settlement is saved separately;
unresolved races are not counted as losses. No automatic promotion is implemented.

Read `evaluation-latest.json` for chronological folds, missing-data coverage,
source manifest and per-race results; `prospective-audit.json` reports only actually
forward-fixed predictions. Next work is longer chronological data coverage and
athlete-specific course records captured before races, followed by untouched
prospective validation of head coverage, conditional misses, calibration and return.

References: https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split
and https://docs.scipy.org/doc/scipy/reference/optimize.minimize-lbfgsb.html .
