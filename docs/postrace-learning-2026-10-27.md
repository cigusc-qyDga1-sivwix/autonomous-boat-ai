# 2026-10-27 結果逆算研究（研究専用・正式予想には不算入）

> Status: **hypotheses only / NOT production logic / NOT formal predictions**  
> Prepared from BOATRACE official race results + publicly retrievable historical before-info, and GitHub's immutable pre-cutoff audit summaries. We DO NOT assert that the historical before-info was ingested by BOAT LAB before its deadline. Case selection was informed by results; do not treat fitted tickets or displayed hit combinations as genuine past predictions.

## 監査スナップショット（2026-10-27 16:21頃 JST）

Source: [frozen production audit](../app/data/live/audit-latest.json), source updated `2026-10-27T07:21:03.748757+00:00`; [forward-fixed research shadow comparison](../app/data/statistical/prospective-audit.json), created `2026-10-27T07:21:25.907892+00:00`.

- Same-day production/frozen original, official verified: **124 races**, **44 hits (35.48%)**, virtual return **60.292%** (¥3,738,100 / ¥6,200,000). Breakdown of 80 misses: **head 40, second after head 28, third after first+second 12**.
- Matched pre-cutoff research shadow, same 124 races: **56 hits (45.16%)**, virtual return **93.877%** (¥5,820,400 / ¥6,200,000). Control in the paired audit: 44 hits / 60.292%. These are archived forward-fixed shadow predictions, not newly invented forecasts.
- Research shadow has **not** been promoted (`promotion_status: not_promoted_insufficient_prospective_evidence`). Neither percentage is a guarantee, a calibrated probability or proof of sustainable profitability; one-day matched comparison has high variance.
- Do not use unverified/pending, refund/cancellation, or disputed races as losses.

## Selected counterfactual cases — correctly labeled retrospective examples

All four are **selected after knowing results**, not an unbiased sample. `original_failure_stage` comes from [audit unhit_examples](../app/data/live/audit-latest.json) when present. A proposed trifecta is **not** a prior frozen bet, and receives **zero** retrospective credit.

| Race | Official finish / winning method | Pre-race observable indicators on official before-info | Original audit error | Candidate scenario to test later |
|---|---|---|---|---|
| 三国4R | **5-1-3**, ⑤まくり差し | ⑤展示タイム6.77 (best of six, next 6.83), ⑤展示ST .02 vs ① .14; ④ .27 | head miss, originally first displayed head ① | Outer speed + ST advantage permits ⑤1着, while ① holds 2着 and ③ holds 3着 |
| 三国5R | **5-6-1**, ⑤まくり | ⑤展示ST .03, ⑥ .01, ①展示ST F.05; exhibition times ⑤6.87, ⑥6.81 | head miss, first displayed head ① | Outer attack ⑤ / outside follower ⑥ / inside third ①; do **not** equate exhibition F with actual race foul |
| 児島1R | **5-1-3**, ⑤差し | ⑤展示ST .01, ① .01, ④ .02; ⑤展示タイム6.91 (NOT fastest; ④6.83) | head miss, first displayed head ① | An outside-course 差し wins **without** being fastest exhibition boat; model needs conditional inside-boat survival and positional pathway |
| 多摩川1R | **6-1-2**, ⑥まくり差し | ⑥展示タイム6.64, next ③6.71 (0.07s gap), ①6.75; ⑥展示ST F.01 | **second miss**, not head miss (initial displayed top head ③) | ⑥1着 had some original ticket head coverage; learn ①2着 / ②3着 conditional on ⑥ win, not just wider 1st choices |

### Official primary evidence

