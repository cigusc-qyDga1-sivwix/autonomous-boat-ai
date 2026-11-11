# BOAT LAB 全国映像解析アダプター設計（2026-10-29）
対象：公式24場のうち、江戸川(03)を除く23場。これは映像研究の対象設定であり、全国の既存展示数値・結果収集は変更しない。

## 設計
- 場別設定 `scripts/nationwide_video_registry.py` がvenue code 01〜24を既存プロフィールから参照する。
- デフォルトは23場すべて `NOT_CONFIGURED`、江戸川は `EXCLUDED_BY_PROJECT_POLICY`。自動的な動画取得は0R。
- 配信元確認・利用条件確認・機械解析の許可確認・正規ブラウザ再生確認の4条件すべて成立後、かつ正規ホストが明示されて初めて`READY`。
- 候補URLはHTTPSおよび完全一致ホストのみ受理。今回追加するコードは実際のHTTPアクセスをしない。
- 三国の既存PowerShellは引き続き場専用の接続診断。全国版への実際の再生処理の接続は別PRで前向きに実証する。
- 同一の6艇識別・スタート伸び・1M/出口加速解析エンジンを再利用する設計。ただし場ごとの水面カメラ補正・コース座標・映像公開時刻は別校正が必要。**三国の設定や軌跡を他場へコピーしない**。
- 異なる映像配信元の権利・アクセス制御を推定しない。DRM解除、Cookie/token抽出、プロキシによる回避を行わない。
- 計測値は欠損を0の能力値とせず`UNVERIFIED`扱い。発走前の検証可能な映像だけで別SHAのシャドー予想を作り、正式買い目への反映は将来のA/B合格後に限定。

## 将来の接続インターフェース
`discover(venue, date, race) -> candidate` / `verify_access(candidate) -> status` / `decode_authorized_frames(candidate) -> frames` / `track_six_boats(frames, venue_calibration) -> measurements` / `freeze_shadow_before_cutoff(measurements) -> sha`。

**今回実装したのは構成台帳・許可ゲート・単体テストだけ**。23場の自動再生・実動画取得・測定精度・予想改善は未検証。Windows実機がない間の土台整備として扱う。
