# BOAT VISION AI — separate experimental AI (2026-11-03)

**Goal:** Develop visual motion research *in parallel* with the numerical BOAT LAB without modifying its official selections, immutable pre-cutoff SHA, result ledger, stake or release process.

## Why a separate AI?
The existing numerical pipeline can continue collecting 6-boat entry, exhibition ST, exhibition time, motor and wind. The video pipeline needs its own independent source, quality gates, feature extraction and evaluation. Combining their release cycles now would make both systems more fragile.

## Current setup
- `vision_ai/` is a **standalone Python package** and has a **separate GitHub CI workflow**. It has no imports from BOAT LAB's numerical forecast engine, no live API, no database writes, no notifications and no betting.
- For the first prototype it consumes **numeric candidate tracks** exported by the existing `scripts/mikuni_six_boat_tracker.py`. It measures camera-stabilized **pixel-only** candidate motion, per six user-seeded labels. It cannot identify boats autonomously or infer true speed, water-plane positions, an actual 1M maneuver or win probability.
- It emits `boatlabs.vision_ai.pixel_motion_candidate.v1`: `PIXEL_CANDIDATES_UNVERIFIED`; `eligible_for_shadow_forecast=false`; `eligible_for_formal_forecast=false`; `bets_generated=0`. The source SHA and day, venue, race are retained.
- Real unattended video remains blocked by **authorized direct media delivery/playback** and subsequent real-footage 6-boat independent identity/calibration verification. Synthetic CV tests and webpage navigation do NOT prove actual footage was analyzed.
- The existing Mikuni video workflows already run separately from the main numerical forecasting workflow, but share a repository. For **repository-level isolation**, create a new `boat-vision-ai` repository later and transfer this self-contained package and dedicated workflow; this GitHub connection cannot create repositories. Keep the current branch as the reviewable starting point.

## Architecture / later link

```text
Numerical BOAT LAB                    Independent BOAT VISION AI
exhibition numeric data               venue-authorized video input
  -> frozen baseline/exhibition         -> ephemeral decode / frame tracking
  -> official result verification       -> 6-boat independent ID/calibration
  -> current forecasts                 -> timestamped numeric features
             \                          /
              \  one-way VERSIONED JSON  /
                -> read-only comparison
                -> same-race/time/point-count prospective A/B
                -> evidence reviewed; optional future promotion
```

**Required interface for future integration:** `event_date`, `venue_code`, `race`, `source_sha256`, `captured_at_utc`, `verified_at_utc`, 6 boat IDs, calibrated motion units, independent verification evidence, model version, sample coverage, source provenance and measurement timestamp. Identity and capture MUST be verified **before** the forecast cutoff safety margin (at least 120 seconds; operational pipeline may require 180). Reject mismatches, partial races, old footage, retrospective frames, unverified candidates and ambiguous source identity. Never let a video subsystem write directly into BOAT LAB `app/data/live` or official results.

**Never** treat current pixel candidate output as verified features. Its schema is intentionally incompatible with a future verified-motion bridge; that bridge must be separately developed, tested and reviewed.

## Parallel milestones
1. Keep BOAT LAB numeric collection/reforecast stable and independently audited.
2. Develop VISION source eligibility and genuine frame acquisition **without** DRM circumvention, JLC stream token discovery, or unauthorized redistribution.
3. Independently validate six boat IDs, camera-motion correction, water-plane calibration and measured start/turn/exit profiles on real approved clips. Report accuracy, coverage and failure cases.
4. Freeze a `vision-ai-verified-motion-v1` contract from real validated six-boat samples, before the actual cutoff. Run video-only read-only shadow A/B (no formal stake).
5. **Only** after sufficient matched forward comparisons of hit/return rate and miss type, test blended predictive features against numerical controls. Never rewrite older forecasts.

## Offline example
```bash
python -m unittest discover -s vision_ai/tests -p 'test_*.py' -v
python -m vision_ai --input ./unverified_mikuni_tracker.json --output ./research/vision-candidates.json
```

The input is an authorized numeric tracker export, **not** the raw video. The output is unverified numeric research with 0 bets. This command cannot access external sources or change frozen predictions.

**Explicit limitations:** This phase creates an independent research component and CI, not a separate hosted repository, live video acquisition, verified six-boat motion model, or an integrated betting prediction. Those remain open work.
