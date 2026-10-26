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
