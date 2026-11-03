# BOAT VISION AI

展示映像専用の独立した研究AI。数値BOAT LABの正式モデル・保存済み買い目・結果台帳を更新しない。

## 現在の機能

| 機能 | 実装・検証状況 |
| --- | --- |
| 許可済み直接HTTPS動画／ローカル動画の入力 | 実装済み。HTTP応答は模擬試験、実配信元での継続取得は未検証 |
| メモリ内デコード・自動区間選択 | 合成動画を実FFmpegでデコードして検証済み |
| 6色の候補検出・追跡・背景によるカメラ補正 | 既存アルゴリズムを再利用。合成映像のみ検証済み。艇番認定ではない |
| 6候補の同時連続追跡 | 区間・追跡鎖をまたいだ連結を除外。候補数と識別成功を区別 |
| 独立ラベルとの精度比較 | 位置誤差・検出漏れ・艇番混同・6艇一致フレームを測定。合成データで検証 |
| スタート後の実速度・旋回・出口加速・艇間連動 | 未実装／実映像で未検証 |
| 数値BOAT LABとの連携 | 未接続。正式・シャドー予想への利用は常に禁止 |

専用CIの成功は実展示映像の取得成功を意味しない。直近の取得状況は [PROGRESS_2026-11-03.md](PROGRESS_2026-11-03.md) を参照。

## 独立した構成と既存資産の再利用

- `analyzer.py`：従来の手動シード付き追跡JSONを分析する入口。既存の入力・出力スキーマは維持。
- `media.py`：既存の直接メディア受信・FFmpegデコード関数を移植。URL制限、容量制限、RAM内処理を再利用。
- `tracking.py`：`scripts/mikuni_auto_vision.py` のアルゴリズムを保持し、MODEL/SCHEMA名だけ独立版に変更。船体学習済み検出器ではなく、色領域と背景特徴点による仮説。
- `pipeline.py`：取得・デコード・追跡を別の状態として記録する実行入口。
- `evaluation.py`：別途作成した正解ラベルとの比較。予想・結果・オッズの入力は不可。
- `report_io.py`：数値JSONだけを保存。`app/`、正式予想・結果用ディレクトリ、入力ファイルへの上書きを拒否。

`scripts/`、`app/`、数値予想エンジンはimportしない。依存は標準ライブラリと、映像処理時のみNumPy/OpenCV/FFmpeg。別リポジトリは未作成であり、後でこのパッケージと専用CIを切り出す。

## 実行

Python 3.11以上、FFmpeg、NumPy/OpenCVが必要。CIではNumPy 1.26.4、opencv-python-headless 4.11.0.86を使用。

```bash
python -S -m vision_ai.run_tests
python -m vision_ai.run_tests --cv
python -m vision_ai.pipeline --manifest vision_ai/examples/source-manifest.json --video-file /path/to/authorized.avi --output research/vision/run.json
```

配信元から許可された直接ファイルURLが利用できる場合は、URLをコマンド引数やレポートへ出さず、`VISION_VIDEO_URL` と `VISION_VIDEO_ALLOWED_HOSTS` に設定して `--from-url-env` を使う。

```bash
python -m vision_ai.pipeline --manifest vision_ai/examples/source-manifest.json --from-url-env --output research/vision/run.json
```

配信ページやHLSプレイリストは受け付けない。プレイヤー内部のURL探索、DRM回避、動画や静止フレームの転載・リポジトリ保存は行わない。ローカルファイルは既に許可された入力を読み、追加コピーを作らない。

入力未設定・取得失敗・デコード失敗では状態JSONを残し、CLIは終了コード1を返す。解析できても候補0艇なら `NO_SUPPORTED_TRACK_CANDIDATES` と明示する。解析パイプラインが動いたことと、実艇認識を確認したことは別。

## 入力と出力の来歴

入力マニフェストは `boatlabs.vision_ai.source_manifest.v1`。日付・三国の場コード10・R・映像種別・既存の許可を参照する識別子を指定する。`expected_sha256` を指定した場合は不一致動画を解析しない。実映像入力が未確認のため、まず三国を対象とする。

出力は `boatlabs.vision_ai.media_candidate_run.v1`。映像SHA、マニフェストSHA、受信・処理時刻、選択区間、解析画像寸法、各処理段階を記録する。受信時刻を撮影時刻と見なさない。日付・Rはマニフェスト上の申告であり、映像との独立照合は未実施。

`declared_source_kind=real_exhibition` と書くだけでは実映像認定にならない。出力は常に `confirmed_boat_tracks=0`、`real_footage_independently_verified=false`、`physical_speed_calibrated=false`、正式・シャドー利用不可、買い目0件。色番号は艇番仮説に過ぎない。

## 精度評価

```bash
python -m vision_ai.evaluation --run research/vision/run.json --labels /path/to/independent-labels.json --radius-px 12 --output research/vision/evaluation.json
```

ラベル形式は `boatlabs.vision_ai.frame_labels.v1`。以下の項目を使う。

| 項目 | 内容 |
| --- | --- |
| `source_sha256/event_date/venue_code/race/declared_source_kind` | 対象runと完全一致 |
| `clip_start_seconds/frame_size/sample_interval_s` | 選択区間・縮小後画像寸法・フレーム時刻軸を完全一致 |
| `annotation_origin` | `independent_manual_review`。モデル出力のコピーは禁止 |
| `reviewer_reference` | 独立ラベル作成者・確認記録を示す識別子 |
| `frames` | 2フレーム以上。各要素に `frame` と6艇分の `boats` |
| 各boat | `boat_id:1..6`、`visible:boolean`、見える場合は `center_px:[x,y]`。見えない艇の座標はnull |

艇番を使わない一対一の位置対応を先に作り、対応した艇番が異なる場合を混同として数える。見えない艇は検出率の分母から除外。近すぎて区別不能な正解ラベルは、半径を下げるか遮蔽扱いとして明示する。評価はラベル付きフレーム上の生の色候補の位置・番号一致に限定し、IDF1や実速度精度を名乗らない。

ラベルの独立性・実映像性をコードだけで証明することはできない。高い一致率が出ても正式・シャドー予想への昇格はしない。

## 次の開発

1. 既存の許可範囲で利用できる直接映像入力、または許可済み実サンプルを接続して、実フレーム取得を確認。
2. 別途ラベルを作り、視点・波・反射・重なり・カメラ切替ごとに漏れと艇番混同を測定。
3. 検出器と追跡を改善し、水面校正・実距離・スタート／旋回／出口区間・艇間連動を検証。
4. 実映像・6艇・レース同一性・単位・取得／検証時刻が確認できた別スキーマだけで、将来の一方向JSON連携を設計。

将来の橋渡しには、少なくとも `event_date/venue_code/race/source_sha256/captured_at_utc/verified_at_utc/model_version`、6艇ID、校正単位、品質指標、独立検証記録が必要。締切前の安全余裕を満たした同一レースで前向き比較する。現在の候補スキーマを流用して正式化しない。過去の買い目と結果は保持する。
