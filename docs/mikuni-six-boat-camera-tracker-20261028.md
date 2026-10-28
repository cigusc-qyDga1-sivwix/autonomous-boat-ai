# 三国｜6艇の初期位置からカメラ補正つき軌跡候補を追跡する v0.2

更新日：2026-10-28（実映像の自動解析成功は未確認）

## 概要

BOAT LABの次の課題は、動画に映る①〜⑥の艇番・旋回・スタート後の伸びを動画だけから信頼して学習すること。現段階では自動識別モデルの精度と実映像が足りないので、**最初の1フレームで6艇を人が指定する半自動追跡**を追加した。

`scripts/mikuni_six_boat_tracker.py` は OpenCV `calcOpticalFlowPyrLK` の順方向・逆方向誤差確認を使い、①〜⑥の初期中心を追跡する。同時に水面外の固定目標6点以上を追跡し、`findHomography(... RANSAC)` によりカメラのパン・ズームに由来する見かけの移動を補正する。

OpenCVの参照資料：<https://docs.opencv.org/doc/doxygen/html/dc/d6b/group__video__track.html>

固定目標が消えた、追跡が失敗した、艇同士が近すぎて識別が曖昧になった、突然映像が切り替わった場合は**そのフレームを未測定**にする。推測で補完したり、色の位置から艇番を自動確定したりしない。

出力：
- `boatlabs.mikuni_seeded_six_boat_pixel_tracks.v0.1`（候補データ）
- `camera_stabilized_center_px`（補正後の画素座標）
- `median_stabilized_apparent_motion_px_per_s`（補正後の見かけの動き）
- `candidate_fully_tracked_boats`（最後まで追えた候補ラベル数）

**これらは艇の実速度(m/s)や旋回半径(m)ではない。** 静止目標の実測水面座標・カメラ透視補正・艇番検証がないため、正式／シャドー予想への入力は禁止。

## 個人の許可済み映像から初期位置を作る

1. [BOAT LAB｜端末内の動画フレーム解析](https://cigusc-qydga1-sivwix.github.io/autonomous-boat-ai/local-video-bridge.html?date=2026-10-28&venue=%E4%B8%89%E5%9B%BD&race=7)を開く。
2. 三国の許可済み動画ファイルを選び、展示の場面が現れる秒数に「読み取り開始位置」、間隔を**0.5秒**に設定して最大24フレームを抽出する。ブラウザでは撮影・保護制限を回避しない。
3. **最初のフレームだけ**を選び、艇①〜⑥の中心を確実に確認して各1点をタップ。さらに岸の看板・岸壁の角など、**動かない固定目標を6点**、画面の広い範囲で選ぶ。水面の泡・波・ボート・画面内の文字は固定目標として使わない。
4. 「三国の6艇・岸6点の追跡用JSONを書き出す」。端末の動画ファイルが120MB以下ならSHA256を端末内で計算できる。大きいファイルの場合は、**同じ動画ファイルのSHA256**を入力する必要がある。サーバーへ動画はアップロードされない。
5. ファイル `mikuni-6boat-seeds-YYYY-MM-DD.json` が生成される。実研究に接続するには `app/data/experiments/mikuni-6boat-seeds-YYYY-MM-DD.json` へ保存し、開催日・レース・元動画SHA256がサーバー側と一致する必要がある。
6. **別途、配信元が認めた直接動画ファイルの取得先**を GitHub secrets/vars に設定する。`MIKUNI_VIDEO_SOURCE_TEMPLATE` と `MIKUNI_VIDEO_ALLOWED_HOSTS` が未設定なら、初期位置JSONだけでは全自動取得は始まらない。

> 初期位置JSONは、選択した映像でのラベルの仮説。独立の正しい艇番確認や水面の距離計測を証明するものではない。個人的な研究範囲を超えて他者の動画・映像を転載しない。

## 研究データの流れと品質ゲート

```
許可済みHTTPS動画 (不明なら取得しない)
    ↓ 120MB上限、SHA256、HTTPS+承認ホスト
メモリ内で0.5秒間隔・最大48フレーム（動画とJPEGを保存しない）
    ↓
白/黒/赤/青/黄/緑の領域候補（未検証）
    ＋ SHA・日時・R一致の6艇＋岸6点の初期位置
    ↓
LK追跡 + カメラ補正（未検証の画素軌跡候補）
    ↓
app/data/experiments/mikuni-video-auto-YYYY-MM-DD.json
    ↓
独立した人/機械の精度検証と水面[m]校正が必要
    ↓ まだ未完成・予想への接続禁止
検証済み6艇の軌跡 -> 締切120秒前までのシャドー予想
    ↓
前向きA/B検証後にのみ正式モデルの採否を判断
```

### JSON形式

ルートは `schema=boatlabs.mikuni_seed_library.v0.1`、`event_date=YYYY-MM-DD`、`venue_code=10`、`records` にレース単位の `boatlabs.mikuni_video_seed_annotations.v0.1` を入れる。含まれる値は
- `race`（1〜12）、`source_sha256`（対象動画の64文字SHA256）、`clip_start_seconds`（0〜300）、`sample_interval_s=0.5`、`reference_frame_index=0`、`frame_size={width,height}`
- `boats`：`lane=1〜6`、`center_px=[x,y]`
- `static_landmarks`：固有 `id` と `center_px=[x,y]` が6点以上

座標は**動画解析処理と同じ640px上限に縮小した映像**の画素座標で、ピクセルサイズが違えばエラーとして停止する。

### 運用の制約

- 元動画・フレームを保存しない。数値候補、sha、品質監査だけ保存。
- `boatlabs.verified_six_boat_tracks.v1` は**自動作成しない**。艇番の自動識別・1マークの距離・0〜5m、5〜15m、15〜30m区間速度は未実装。
- 正式v1.5、シャドー評価、収支記録、オッズ、結果照合を変更しない。
- 三国での個人研究の許可があっても、独立の映像配信事業者の自動取り込み条件は別に確認する。YouTube/JLC/BOATCASTのストリームURL推測、DRM解除は行わない。
- プロトタイプの技術検証は**合成映像**で成功。三国の実展示映像からの艇番追跡成功例はまだ0件。

## 自動テスト

```bash
python -m unittest discover -s tests -p test_mikuni_six_boat_tracker.py -v
python -m unittest discover -s tests -p test_mikuni_video_motion_pipeline.py -v
node app/tests/local-video-bridge.test.js
```

CI `.github/workflows/mikuni-six-boat-vision-tests.yml` がOpenCVを実際にインストールして、カメラ移動のある6艇合成映像・場面切替・艇種点欠損・違うSHAをテストする。テストスキップを成功とはみなさない。
