# BOAT LAB venue-specific original exhibition model design (research v0.1)

Reviewed: **2026-11-17 JST**. Production forecasting, fixed ticket snapshots,
learned model SHA, revenue ledger and main are deliberately unchanged.

## Factual measurement contract

Sources:
- BOAT RACE official explanation: https://www.boatrace.jp/owpc/pc/site/news/2025/07/44414/
- Collected links to official venue measurement diagrams (checked 2026-11-08):
  https://hunebaka.com/learn/exhibition/original-times/
- Direct BOATCAST GitHub Actions proofs, 2026-11-17:
  Tokuyama 2R: https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/actions/runs/43993185462
  Karatsu 2R: https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/actions/runs/43993605834

The two Actions proofs show HTTP 200 and six parsed boats on each tested race,
but **neither proves pre-cutoff capture nor independently certifies a formal model**.
They are distinct from historical BoatraceCSV feeds currently reporting HTTP 404.
Source terms/access frequency need assessment before broad live automation.

|場|Documented columns|Venue-specific treatment (research only)|
|---|---|---|
|01 桐生|half-lap / turn / straight|Do NOT double half lap. Test wind and wave interactions.|
|02 戸田|lap / turn / straight|Test 1M-related attack versus inside resistance with actual entry.|
|03 江戸川|not verified|Exclude from this original-exhibition model.|
|04 平和島|lap / turn / straight|Measured wind/tide only; test turn and straight conditional effects.|
|05 多摩川|lap / turn / straight|Test post-turn/exit acceleration as distinct from usual exhibition.|
|06 浜名湖|lap / turn / straight|Original straight and regular exhibition use different segments.|
|07 蒲郡|lap / turn / straight|Normally lap 2; lap 1 when only one lap is run. Store selection.|
|08 常滑|lap / turn / straight|Lap missingness is possible; never set zero/worst score.|
|09 津|lap / turn / straight, documented 2026|Verify actual present-day release before enabling live use.|
|10 三国|half-lap / turn / straight|Do NOT equate half lap with full lap.|
|11 びわこ|lap / turn / straight|Official turn section is 1M; model 1M survival interaction.|
|12 住之江|lap / turn only|Do not substitute regular exhibition as original straight.|
|13 尼崎|lap / turn only|Same: do not infer missing original straight.|
|14 鳴門|lap / turn / straight|Conditional attack and tide only with actual evidence.|
|15 丸亀|lap / turn / straight|Validate current feed; tide/turn conditional tests.|
|16 児島|lap / turn / straight|Validate current segment; compare head vs pair misses.|
|17 宮島|lap / turn / straight (older diagram)|Re-check specification drift; do not force tidal bonus.|
|18 徳山|lap / turn only|2026-11-17 2R six-boat source proof. Test 2nd/3rd survival.|
|19 下関|lap / turn / straight|Official page states lap 2; account for shortened exhibitions.|
|20 若松|lap / turn / straight|Lap uses lap 1; turn/straight best of laps 1 and 2, not a common circuit.|
|21 芦屋|lap / turn / straight|Test outer-boat 2nd/3rd retention, not automatic upgrade.|
|22 福岡|lap / turn / straight|Keep straight segment distinct from regular exhibition.|
|23 唐津|lap / turn / straight|2026-11-17 2R six-boat source proof. Test 1M inside/outside paths.|
|24 大村|lap / turn / straight|Measurement interval changed historically; don't reuse old fixed ranges.|

For all 24, **column presence is not proof of actual measurements for every race**.
The code defines expected columns only; its live parser needs actual 6-boat
evidence. Older reference diagrams may have changed.

## Separate factual extraction from predictive hypotheses

1. For each original measured item and each race, store the raw seconds, 6-boat
   midrank, difference to the within-race median, and gap from the fastest.
   Negative raw deltas mean *faster*, not necessarily *better finish*.
2. Compare only equivalent venue/method definitions. Do not compare raw seconds
   across venues, multiply half lap to make full lap, or subtract straight/turn
   time from lap where timing circuits differ.
3. Preserve `NOT_OFFERED` (venue does not publish that metric),
   `MISSING_OR_INVALID_SIX_BOAT` (published but missing), and
   `SIX_BOAT_COMPLETE` independently per metric.
4. Validate the same date/venue/race, provider URL, 6 unique boat indices,
   source capture, frozen timestamp, independent measurement SHA,
   and 2-minute minimum cutoff margin. Data after cutoff are historical
   research only and must NEVER enter stored pre-cutoff predictions.
5. Do not turn this extractor into a hard-coded handicap. Add candidate
   interactions **only in a separate model schema/SHA**:
   - P(first): `ST × actual entry × relative straight/turn`,
     lane-1 survival/failure in both directions.
   - P(second | first): `relative turn × candidate first's course/attack`,
     nearby followers and alternate-route survivors.
   - P(third | first, second): `relative turn + lap/half-lap`,
     recovery and wake/trailing ability.
   - Venue-level weights with shrinkage/partial pooling; major weather, wave,
     tide, grade, and entry-change interactions require measured inputs and
     sufficient samples. Model coefficients must come from training, not
     analyst-set bonuses or post-hoc ticket changes.
6. Train on historical outcomes solely as labels for days strictly BEFORE
   the predicted date; select hyperparameters using chronological folds, no
   overlap between train and prospective validation. Treat published time
   columns as observations, not as estimates of maneuver success.
7. Freeze both main and candidate output at the same event time and model SHA
   with identical point count and virtual ¥50,000, independent SHA and no
   retrospective recreation. Compare 100+ officially settled **common**
   prospective races by venue, model SHA, grade, and head/second/third misses,
   hit rate, return rate, and payout delta. No promotion without proof.

## Code added

`scripts/original_exhibition_venue_research.py` is a **standalone research
transformer** that generates six-boat relative features from a previously
captured BOATCAST research record; it does not fetch, score predictions,
read outcomes, write snapshots, alter classification or modify production.
`tests/test_original_exhibition_venue_research.py` tests specification
variants, cutoff timing, SHA integrity and missing values.

To run only the new tests:

```bash
python -m unittest discover -s tests -p test_original_exhibition_venue_research.py -v
```

## Immediate research gates

- Confirm live BOATCAST response across **half-lap / two-metric / three-metric**
  venue groups and official-page correspondence.
- Implement bounded, approved-rate fetching and immutable six-boat captures
  before the deadline (target <= cutoff - 5 minutes); verify real scheduling
  latency. Fail closed if arrival is late.
- Evaluate venue-specific relative metrics as a **shadow**. Do not claim
  performance gain before official forward comparison.
- Only after proven improvement consider a separate formal-promotion PR.
