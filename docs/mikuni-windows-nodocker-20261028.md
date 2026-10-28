# 三国展示の接続診断：Windows軽量版（Docker不要）

2026-10-28。個人研究用途について、利用者は三国ボートレース場から許可を得ている。本ツールは**正規に公開されたJLC展示リプレイのブラウザ接続状態の調査だけ**を行い、まだ実映像を取得・デコードしない。配信側の利用条件や認証を回避しない。

## 準備（約10KBのPowerShellファイル1個のみ）

**不要：Docker Desktop、Python、Node.js、Git、追加ブラウザ。**

必要なもの：Windows 10/11、標準搭載のMicrosoft Edge、Windows PowerShell 5.1、通常のインターネット回線。

1. 次のGitHubファイルをMicrosoft Edgeで開く：
   https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/blob/main/scripts/check_mikuni_edge_nodocker.ps1
2. 画面右上の **Download raw file** を押し、ファイル名を **check_mikuni_edge_nodocker.ps1** のまま「ダウンロード」フォルダーに保存。
3. ダウンロードフォルダーをエクスプローラーで開く。上部のアドレスバーを押して **powershell** と入力してEnter。
4. 次の1行を貼り付けてEnter（WindowsのPowerShellに対して今回のファイルだけ実行を許可）：

\`\`\`powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check_mikuni_edge_nodocker.ps1 -Date 2026-10-28 -Race 1
\`\`\`

**ユーザーが安全性を確認した自分のGitHubのファイルのみを実行。** 不審なダウンロード、管理者権限、Windowsの恒久的な実行ポリシー変更は不要。Windowsがブロックした場合は無理にセキュリティを無効化しない。

## 何をする？

WindowsにあるEdgeを、普段のCookieやログイン情報を含まない**一時プロフィール**でヘッドレス起動。ポート番号はランダム、通信相手は自分のPCのlocalhostだけ。公開JLCページを開き、開催節→日付→1Rの表示上のクリックを試し、通常ブラウザが自然に要求した再生APIのHTTPステータスだけを記録する。

- 研究ソフトはフルURL、認証トークン、Cookie、IPアドレス、動画、スクリーンショット、フレームを保存しない。
- 既知のHLS/MP4/DASHなどのメディア要求と無関係なXHRは事前ブロックする。正規ページのその他のサブリソース通信は発生し得る。
- 終了後は新しく起動した専用Edgeプロセスを閉じ、利用した一時プロフィールを削除する。
- 表示だけのページ操作なので、発走前の正式予想・予想SHA・収支・全国収集は変更しない。

## 結果の見方

- \`EDGE_SELFTEST_PASSED_NO_NETWORK\` — \`-SelfTest\` 指定時にEdge制御の動作確認成功。接続自体は未検証。
- \`PLAYBACK_API_HTTP_403\` — Windowsからの通常API GETでも403。地域/接続条件の仮説を再評価する。
- \`PLAYBACK_API_2XX_VIDEO_UNVERIFIED\` — 通常GETの応答が200または206。**動画の自動取得・6艇の識別ができたという意味ではない**。
- \`NO_PLAYBACK_API_RESPONSE\` — ページ構造、開催日、再生処理など別原因を調べる。
- \`EDGE_DIAGNOSTIC_FAILED\` — Edgeの起動やDevTools接続に失敗。failure_stageで失敗段階を分離。

エラーの診断結果は \`access_decision\` と \`playback_api_statuses\` をChatGPTに貼ればよい。トークンやCookieは共有しない。

## 自己テストだけやりたい場合

\`\`\`powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check_mikuni_edge_nodocker.ps1 -SelfTest
\`\`\`

## 技術的制約と未達項目

- 開催節/日付と選んだ1Rの関連付けは未検証のため、ログに \`CLICKED_DATE_ASSOCIATION_UNVERIFIED\` と明示する。
- 一部の新しい映像配信はURLの拡張子が見えない。メディア要求を強制停止する保護は、識別可能な形式・ブラウザMediaタイプ等への適用であり、**映像のすべてのネットワークバイトを遮断できると保証しない**。実動画取得処理はまだ作っていない。
- JLC/BOATCASTの独自配信条件がある場合はそれを遵守。配信制限回避、VPN/IP偽装、DRM解除、認証トークン収集は実装しない。
- 国内Windowsからのアクセスが成功した場合、次の独立工程で、許諾範囲の取得先を実証し、実際のFFmpegフレームデコード・取得時間・6艇追跡精度を計測する。
- Microsoft Edgeは必ず実行PC上にインストールされている必要がある。企業管理PCでDevTools起動が禁止されている場合は無理に解除せず、手動の正規ブラウザ視聴チェックを代替にする。
