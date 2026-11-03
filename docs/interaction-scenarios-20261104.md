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

## Primary promotion decision — 2026-11-04
User requested the **new interaction logic as the actual MAIN ticket selection**, not a shadow-only output. The first exploratory module still labels its raw scenario scores SHADOW_UNCALIBRATED and never generates stakes; the existing collector now adapts its ordered candidate scores to **primary virtual tickets** and records `interaction_primary` metadata. This is not statistical validation.

- Activation gate: new snapshots generated on/after **2026-11-04 09:00 JST**, only when cutoff is later; never rewrite an older snapshot.
- Applies where the existing 23-venue tactics is supported; **江戸川 excluded**.
- Uses existing pre-cutoff six-racer weights and available start/exhibition readings. No outcomes, odds or realized ST.
- Retains prior primary `bets` in `interaction_primary.old_main_bets` for same-race A/B.
- Matches prior primary number of tickets (4–20) and 50,000-yen virtual allocation; does not assert true win probabilities.
- App ticket classification remains governed by the pre-cutoff **complete exhibition gate**; baseline is provisional, not formal exhibition-reflected.
- Before/after daily aggregates are descriptive only and may be confounded by venue, field composition and weather. Strongest incremental test is same-race pre-cutoff paired control, comparing payout and calibration over future races.
- No live real-money purchases. Promotion may be reverted if failures or adverse results are observed.

**Verification**: unit and integration tests were authored, but successful GitHub Actions execution and production deployment must be checked separately. No claim of passing CI until run evidence is obtained.
