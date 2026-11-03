# Windows rendered replay runner — implementation checkpoint

Checked 2026-11-03 UTC. This is an independent experimental delta on PR #154 commit
`4335ce1f01902f5bf70ae4fef226ac4c57f35419`, not a change to the formal BOAT LAB.

## Evidence and boundary

- Existing Windows script `scripts/check_mikuni_edge_nodocker.ps1` (blob `dac30bd0de4af47951e48fb67914f577852e02d3`) supplied the official PC entry, temporary Edge playback and numeric pixel-probe precedent. The old path required manual date/R selection and START confirmation.
- A browser inspection of the official PC entry with `tpl=10` found `#switcher_tenji`, date/R exhibition links with `md='T'`, the JLC wrapper and its direct official CDN player. Selecting 2026-10-28/1R populated a matching exhibition player. This proves UI selection, not video reception.
- The runner uses these observed UI elements. It checks wrapper and child-player date/R/venue/type before playback and each RAM capture. It does not discover stream URLs, inspect network requests, or extract tokens.
- Maximum three windows at configured offsets, 6–24 samples per window, bounded image dimensions and 24MB encoded RAM limit. No direct FFmpeg dependency on Windows; rendered pixels feed PR #154's existing tracker.
- Distinct rendered-input schema/hash. A rendered screenshot sequence does not pretend to be the original media or inherit the original-media independent-label verification contract.
- Fixed error categories only. Viewing refusal and identity ambiguity terminate without retries. Missing replay retries are bounded. Application output is numeric JSON only.

## Validation

Local Python 3.12: 39 standard-library checks and 54 checks including real OpenCV/FFmpeg,
all passed, no skips. Added eight runner contract tests and four generated-pixel checks.
These are synthetic/mocked tests, not real exhibition accuracy evidence.

The portable build uses verified-hash Python 3.12.10 embed x64 and six pinned PyPI wheels.
The Windows workflow imports the packaged runtime and drives installed Edge on a locally
generated canvas. Even a green Windows workflow cannot prove official replay access.

## Pending / next work

1. Run CHECK_RUNTIME.cmd and START_CAPTURE.cmd once on the user's Windows PC using a currently available Mikuni exhibition date/R. This environment cannot execute that PC remotely.
2. Inspect distinct stages: official selection, player identity, clock advancement, dynamic pixels, candidate count and simultaneous support. Never equate success of the process with six confirmed boats.
3. Diagnose any fixed failure category without bypassing restrictions. Windows first-run behavior is unconfirmed until actual execution.
4. Only after actual acquisition, add reviewed numeric-only cloud ingestion. Current cloud_sync explicitly says local outbox only.
5. Independent real-footage identity labels, timing/scale calibration and start/turn/exit metrics remain pending. Formal and shadow eligibility are always false, confirmed identities and bets always zero.

No production imports, forecast/ledger writes, main merge, scheduled acquisition or cloud
upload were introduced. User instructions are in `windows/README_WINDOWS.md`.
