# 三国：PC不要の動画研究と検証監査

既存GitHub Actionsは、三国の公開情報を調査し、許可された動画入力があれば無人解析を試みる。6艇色候補検出は合成映像で試験済み。WindowsのJLC PC版ではユーザーが対象レースを選んだ後、ブラウザのHTMLVideoElementを再生開始でき、再生時計の進行まで確認した。

ただし、2026-10-30の研究記録は `source_configured=false`、実映像解析0R、独立に確認済みの艇識別0。ユーザーは三国から個人研究目的の動画自動保存・AI解析（元動画は無断転載しない）の許可を得たと報告している。JLCでの閲覧・再生成功は、GitHub Actionsからアクセスできる直接動画ファイルの提供方法を証明しない。三国の利用許可と、独立した配信元のアクセス方式は区別する。

`scripts/mikuni_video_verification_gate.py` は既存の日次研究台帳を読み、次のように明確に区別する。

- `AWAITING_DIRECT_MEDIA_ENDPOINT`: 三国からの個人研究・動画自動保存・AI解析についてユーザー申告の許可は取得済み。ただしクラウドが利用する直接動画ファイル／正規APIの接続先が未設定
- `SOURCE_CONFIGURED_NO_DECODED_MEDIA`: ソースの設定はあるがデコードできた実映像がない
- `REAL_MEDIA_RESEARCH_UNVERIFIED`: 実映像の候補数値を得たが独立の6艇識別検証が未完了

すべて `video_ai_complete=false` のフェイルクローズ判定。元映像、画像、URL、Cookie、トークンは監査に保存しない。既存の`.github/workflows/mikuni-authorized-video.yml`で動画研究のたびに`app/data/experiments/mikuni-video-verification-YYYY-MM-DD.json`へ出力し、ソース情報と日付不一致、予想への不正な昇格があれば失敗させる。

この自動監査はユーザーのPCを要求しない。実映像を解析するための残る外部依存は、**利用条件に合う直接動画ファイル／APIの接続先とクラウドからのアクセス方法**（設定は`MIKUNI_VIDEO_SOURCE_TEMPLATE` secretと`MIKUNI_VIDEO_ALLOWED_HOSTS` variable）。未承認配信URLの推測やDRM回避は行わない。真の艇番識別や予想への反映には、独立の実映像検証が必要。

検証: `python -m unittest discover -s tests -p 'test_mikuni_video_verification_gate.py' -v`


## 2026-10-31 更新：許可と技術的接続を明確に分離

ユーザーが三国から個人研究での**自動保存・AI解析**について許可を得たことを再確認。監査項目 `venue_permission_status=USER_REPORTED_GRANTED_PERSONAL_AUTO_ANALYSIS_NO_REPOST` はユーザー申告の許可を示す。これは代理店/JLCの配信アカウント、動画の配布エンドポイント、GitHub Actionsでの実取得成功を意味しない。

直接動画ソースがない場合の状態を `AWAITING_DIRECT_MEDIA_ENDPOINT`／`DIRECT_MEDIA_ENDPOINT_NOT_CONFIGURED` に変更。許可取得をやり直す前提にしない。正規の動画配布経路が確認できたら既存のSecret/variableを使い、1Rで実入力テストへ進む。映像の無断転載やアクセス保護回避は行わず、6艇の実映像による精度確認まで正式予想に反映しない。
