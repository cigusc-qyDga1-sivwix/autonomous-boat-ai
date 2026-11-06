# BOAT LAB — Independent Exhibition Bridge (Pilot)

**State:** prototype; NOT deployed to Google Cloud, NOT connected to BOAT LAB formal forecasts. Existing main predictions, SHA256 ledgers, payout and PWA are unchanged.

## Objective

Replace the dependency on a third-party CSV's publication window with a bounded, one-race-at-a-time numeric exhibition acquisition experiment. The Cloud Run job is independent from the nationwide GitHub forecast runner; it can save **immutable research candidates** directly to a private Google Cloud Storage bucket without cloning or committing the 20–50 MB daily ledger.

## Source and permission boundary

Observed data-file shapes were documented in the public BoatraceCSV parser (MIT project):
https://github.com/BoatraceCSV/boatracecsv.github.io/blob/main/scripts/boatrace/preview_tsv_scraper.py

BOATCAST site policy: https://boatcast.jp/static/sitepolicy/index.html . It prohibits access patterns that disrupt its operations, including excessive automated access. The data URLs are an unofficially discovered internal format, **not a supported public API**. A project owner's permission and confirmation of acceptable automated use are needed before unattended deployment. Do not bypass 403, anti-bot controls, or access restrictions.

**Live fetching is disabled** unless environment variable `BOATCAST_DIRECT_FETCH_APPROVED=1` is explicitly configured. Even when enabled, the pilot fetches only `bc_j_stt` and `bc_j_tkz` for one exact race, sleeps between requests, has no retries, and stops immediately on access failure. It does not collect video, other race results or pay tables. An operator must supply the race deadline; it is recorded as *unverified* until an independent current race schedule is compared. Code is deliberately not configured to poll all venues automatically.

## Output and safety

- `boatlabs.direct_exhibition_candidate.v1` JSON with six normalized boats, their actual entry courses, exhibition ST (negative for F), exhibition time and tilt, actual collection time, and measurement SHA256.
- `source_observed_jst: null` because the provider's publication time is **not available**; do not infer it from collection time.
- `status: research_only_not_formal`, `formal_forecast_authorized: false`. This is a research candidate, **never** a retrospective formal prediction.
- Refuse inputs with missing/duplicate lanes or courses, malformed numbers, different JST day, or capture at/after three minutes before the supplied cutoff.
- Optional private GCS delivery is create-only under `exhibition-bridge/v1/YYYY-MM-DD/<race-code>/<measurement-sha>.json`; do not make the bucket public. Authentication should use Cloud Run's least-privilege service account and Application Default Credentials, not a key in GitHub.
- The existing app must **not** directly consume this schema as a formally fixed forecast. Integration requires verified source authorization, authenticated receipt, authoritative cutoff time, pre-cutoff runtime and persistence timestamps, and forward-only tests.

## Offline tests

Run from the repository root:

```bash
python -m pytest -q tests/test_independent_direct_exhibition_probe.py
```

For an offline fixture directory containing `stt.txt` and `tkz.txt` in the documented TSV format (requires a future same-JST-day cutoff):

```bash
python services/exhibition-bridge/collector.py --date today --venue 23 --race 7 --cutoff 22:00 --fixture-dir /path/to/fixture --out /tmp/exhibition-candidate.json
```

## Cloud Run Job (manual proof only; no automatic schedule yet)

Cloud Run deployment requires a Google Cloud project with billing and adequate IAM, which have **not** been connected to this chat. Example after confirming source permission and deploying credentials securely:

```bash
PROJECT_ID=your-gcp-project
REGION=asia-northeast1
IMAGE=asia-northeast1-docker.pkg.dev/$PROJECT_ID/boatlabs/exhibition-bridge:pilot
# Configure Artifact Registry repository and Cloud Build access first.
gcloud builds submit services/exhibition-bridge --tag "$IMAGE" --project "$PROJECT_ID"
gcloud run jobs deploy boatlab-exhibition-bridge-pilot --image "$IMAGE" --region "$REGION" --project "$PROJECT_ID" --service-account exhibition-bridge@$PROJECT_ID.iam.gserviceaccount.com --set-env-vars BOATCAST_DIRECT_FETCH_APPROVED=1 --args=--date,today,--venue,23,--race,7,--cutoff,22:00,--live,--gcs-bucket,your-private-bucket
```

The fixed race/cutoff arguments above are **illustrative, not production scheduling inputs**: do not repeatedly run them and do not schedule the pilot every minute. A follow-up version must discover authoritative upcoming race targets, deduplicate fetches, honor source-permitted rate limits and access controls, and securely deliver data to a BOAT LAB event handler.

## Acceptance criteria before production integration

1. Direct source permission and small live sample connectivity confirmed (HTTP status, encoding, 6 boat completeness).
2. Same-race CSV vs direct collection time comparison using actual **collection** timestamps; no unverified source timing claims.
3. One-race target discovery from authoritative event schedule, per-host throttling, GCS delivery audit and alerts.
4. BOAT LAB consumer verifies candidate integrity, current date, race identity, official cutoff and publication complete **before** creating a new SHA-fixed forecast. Post-result backfill never counts as official.
5. Compare at least a forward sample of 100 races; track retrieval, pre-cutoff freeze, publication success, odds-free forecast changes separately.

Cloud Run Jobs pricing includes a minimum one-minute billable instance per execution, so minute-level schedules should be evaluated before turning on. See https://cloud.google.com/run/pricing .
