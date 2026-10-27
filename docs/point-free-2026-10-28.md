# Point-free selection trial — 2026-10-28 JST

User intent: select combinations from race evaluation first; count and allocate
only afterwards. There is no 18-ticket target, no requirement to buy 120 tickets,
no fixed number of heads and no two-tickets-per-head reservation.

## Operational scope

Only the 2026-10-28 race day uses four-factor-v1.5-point-free-untrained as the
primary model. Date and per-race live clock must agree; production retains its
180-second buffer, six-exhibition-row/actual-entry requirements and provisional
baseline distinction. No old snapshots are changed; revisions are append-only.
The automatic 5-minute collector remains the publisher. A bounded 10/28 watchdog
starts from its scheduled 06:02 JST invocation, checks source freshness and
collecting-job status, and can dispatch the same collector. It expires at day end.
GitHub schedules are best effort. The trial does not auto-promote to later days.

## Selection rule and honest limitations

The trial retains the current conditional score computation: v1.4 venue-aware
scores outside Edogawa, v1.3 conditional scores inside Edogawa. It removes the
4–12 point-count formula, head mass/individual-share quota reservations, and
post-selection ticket replacement. It evaluates all 120 feasible triples, then
adopts each triple whose joint relative score is at least the mean of those 120
scores (with a numerical tolerance for equality). This neutral, uniform reference
is explicit and untrained: it is neither an empirical win threshold nor a claim
that trajectories or maneuver causes have been learned. Missing observations
remain neutral under the existing score model. No odds or results enter selection.

Point count is the number of adopted evaluations. The physical domain has 120
triples, not a point target. Even completely tied evaluations may all pass; no
all-ticket fill occurs to reach a number. Each of the 120 adoption/rejection
records and its unrounded score is frozen under four_factor.ticket_policy.
There is no retrospective result optimization or performance claim in this patch.

## Allocation and matched comparison

After selection, allocate the same virtual 50,000 yen using 100-yen units. Each
adopted triple gets one unit and the remainder follows relative score^0.8 with
largest-remainder rounding. This changes both the candidate selection and amount
per ticket. Every source snapshot freezes point_free_control: the same input and
instant, v1.4/v1.3 predecessor tickets and allocation, with no additional formal
stake. Report additional hits, lost hits, point distribution, under-budget hits
and ROI together; higher coverage alone does not demonstrate improvement.
forecast_audit.point_free_comparison separates baseline and exhibition comparisons.
The statistical shadow matches the source count and currency granularity, while
remaining a separate research model. Old-model validators keep their old bounds.

## Validation

Dedicated tests cover 1/2/3/17/19/41/73/120 adopted evaluations, permutation
independence, all saved-race input replay, unchanged athlete/head/conditional
scores, same-input predecessor parity, 50,000-yen totals, no result dependence,
Edogawa exclusion, date activation, immutable prior revisions, formal gate,
idempotence, cutoff rejection, broad settlement and statistical shadow support.
Earlier engine outputs are also compared to the prepatch source for parity.
