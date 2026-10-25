# P0: Exhibition-to-forecast connection acceptance criteria

The exhibition research page (`app/exhibition-research.js`) only reads archived JSON and explicitly never writes to the forecast ledger. Displayed values are **not** proof of a live pre-cutoff forecast.

## Verified 2026-10-26
- `app/data/exhibition/status-latest.json`: all source counts zero, no research records.
- `app/data/live/audit-latest.json`: 144 baseline predictions, zero exhibition-final predictions.
- `scripts/autonomous_daily.py`: live forecast generation consumes `preview` from OpenAPI or date-matched `app/data/exhibition/YYYY-MM-DD.json` via `exhibition_bridge.inject`; requires complete six-boat entry/ST/time and at least three minutes before cutoff in production.
- `app/exhibition-research.js`: read-only, historical data and results can never be retroactively promoted to official tickets.
- PR #51 merged to show existing provisional picks on the venue board, without relabeling them as official.

## P0 implementation
1. Instrument per-race diagnostics: source fetched; six-boat entry/ST/time validated; observed timestamp; cutoff and current JST; injection rejection reason; forecast generated; SHA persisted; site published.
2. Identify a *lawfully accessible* real-time exhibition feed and collect its actual response before cutoff. Do not use after-cutoff archived CSV as proof of live capture.
3. In a bounded cutoff-aware worker, begin collection five minutes before cutoff, retry while safe, and regenerate predictions after each new verified exhibition snapshot. Respect processing/persistence time and never rewrite frozen history.
4. Expose `source -> validated -> predicted -> saved -> displayed` state on the race card. Preserve baseline bets labeled provisional when exhibition unavailable.
5. Test 三国1R with a pre-cutoff fixture (success, incomplete six boats, front-attachment, delayed feed, late cutoff) and end-to-end production run. Do not claim success from the fixture alone.
6. Deploy only after CI and live source verification; no notifications or real bets.

**Not yet implemented:** live feed, retry worker, diagnostics and end-to-end confirmation.
