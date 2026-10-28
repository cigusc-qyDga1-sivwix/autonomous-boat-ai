# BOAT LAB 三国公式展示映像｜国内環境からの接続実験

更新日：2026-10-28。研究利用について三国から許可済み（利用者申告）。**これは動画自動取得ではなく、正規ブラウザ経由の再生APIの接続試験**。JLC/BOATCAST等の第三者配信元の利用条件を守ること。

## 何が進んだか

2026-10-28のGitHub ActionsにおけるJLC三国1Rは、公開ページHTTP200、プレイヤー設定HTTP200、Streaks再生APIの通常GETが **HTTP403 / `REQUEST_FAILED` / id124**。GitHubクラウド発アクセスへの地域制限が有力仮説だが、原因は配信元未確認。同じテストを、本人が正規に視聴できる日本国内の通常回線で再実行すれば切り分けが可能。

## 国内のMac/Linux PCで実行

要件：信頼できるDocker Desktop/Engine、Git。公式映像を国内の正規回線で通常視聴可能であること。VPN/プロキシによるアクセス制限の回避はしない。

```bash
git clone https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai.git
cd autonomous-boat-ai
bash scripts/check_mikuni_domestic.sh --date 2026-10-28 --race 1
```

2回目以降は `bash scripts/check_mikuni_domestic.sh --date YYYY-MM-DD --race 1` の1コマンド。日付省略時は日本時間の当日、R省略時は1R。最新コードに更新する際は事前に出所と差分を確認してから `git pull`。

### Windows PC（PowerShellとDocker Desktop）

```powershell
git clone https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai.git
cd autonomous-boat-ai
powershell -ExecutionPolicy Bypass -File scripts/check_mikuni_domestic.ps1 --date 2026-10-28 --race 1
```

実行ポリシーを恒久的に変更する必要はない。PowerShellから既知のローカルファイルだけ実行する。Docker未導入の場合、公式Docker Desktopのセットアップを先に行う。

**iPhone単体ではこのDocker/Chromium検証を実行できない**。端末の国内回線だけがあってもGitHub上の実行環境を自動的に国内へ変更できるわけではない。

## 自分で管理する日本国内Linuxサーバー（省略可）

`Settings > Actions > Runners` から、**公開リポジトリのself-hosted runnerについてセキュリティ上のリスクを理解した場合に限り**本人管理の専用Linux端末を登録し、`jp-licensed-research` の固有ラベルを付ける。コード・PR・Actionトークンを無関係な利用者が変更できないようにし、検証以外の機密情報を置かない。

その後、GitHub Actionsの `BOAT LAB Mikuni Japan-origin replay access diagnostic` をmainブランチで手動実行。**ランナー未登録ならジョブは実行できない**。登録・端末の起動・通信の条件整備はChatGPTから自動実行できない。

## どんな結果なら次に進める？

- `BOTH_PROFILES_HTTP_403`：クラウド同様にAPI接続拒否。URLの推測や認証の偽装はしない。
- `HTTP_RESPONDED_BUT_ACCESS_UNCONFIRMED`：200以外の応答あり。HTTP種別の追加診断が必要。
- `NORMAL_GET_RESPONDED_2XX_VIDEO_NOT_VERIFIED`：**再生APIの通常GETが2xx**。動画ファイル取得・デコードは依然未実証であり、利用条件と正規配信手段を確認して別工程に進む。
- `NO_BROWSER_GET_RESPONSE`：公開ページ表示やアコーディオンの同期に問題がある可能性。
- その他：コンテナ・ネットワーク・ページ構造の診断が必要。

結果はコンソールに出る安全なJSONのみ。IP/現在位置、再生URLのクエリ、APIトークン、クッキー、原本映像、動画フレームは含めない。保存先は明示`--out`で指定した時だけ。動画を生成・保存したときの指標である `verified_official_video_races`、`video_bytes_downloaded`、`six_boat_tracks_verified` は**必ず0**で出力する。

## 技術・セキュリティ上の制限

- マイクロソフトのPlaywright Python Chromium公式イメージを使用（v1.55.0 noble）。Pythonモジュールは固定バージョン。ブラウザは通常の正規アクセスに限る。
- Docker実行時は非root・読取専用ファイルシステム・一時領域・メモリ/CPU/PID制限・Linux capabilities削除を採用。実環境の動作は接続先PCで別途確認が必要。
- ブラウザのGETは通常の公開再生ページが送るものに限り、最大5件。原本映像、HLS、DASH、動画セグメントのリクエストはブロック。403レスポンス本文は非常に小さなJSONで許可されたコード項目だけを監査。
- 動画の正式なフレーム取り込みには別途、**利用許諾範囲の配信経路**と、原本SHA256・取得UTC・日付/R・FFmpeg実デコード・6艇識別精度の実測が必要。
- 発走前の正式予想・結果・収支は一切変更しない。事後実験は正式的中に数えない。
