# 三国：PC不要の動画研究と検証監査

既存GitHub Actionsは、三国の公開情報を調査し、許可された動画入力があれば無人解析を試みる。6艇色候補検出は合成映像で試験済み。WindowsのJLC PC版ではユーザーが対象レースを選んだ後、ブラウザのHTMLVideoElementを再生開始でき、再生時計の進行まで確認した。

ただし、2026-10-30の研究記録は `source_configured=false`、実映像解析0R、独立に確認済みの艇識別0。JLCでの閲覧・再生成功はGitHub Actionsの直接動画ファイル入力や配信者の承認を証明しない。

`scripts/mikuni_video_verification_gate.py` は既存の日次研究台帳を読み、次のように明確に区別する。

- `AWAITING_AUTHORIZED_DIRECT_MEDIA`: 許可された実映像入力が未接続
- `SOURCE_CONFIGURED_NO_DECODED_MEDIA`: ソースの設定はあるがデコードできた実映像がない
- `REAL_MEDIA_RESEARCH_UNVERIFIED`: 実映像の候補数値を得たが独立の6艇識別検証が未完了

すべて `video_ai_complete=false` のフェイルクローズ判定。元映像、画像、URL、Cookie、トークンは監査に保存しない。既存の`.github/workflows/mikuni-authorized-video.yml`で動画研究のたびに`app/data/experiments/mikuni-video-verification-YYYY-MM-DD.json`へ出力し、ソース情報と日付不一致、予想への不正な昇格があれば失敗させる。

この自動監査はユーザーのPCを要求しない。実映像を解析するための残る外部依存は、**配信元が明示的に許諾した直接動画ファイル／API入力**（設定は`MIKUNI_VIDEO_SOURCE_TEMPLATE` secretと`MIKUNI_VIDEO_ALLOWED_HOSTS` variable）。未承認配信URLの推測やDRM回避は行わない。真の艇番識別や予想への反映には、独立の実映像検証が必要。

検証: `python -m unittest discover -s tests -p 'test_mikuni_video_verification_gate.py' -v`
