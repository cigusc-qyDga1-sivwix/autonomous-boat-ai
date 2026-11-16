# BOAT LAB original-exhibition recovery: official-source research

Date of source review: **2026-11-17 JST**. Research only; no forecast, wager, model, ledger or main-branch changes.

## Verified source facts

- BoatraceCSV provider documents `data/previews/original_exhibition/YYYY/MM/DD.csv`, but the current BOAT LAB `status-latest.json` reports `github_raw:HTTP 404` and `github_pages:HTTP 404` for original/stt/tkz/sui. Documentation is **not evidence of delivered rows**. Issue #269 remains open.
- The official **Gamagori** venue publicly shows `展示タイム / 一周 / まわり足 / 直線` for six lanes. An independently checked example is the venue page for **2026-11-11, 11R** at
  https://www.gamagori-kyotei.com/asp/gamagori/sp/kyogi/kyogihtml/recomend/recomend202611110711.htm
- Different venues use different timing segments. Kiryu's half-lap is **not** a full lap; Suminoe/Amagasaki/Tokuyama publish venue-specific subsets; Edogawa is out of scope.

## What this PR adds

`scripts/official_original_exhibition_research.py` is a deliberately **standalone one-race collector**, restricted to a known official Gamagori domain and venue code. It validates the page's displayed date/race, unique six lanes and courses, all four numeric columns and plausible bounds. It records the exact capture time, page SHA-256, measurement SHA-256, URL, missing reasons and `eligible_for_formal_prediction=false`. It never imports results, predicts a ticket, changes official outcomes or touches frozen snapshots.

Example, after checking the venue's access terms and responsible request frequency:

```bash
python -m unittest tests.test_official_original_exhibition_research
python scripts/official_original_exhibition_research.py --date 2026-11-11 --race 11
```

Each invocation saves an immutable **research capture** under `app/data/exhibition/official-source-research/YYYY-MM-DD/`. Historical capture must not be represented as pre-cutoff evidence. An HTTP error or partial six-boat record produces `MISSING`, never fabricated values.

## Required before operational/formal integration

1. Verify venue-site access conditions and actual HTTP response from the GitHub Actions runner; compare extracted six raw rows against the official rendered six-row table. The current PR's parser tests are offline fixtures; **live acquisition success is not yet claimed**.
2. Reconcile *the same race/time* against Boatrace OpenAPI's six lanes, entry, ST, ordinary exhibition time, race cutoff and first-capture time. Retain raw HTML SHA, source timestamp and independent measurement SHA. If any field is missing or source is late, do not certify.
3. Only then connect the adapter to the **research** collection workflow with a bounded retry cadence, fetch-health and no overwrites. Extend venue-by-venue using adapters; do not parse other sites as Gamagori.
4. Add a new isolated experimental feature schema/model SHA. Compare against fixed learned formal tickets on **100+ prospective common official-settled races** using the same stake/point count before considering any formal adoption.

No assertion of CI green, live success, deployment, or official-model integration is made by this PR.
