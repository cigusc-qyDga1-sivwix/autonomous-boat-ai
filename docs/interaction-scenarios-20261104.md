# Interaction scenarios v0.1 — 2026-11-04

## Scope
New independent shadow research for BOAT LAB; no imports in the official collector, no modifications to app/data/live, stored forecasts, results, payout ledger, or BOAT VISION AI. The model is **untrained, uncalibrated, and not authorized for formal forecasts**.

## Hypotheses, NOT verified effects
- Faster outer attack can create a following lane for another boat.
- A defender may contest the attack, lowering the attacker's chance.
- A wide/failed attack may leave space for a follower.
- The outcome should be expressed as ordered 1st–2nd–3rd conditional branches rather than independent runner scores.

The percentages used for scenario assumptions (42/25/20/13) and score perturbations are **illustrative constants, not empirically estimated probabilities**. They must not be presented as win rates, betting edge, or confirmed tactical frequencies. Exhibition ST is not actual ST.

## Test locally
```bash
python -m pip install -e '.[test]'
python -m pytest -q tests/test_interaction_scenarios.py
python -m pytest -q
```

## Next forward test
1. Connect a read-only adapter to **pre-cutoff, timestamped** BOAT LAB six-boat inputs, translating the existing internally computed scores into `strength` without results or payouts.
2. Preserve same race ID, input SHA, timestamp and cutoff. Freeze both official baseline and independent shadow output prior to cutoff; do not retroactively replace.
3. Compare >=100 prospective races at identical point counts and hypothetical stakes; assess hit rate, return, log loss/Brier-style calibration and 3rd-place omissions by venue/attack lane. No postrace fit applied to historical snapshots.
4. Fit scenario priors from permitted historical data on training dates only; hold out future races. The current constants are **not** verified from empirical samples.
5. Only after CI, integration and prospective evaluation consider an opt-in app shadow display; formal BUY remains unchanged.

## Contract
`scripts/interaction_scenarios.py::evaluate` requires six distinct lanes, positive finite prior strengths and timezone-aware capture/cutoff. It rejects unrecognized racer fields (including outcome and odds features). Its output always declares `SHADOW_UNCALIBRATED`, `eligible_for_formal_forecast=false` and `bets_generated=0`.

Research inputs do not imply that lane-to-lane interference, mark tactics or paths are truly known. No external video data or scraping is introduced.
