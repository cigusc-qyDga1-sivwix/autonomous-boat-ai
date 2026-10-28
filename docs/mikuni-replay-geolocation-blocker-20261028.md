# 三国 展示映像 403の原因分離と自動取得への移行ゲート

監査日: 2026-10-28。個人研究の自動保存・AI解析について三国場から問題ないと回答を受けたことは**利用者確認済み**。同じ許可の再申請は必要ない。ただしJLC/BOATCASTなど第三者配信サービス独自のアクセス条件は別で、成功/権利を推定しない。

## 実験結果と証拠
- GitHub-hosted Ubuntu 24.04、Playwright desktop / Pixel 7 profile、三国10/28 1Rをブラウザ操作: JLC公開ページ200、1R表示/クリック成功。
- `front.player.boatrace-cdn.jp` プレイヤーJSON: HTTP 200
- `livebb.jlc.ne.jp` のプレイヤー元テキスト: HTTP 200
- `playback.api.streaks.jp`: HEAD 401、通常ブラウザ GET 403、JSON `{"code":"REQUEST_FAILED","id":124,"status":403}`（機密情報を含むエラー文は記録しない）。
- リクエスト上の認証系ヘッダーは名前のみ監査。Origin/Refererの有無を確認し、ヘッダー値やCookie等を残さない。
- 公開ソフトウェアのStreaksクライアントは id=124 を geographic restriction、id=126 を API-key/credential-related refusal と**区別**しているが、本サービスの管理者による公式な理由の説明ではない。参考: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/streaks.py
- **実映像バイト 0、実映像デコード0R、6艇ID確認0R。** 合成テスト成功や公開ページ閲覧とは別集計。

## 結論と残る不確実性
優先仮説: GitHubの共有クラウド出入口が、配信APIの地域/IP/配信ポリシーで拒否された。認証ヘッダー不足、映像公開時刻、レースID整合、動画販売権等も未除外。**確定していない仮説を根拠にIP偽装・プロキシ・トークン再利用・DRM解除を追加しない。**

## 次の検証と実装判断
1. **日本国内で配信元の条件を満たす通常の視聴環境**で、公式ブラウザ再生が可能か比較する。
2. 許諾済み端末・回線の self-hosted Linux runner がある場合、GitHubの`Actions`から手動診断ワークフロー `mikuni-japan-origin-diagnostic.yml` を実行する。ラベルは `jp-licensed-research`。これは診断だけで、動画を取得しない。
3. 別の公式経路（BOATCAST）の公開ページ構造は `scripts/mikuni_boatcast_public_probe.py` で比較する。ただし同サイトの利用条件も適用される。
4. 公式の正規メディア配信源が利用できると判明した時のみ、既存 `mikuni_video_ephemeral.py` の直接MP4/WebM入力、または別PRの配信事業者承認済みHLSアダプタに接続する。
5. 実映像の`media_bytes>0`・原本SHA256・取得日時・開催日/R対応・FFmpegでのデコードフレーム > 0・カットオフ前取得を別々に測定。そこからようやく6艇追跡・校正・シャドー予想に進む。

## self-hosted runnerを使う前の安全条件
- 本人/配信事業者が認める日本国内の通常回線・端末だけで行う。VPN/トンネル等の制限回避手段を設計に入れない。
- `Settings → Actions → Runners` で管理者がLinux端末を登録し、固有ラベル `jp-licensed-research` を付ける。登録トークンやキーをリポジトリ・ログに記載しない。
- Python 3.11+ と Playwright 1.55.0 / Chromium を事前に用意する。常時稼働・セキュリティ更新の可能な専用環境が望ましい。
- 公開リポジトリに他者からの任意PRを実行させない。本診断は `workflow_dispatch` + main固定 + `contents: read` だけ。Runner上に原本動画、フレーム、HAR、トークンを残さない。
- ランナーが存在しなければワークフローは未実行のまま。それを成功と呼ばない。通常ブラウザアクセスができても、自動動画取得の権利や技術的動作が保証されたわけではない。

## 日次運用への統合禁止事項
元の`mikuni-authorized-video.yml`、全国24場の正式予想・資金配分・結果・研究台帳を改変しない。これらは現時点で影響を受けない。映像の取得が実測されるまで`confirmed_boat_tracks=0`と`video_races_observed=0`を維持する。