- 三国4R [results](https://www.boatrace.jp/owpc/pc/race/raceresult?hd=20261027&jcd=10&rno=4) / [exhibition](https://www.boatrace.jp/owpc/pc/race/beforeinfo?hd=20261027&jcd=10&rno=4). Actual race ST ⑤ .13 / ① .23 is **post-event outcome, excluded from candidate pre-race features**.
- 三国5R [results](https://www.boatrace.jp/owpc/pc/race/raceresult?hd=20261027&jcd=10&rno=5) / [exhibition](https://www.boatrace.jp/owpc/pc/race/beforeinfo?hd=20261027&jcd=10&rno=5). Actual race ST ⑤ .09 / ⑥ .12 / ① .24: **outcome-only diagnostic**.
- 児島1R [results](https://www.boatrace.jp/owpc/pc/race/raceresult?hd=20261027&jcd=16&rno=1) / [exhibition](https://www.boatrace.jp/owpc/pc/race/beforeinfo?hd=20261027&jcd=16&rno=1).
- 多摩川1R [results](https://www.boatrace.jp/owpc/pc/race/raceresult?hd=20261027&jcd=05&rno=1) / [exhibition](https://www.boatrace.jp/owpc/pc/race/beforeinfo?hd=20261027&jcd=05&rno=1). Actual race ST ⑥ .13 / ① .06 is **outcome only**, showing why exhibition speed and start alone cannot explain causality.

## Next shadow-only testable hypotheses (NOT approved weights)

**H1: Outstanding outside exhibition time.** Before cutoff, compare each ④⑤⑥ boat's valid measured exhibition time with the next-best valid boat, its own course, racer/motor ability, course records and ST context. Hypothesis: unusually large relative exhibition lead may require retaining more outside 1st scenarios. Do not use a hardcoded 0.07s cutoff learned from this selected race; tune only on strictly previous dates.

**H2: Outside attack + neighbor follow vs inside survivor.** Condition 2nd/3rd rankings on a candidate 1st, and distinguish ① remains 2nd, ① remains 3rd, and adjacent ⑥ follows ⑤. These are **test scenarios**, not proof of actual 1M paths. A final finishing order or winning technique cannot identify wakes, positions, interference or which gap was physically used; video labels are required.

**H3: Not all outside wins share the same predictor.** 三国4 shows expo-time/ST advantage; 児島1 wins via reported 差し despite nonleading exhibition time; 多摩川1 shows large exhibition-time lead with negative exhibition ST. Avoid forced rules "fastest exhibition always wins" or "exhibition F forbids head"; negative/F measurements are missing for valid-ST features.

**H4: Failure stage prioritization.** Today's original 40 head misses and 28 second misses justify evaluating two independent fixes, while 12 third misses should not encourage uniform ticket inflation. Compare existing `four-factor-v1.1`/`four-factor-v1.2` mixed archival frozen snapshots only as archived; do not retroactively relabel original version.

## Reproducible evaluation protocol

1. Use complete 6-boat archived **pre-cutoff timestamped immutable source/features** only. No result, actual race ST, actual decision, final odds or payout may enter model selection. Do not include historical exhibition acquired after cutoff as though actually available then.
2. Define development window from **past dates only**, include **all verifiable races**, not just four selected failures. Hold subsequent date(s) untouched; keep location, class, weather, entry changes and F/missing coverage segmented.
3. Freeze production baseline and H1, H2, H3 research models with `captured_at`, source SHA, model SHA, event/date/course keys and bets BEFORE cutoff. Do not overwrite existing forecasts; no retroactive changes to production formal revenue or BUY/WATCH/SKIP.
4. Score with official unique 1st-2nd-3rd and payout only **after** every test-model ticket is frozen. Compare *paired* races: head capture; second capture conditional on head; third capture conditional on pair; exact 3連単; virtual ¥50,000 stake/return. Report point count and uncertainties. 4–12 tickets can be used consistently, not widened merely to claim higher hit rates.
5. Evaluate both improvements AND regressions (miss classes/venue/inside vs outside/low odds etc). Run longer forward A/B sample before discussing promotion. Prefer model-family statistical shadow as a benchmark but **not automatic promotion** merely because this one day looks better.
6. Only video-verified 進入→スタート→1M→バック evidence can receive causal/trajectory labels; official 決まり手 is merely winner-method metadata. Do not create fictitious animation labels from finishing order.

## Existing compatible implementations

- `scripts/replay_exhibition_today.py`: generates replay candidates **before** official result scoring, historically collected exhibition is research-only.
- `scripts/research_start_gap.py` / `scripts/research_outside_roles.py` / `scripts/research_coupling_patterns.py`: retrospective descriptive research, does **not** change production prediction weights.
- `docs/statistical-learning-v1.md`: conditional P(first) × P(second|first) × P(third|first,second), shadow trained only through earlier dates and evaluated separately.

**Decision: No main-model coefficient change, no automatic retrospective credit, no verified gain claimed by these four post-hoc cases.** This note stores explicit learnable hypotheses and safe experiment gates, not a deployed predictive improvement.
