# Pending-race head coverage trial — 2026-10-27

Authorized scope: only races without exhibition-informed predictions at activation.
The explicit candidate roster is config/head-coverage-2026-10-27.json. Its source
SHAs identify the baseline records observed while preparing the change, not a
promise all candidates will activate. The live collector rechecks the complete
version history: any prior exhibition excludes activation. A race activated while
baseline-only keeps the policy when its first and subsequent exhibition arrives.
Other dates and non-roster races use their existing model. There is no automatic
promotion tomorrow. Activation requires at least 180 seconds before cutoff.

Model: four-factor-v1.2-head-coverage-untrained. Athlete/motor/exhibition/weather
weights, all 120 combination scores and pre-selection head shares stay unchanged.
The old v1.1 selects the highest scoring N combinations. The trial reserves the
best two combinations for each head in the smallest descending head-score prefix
reaching 0.80 relative mass, stopping before a subsequent head below 0.10 and
before two tickets per head would exceed the existing N. Remaining slots take the
highest available full-combination scores. It may retain one, two, three or more
heads; no fixed lane/template. Original N, 4–12 limits, and virtual ¥50,000 remain.
These parameters are an uncalibrated trial policy, not empirical win probabilities
or a claimed statistical optimum. No guarantee of reaching 80% or of profitability.

Every v1.2 freeze stores same-input/same-instant v1.1 tickets in
head_coverage_control, alongside existing v0.9 and venue controls. They are
research comparisons with no extra formal stake. Compare both hit rate and ROI
on precisely the same future settled races; fitting this policy using today's
observed failures means retrospective replay cannot establish improvement.

Old versions and SHAs are append-only and never rewritten. Baseline revisions
remain provisional. Six valid exhibition/entry readings and the existing safe
capture gate are still required for formal tickets. This change does not add
wind-direction coefficients or individual athlete per-course finish-rate data.

Validation: full saved-race input replay for invariant head shares/ability/point
count/stake, control parity and no result dependence; mixed-history collector tests
for activation, prior-formal exclusion, append-only updates, later exhibition,
idempotence, non-roster/date/time guards. Existing old-engine regressions retained.
