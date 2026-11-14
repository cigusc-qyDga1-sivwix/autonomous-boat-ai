# 2026-11-14 BOAT LAB: success/failure learning specification (forward-only)

Status: research protocol; no new model weights or production forecast change. Source cohort: 151 officially verified races (72 hits, 79 misses); virtual 7,550,000 JPY stakes and 6,408,200 JPY payouts; 84.9% ROI; 5 races held due to return/absence/etc. Do not label the held cases as losses or use them for training until settled.

## What to preserve from 72 hits
- Archive immutable pre-deadline predictions and the exact feature inputs/model SHA per race; determine whether successes were high-probability correct head/course, conditional 2nd and 3rd, or broad-combination coverage. A hit alone does not validate the underlying scenario.
- Compare 1-head survivors, non-1-head attacks, and inside-boat 2nd/3rd survivors separately; avoid blanket anti-1 tuning that destroys accurate inside wins.
- Keep source freshness and all-six exhibition verification as eligibility gates; never backfill post-race observations into pre-race inputs.

## Failure taxonomy (observed result, not asserted cause)
- 38 missed first place, 18 missed second place, 23 missed third place; total 79. These are position-of-miss labels, not established physical causal mechanisms.
- For each miss, assign an outcome-blind proposed pre-race mechanism from inputs available at cutoff: inside-defense weakness, outside attack readiness, actual entry/course shift, exhibition-vs-motor contradiction, second-boat position switching, conditional third survival. Mark unknown when evidence is insufficient.
- Differentiate inside boat loses first but survives 2nd/3rd versus inside boat drops out completely; test independent attack evidence and inside-skill strength both ways.

## Next training / evaluation
1. Ingest Nov 14 only after official-result verification; ensure no leakage of payouts, finish, actual ST, post-race video, or outcome-dependent SKIP choices into forecast features.
2. Retrain chronological historical-only model using target-date-exclusive data, with independently versioned data/model SHA and training-through day. Before changing formal forecasts, require artifact freshness, CI success, and pre-race eligibility.
3. Freeze new challenger and unchanged incumbent simultaneously on exactly the same future races. Compare hit rate, ROI, 1st recall, 2nd and 3rd conditional recall, 1-head success and inside survival, by venue and cohort; record 95% uncertainty intervals. Minimum 100 common eligible forward races is a checkpoint, not proof of improvement.
4. Evaluate risk-shadow KEEP/WATCH/SKIP separately. In the observed Nov 14 SKIP candidate set 22 of 46 were hits: quantify missed-hit opportunity cost and losses averted. Do not adopt automatic SKIP until net held-out benefit is demonstrated.
5. Promote only after meaningful forward improvement in ROI without unacceptable hit-rate or venue regression and with outcome-blind code tests. Roll back with pinned previous model SHA on deterioration.

## Production invariant
Do not change existing formal ticket amounts, saved pre-race predictions, historical settlement, or cumulative return. Preserve current learned-primary fallback and research-shadow separation until prospective comparison passes. No retrospective reconstruction counts as an actual formal hit.

## Required daily report
Date; frozen forecast count; six-boat-complete eligible count; official verified/held; model SHA/training-through; success scenario segments; first/second/third misses; hit rate; ROI; prior-day vs same-cohort baseline; shadow opportunity-cost; proposed change and evidence; actual CI/deployment status.
