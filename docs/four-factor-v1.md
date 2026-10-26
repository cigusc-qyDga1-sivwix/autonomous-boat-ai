# Four-factor primary v1.0 — 2026-10-27

For future races from 2026-10-27 JST, use `four-factor-v1.0-untrained` as primary. Freeze the former v0.9 using the same pre-cutoff basic inputs as a separate shadow control. Historical snapshots, hashes and settlements are never rewritten. These are manually chosen trial weights, not fitted optimal coefficients or calibrated win probabilities.

## Base equation

`athlete^0.60 * motor^0.25 * exhibition^0.10 * weather^0.05`

Each factor is a positive multiplier around 1. Weights are log-space contributions to the base movement score. Actual-course priors and conditional six-boat 1M/2M scenarios then build 1st → 2nd → 3rd combinations. They are not percentages of final predictive attribution. Existing 4–12 picks, hypothetical ¥50,000/R, WATCH-only classification, and official-only settlement remain.

- Athlete (60): national win rate, national top-3 rate, local win rate, average ST, and same-frame historical win-rate/ST context. Source periods and sample sizes are not unified or calibrated. Full official course-specific 1st/2nd/3rd rates are not yet integrated; frame win rate is not a first-place percentage.
- Motor (25): motor top-2 and available top-3 rate. No invented improvement/history/sample-size correction.
- Exhibition (10): complete six-boat time/turn/straight/lap fields and legal exhibition ST. Missing values remain unavailable; exhibition F is not a super-fast legal start. Exhibition ST is not used a second time in the v0.7 slit estimator under this variant. The weighted base exhibition multiplier is bounded to exp(±0.10). It is neutral before exhibition.
- Weather (5): bounded roughness flattening from available wind/gust/wave fields. No guessed headwind/tailwind effect or uncollected rough-water racer skill. The legacy wind hedge is disabled for this variant to prevent double weighting.

## Identity and freshness

Fresh race_cards and waku10 CSV are retrieved before forecast generation. Join by date/venue/race, lane and registration number. Accept only matching source URLs, recorded SHA256, available state and timezone-aware capture in the same JST day, no later than the prediction and at most 30 minutes old. Only explicit pre-race numeric columns enter the model, not session/race outcomes or payouts. If an actual entry changes, old frame-specific history is not relabeled as different-course history. Unavailable metrics contribute neutral log weight 0 without redistributing the nominal weights.

If previously missing player/frame context becomes available before cutoff, append a bounded new same-phase revision (maximum three context-quality upgrades); never overwrite the old provisional/formal snapshot or add after cutoff.

The immutable racer rows preserve source hashes, URLs, capture times and context used. `four_factor` records factor weights, raw/weighted multipliers, availability and combination. This is a newly captured prospective use, not permission to backfill historical research as formal predictions.

## Display and validation

The race detail shows the factor multipliers. Pure player ability is displayed separately from the motor/exhibition/weather factors for v1.0; past model displays retain their definitions. Browser and server use the same JavaScript factor and tactical engine.

Tests cover directionality, neutrality/missing fields, exhibition F, entry changes, weather flattening, player-versus-motor separation, no outcome leakage, browser/server parity, budgets, cutoff gates, old snapshot preservation, date/ID/source freshness and historical model parity. Accuracy, return-rate improvement and optimal weighting require future pre-cutoff comparisons; no performance claim is made from October 26 hindsight.

## October 27 operation

Renew the bounded prediction-freshness watchdog for October 27 JST. It waits until 06:00 JST without dispatching overnight, checks freshness independently of cron during the day, and stops at the next JST midnight. Five sequential shifts cover the wait and remaining day under per-job limits. This is a daily incident mitigation, not a permanent external scheduler; the following day requires a separately validated operating arrangement.


## v1.1: ability-first second and third, October 27 prospective revision

`four-factor-v1.1-untrained` supersedes v1.0 for newly generated pre-cutoff
snapshots. Keep the same four base weights and the earlier same-time v0.9
control. Append one model upgrade to eligible races; never alter earlier SHA
records or closed races. The v1.0 function remains available for historical parity.

Diagnosis: v1.0 inherited a fixed head-to-second course table and stacked
adjacent-following, outer-following, wake and ticket-rescue multipliers. Those
could overpower the newly added athlete factor. v1.1 bypasses these in both
second and third scoring and selects the highest-ranked complete combinations
without legacy rescue. All five second-place and four third-place candidates
are evaluated and recorded, with no compulsory follower or lane quota.

Second weight = unconditional course prior [1.10,1.10,1.06,1.02,.98,.94]
× four-factor combined strength^1.15 × bounded relative-strength competition.
Third uses [1.04,1.04,1.03,1.02,1,.98] and strength^.95. The competition factor
is clamp(1+.05×(candidate strength/preceding strength−1),.95,1.05). It is a
small untrained proxy, not observed wake or a measured maneuver. These priors
are manual trial coefficients, not fitted course finish rates. Head priors and
pre-race attack evidence remain. No course forces a named winning maneuver;
ticket descriptions explicitly say it is undetermined. Legacy diagnostic
wake/coupling graphs are marked unapplied to chaser scoring.

This change removes the diagnosed structural bias; it does not establish an
improvement in hit rate, missed-place rate or return. Athlete-specific historical
second/third rates and maneuver success are still unavailable. Evaluate future
frozen predictions rather than claiming an improvement from hindsight.
