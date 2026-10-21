# Wakamatsu pilot — phase 1

Scope: Wakamatsu venue code 20 only. Trigger target: **betting cutoff minus 10 minutes**, not scheduled race start.

## Current status
- Implemented: deadline calculation, venue restriction, missing-data audit, unit tests.
- Not implemented: authoritative cutoff schedule retrieval, exhibition/weather/odds connectors, durable storage, scheduler service, automatic predictions, model retraining.
- Missing exhibition values MUST remain null; SKIP until validated.
- No real-money wagering. No mobile notifications.
- A GitHub Actions scheduled workflow alone cannot guarantee precise minute-level execution. Use an always-on worker with retries and idempotent race IDs once data sources are authorized.

## Next integration gate
1. Confirm permitted data sources and timestamps.
2. Capture data source URL, retrieval time, and freshness for every field.
3. Test 10-minute cutoff triggers against actual Wakamatsu races.
4. Freeze pre-race predictions, then compare with official results.
5. Only then expand to other venues.
