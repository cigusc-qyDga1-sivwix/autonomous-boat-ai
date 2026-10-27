# BOAT LAB 10/28: 10-venue morning/day/night turn-motion research

Date: 2026-10-28 JST. Today's official BOATRACE schedule lists 11 active venues. The turn-motion comparison expands from the initial 3 to **10 venues x 12R = up to 120 races**, excluding Edogawa (03) from the venue-tactics comparison as previously requested. Nationwide archival collection itself still includes Edogawa.

| Session | Core model venue (original) | Extended research venues | Planned races |
|---|---|---|---:|
| Morning | 唐津 Karatsu (23) | 三国 Mikuni (10) | 24 |
| Day | 児島 Kojima (16) | 尼崎 Amagasaki (13), 津 Tsu (09), 常滑 Tokoname (08), 福岡 Fukuoka (22) | 60 |
| Night | 蒲郡 Gamagori (07) | 桐生 Kiryu (01), 丸亀 Marugame (15) | 36 |

Source: https://www.boatrace.jp/owpc/pc/race/index?hd=20261028

## Actual implementation
The existing every-five-minutes (best effort) BOAT LAB GitHub workflow reuses the nationwide exhibition archive from BoatraceCSV. On 2026-10-28 JST only, scripts/turn_three_pilot.py writes a research-only ledger to app/data/experiments/turn-video-pilot-2026-10-28.json. The same path is retained; the schema is now boatlabs.turn_video_multivenue.v2. Earlier boatlabs.turn_video_three_venues.v1 records are read to preserve already captured original three-venue SHA/time evidence.

The mobile research page app/turn-vision-pilot-20261028.html allows filtering by session and original/extended study role. No archived results are incorporated into the historical or prospective frozen forecast ledger. If a race's data or timestamps are not securely proven to be pre-cutoff, that observation remains research-only without a qualifying first numeric snapshot.

## What is and is not measured
Available after publication: six-boat exhibition time/ST, actual entry course, tilt, available venue-specific original exhibition figures and wind/wave; post-finish unofficial result, including whether the **actual first-course entrant** won. Result data is NOT proof of turn error, losing speed, or an inside gap.

NOT available: automated licensed video capture, 6-boat visually confirmed trajectories, turn-mark clearance, turn radius, exit speed or visual pass-causality. These stay unavailable/unverified. Official BOATCAST site policy restricts embedding and reuse. Permission has not been obtained for machine-processing official video. Do not capture, scrape, or download it without explicit authorization.

## Validation
Test synthetic 120-race coverage, Edogawa exclusion, preservation of original three-venue audit SHA, actual entry course 1 versus boat no.1, missing and post-cutoff data, and all timestamps.

Command: python3 -m unittest discover -s tests -p test_turn_three_pilot.py
Command: python3 scripts/turn_three_pilot.py --date 2026-10-28

Official video watch: https://boatcast.jp/
Official video policy: https://boatcast.jp/static/sitepolicy/index.html

Only after obtaining explicit licensed source footage, label real boat IDs and 1M marker/camera calibration. Then test whether exposure to video improves future prestart 1-course escape and 2nd/3rd-place predictions with independently frozen A/B variants. The primary model, BUY and official settlement remain unchanged.