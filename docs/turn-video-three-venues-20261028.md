# BOAT LAB 10/28 Morning / Day / Night turn-vision pilot

Date: 2026-10-28 JST. Morning Karatsu (23), Day Kojima (16), Night Gamagori (07). Twelve races per venue, 36 total.

## Operation
The already scheduled nationwide collection runs about every five minutes. On 2026-10-28 JST only, scripts/turn_three_pilot.py reads the archived exhibition research records and updates app/data/experiments/turn-video-pilot-2026-10-28.json. Existing research snapshots, official result audits, BUY decisions and forecasts remain unchanged. GitHub Pages displays the record read-only at app/turn-vision-pilot-20261028.html.

Data inputs are historical BoatraceCSV observations. Race results are unofficial pending independent verification with BOATRACE. First course refers to actual entry course, not automatically boat #1. A first-course loss does not prove a turn was wide, speed dropped, or another boat found an inside gap. No retrospective inputs enter prestart forecasts.

## Video evidence
Current state is NO_LICENSED_VIDEO_ANALYZED for every race. Official video reuse, capture, download and machine-vision rights are not confirmed; no automated download or video stream recording is implemented. Mark clearance, turn radius, exit speed, confirmed six-boat tracks and visual inside-gap detection are all null until a rights-cleared video and ground-truth camera calibration exist. BOATCAST is linked only for direct human viewing under its site policy.

## Next validation
First obtain explicit authorized use of source videos, then verify boat IDs, first-turn mark location and fixed-camera geometry, and compare 20-50 annotated races. Evaluate recognition error and prestart A/B performance before touching the primary model.

## Tests
Run: python3 -m unittest discover -s tests -p test_turn_three_pilot.py
Run: python3 scripts/turn_three_pilot.py --date 2026-10-28

Official 1R beforeinfo Karatsu: https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=1&jcd=23&hd=20261028
Official videos: https://boatcast.jp/
Video site policy: https://boatcast.jp/static/sitepolicy/index.html