# BOAT LAB 10/28: 10-venue morning/day/night turn-motion research

Date: 2026-10-28 JST. Today's official BOATRACE schedule lists 11 active venues. The turn-motion comparison expands from the initial 3 to **10 venues x 12R = up to 120 races**, excluding Edogawa (03) from the venue-tactics comparison as previously requested. Nationwide archival collection itself still includes Edogawa.

| Session | Core model venue (original) | Extended research venues | Planned races |
|---|---|---|---:|
| Morning | 唐津 Karatsu (23) | 三国 Mikuni (10) | 24 |
| Day | 児島 Kojima (16) | 尼崎 Amagasaki (13), 津 Tsu (09), 常滑 Tokoname (08), 福岡 Fukuoka (22) | 60 |
| Night | 蒲郡 Gamagori (07) | 桐生 Kiryu (01), 丸亀 Marugame (15) | 36 |

Source: https://www.boatrace.jp/owpc/pc/race/index?hd=20261028

## Actual implementation
The existing every-five-minutes (best effort) BOAT LAB GitHub workflow reuses the nationwide exhibition archive from BoatraceCSV. On 2026-10-28 JST only, scripts/turn_three_pilot.py writes a research-only ledger to app/data/experiments/turn-video-pilot-2026-10-28.json. The same path is retained; the schema is now boatlabs.turn_video_multivenue.v3. Earlier boatlabs.turn_video_multivenue.v2 and boatlabs.turn_video_three_venues.v1 records are read to preserve already captured original three-venue SHA/time evidence.

The mobile research page app/turn-vision-pilot-20261028.html allows filtering by session and original/extended study role. No archived results are incorporated into the historical or prospective frozen forecast ledger. If a race's data or timestamps are not securely proven to be pre-cutoff, that observation remains research-only without a qualifying first numeric snapshot.


## 2026-10-28: 全6艇ターン精度＋スタート後の伸び

**対象は1号艇だけではなく、全6艇。** 各レースに艇番①〜⑥の個別研究スロットを持たせ、以下を独立に計測する。

- **ターンマーク基準：** 同じ1マーク中心座標を全艇の共通基準にする。艇中心から1マーク中心への近似距離、旋回半径、旋回入口・出口の速度、立ち上がりの速度保持率、他艇が通れる空間を検証する。近ければ必ず有利ではなく、差し・まくりの適切な軌道は条件によって変わる。
- **スタート後の伸び：** 同じスタートライン・走行方向を基準に、各艇がスタートラインを通過した後の0〜5m、5〜15m、15〜30mの区間速度、後半／前半の速度比を測る。**公式STはタイミングを示す別の値であり、スタート後の伸びを代替しない。**
- **6艇の相対位置：** 伸びた艇と伸び負けた艇の位置関係がターンへの進入角度、差し場、まくり、まくり差し、残存にどう影響するか、適切な時点の観測だけで将来のレースに検証する。

全120R×6艇＝720艇スロットを研究データとして明示。現時点の実動画解析結果はゼロ。位置が確認できない艇は **未測定** であり、数値0や弱い艇と評価してはならない。

映像解析の研究モジュールは別の`ai-keirin`リポジトリ、`experimental/boat-ai-pro-v0.1`ブランチの`boat-ai-pro/boat_ai/six_boat_motion.py` に実装。人間の実艇識別・固定カメラ水面校正ができた合法ローカル動画に限った合成試験版であり、本番10場の映像を自動解析したわけではない。

**監査の不変条件**：展示数値の発走前SHA・正式予想・買い目・公式結果・収支を変更せず、研究台帳の読み取り専用項目だけ追加。

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