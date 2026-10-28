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

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check_mikuni_edge_nodocker.ps1 -Date 2026-10-28 -Race 1
```

**ユーザーが安全性を確認した自分のGitHubのファイルのみを実行。** 不審なダウンロード、管理者権限、Windowsの恒久的な実行ポリシー変更は不要。Windowsがブロックした場合は無理にセキュリティを無効化しない。

## 何をする？

WindowsにあるEdgeを、普段のCookieやログイン情報を含まない**一時プロフィール**でヘッドレス起動。ポート番号はランダム、通信相手は自分のPCのlocalhostだけ。公開JLCページを開き、開催節→日付→1Rの表示上のクリックを試し、通常ブラウザが自然に要求した再生APIのHTTPステータスだけを記録する。

- 研究ソフトはフルURL、認証トークン、Cookie、IPアドレス、動画、スクリーンショット、フレームを保存しない。
- 既知のHLS/MP4/DASHなどのメディア要求と無関係なXHRは事前ブロックする。正規ページのその他のサブリソース通信は発生し得る。
- 終了後は新しく起動した専用Edgeプロセスを閉じ、利用した一時プロフィールを削除する。
- 表示だけのページ操作なので、発走前の正式予想・予想SHA・収支・全国収集は変更しない。

## 結果の見方

- `EDGE_SELFTEST_PASSED_NO_NETWORK` — `-SelfTest` 指定時にEdge制御の動作確認成功。接続自体は未検証。
- `PLAYBACK_API_HTTP_403` — Windowsからの通常API GETでも403。地域/接続条件の仮説を再評価する。
- `PLAYBACK_API_2XX_VIDEO_UNVERIFIED` — 通常GETの応答が200または206。**動画の自動取得・6艇の識別ができたという意味ではない**。
- `RACE_OPENED_NEW_TAB_UNINSPECTED` — 旧版で別タブの通信を監視できていない状態。
- `POPUP_CHECKED_NO_PLAYBACK_API_RESPONSE` — 新版で安全な新タブ診断まで終えたがAPI応答がない。
- `NO_PLAYBACK_API_RESPONSE` — ページ構造、開催日、再生処理など別原因を調べる。
- `EDGE_DIAGNOSTIC_FAILED` — Edgeの起動やDevTools接続に失敗。failure_stageで失敗段階を分離。

エラーの診断結果は `access_decision` と `playback_api_statuses` をChatGPTに貼ればよい。トークンやCookieは共有しない。

## 自己テストだけやりたい場合

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check_mikuni_edge_nodocker.ps1 -SelfTest
```


## 2026-10-28 22時台の国内Windows初回診断と追加対応

利用者が送ったPowerShell画面では、`landing_http_status=200`、`meeting_header_clicked=true`、`day_header_clicked=true`、`browser_tabs_after_click=2`、`access_decision=RACE_OPENED_NEW_TAB_UNINSPECTED`。**403解消や動画取得成功ではない**。ブラウザの別タブでプレイヤーが開き、元タブだけの監視では応答が見えなかった。

改良版は、別タブが正規の `front.player.boatrace-cdn.jp` / `livebb.jlc.ne.jp` / `playback.api.streaks.jp` のいずれかである場合のみ、独立DevToolsセッションを開き、メディア拡張子/Mediaタイプ/不明なXHRをブロックした**あと**再読込を一回実施する。接続状態を `new_tab_guard_status` と `playback_api_statuses` で監査。別タブが未知ホストなら絶対に自動再読込しない。

- `new_tab_guard_status=GUARDED_RELOAD_COMPLETE`：新タブの安全なブラウザ再読込診断が完了。**取得成功の意味ではない**。
- `new_tab_guard_status=UNRECOGNIZED`：予期しない配信先のため自動再読込せず中止。
- `POPUP_CHECKED_NO_PLAYBACK_API_RESPONSE`：再読込後も再生APIの応答を確認できない。**200/403いずれとも判定しない**。

Windowsでの利用：以前と同じGitHub URLから最新の単独`.ps1`ファイルを**再ダウンロードして置き換え**、前回の同じコマンドを実行。PowerShellを管理者として起動する必要はない。実際の映像や認証トークンは保存せず、`video_bytes_saved=0` を維持する。

## 技術的制約と未達項目

- 開催節/日付と選んだ1Rの関連付けは未検証のため、ログに `CLICKED_DATE_ASSOCIATION_UNVERIFIED` と明示する。
- レースボタンで別タブが開いた場合、元ページだけのDevTools通信監視ではプレイヤーAPIの結果を観測できない。`browser_tabs_after_click` の値と `RACE_OPENED_NEW_TAB_UNINSPECTED` を見て、**API 200/403が不明であることを明示**する。
- 一部の新しい映像配信はURLの拡張子が見えない。メディア要求を強制停止する保護は、識別可能な形式・ブラウザMediaタイプ等への適用であり、**映像のすべてのネットワークバイトを遮断できると保証しない**。実動画取得処理はまだ作っていない。
- JLC/BOATCASTの独自配信条件がある場合はそれを遵守。配信制限回避、VPN/IP偽装、DRM解除、認証トークン収集は実装しない。
- 国内Windowsからのアクセスが成功した場合、次の独立工程で、許諾範囲の取得先を実証し、実際のFFmpegフレームデコード・取得時間・6艇追跡精度を計測する。
- Microsoft Edgeは必ず実行PC上にインストールされている必要がある。企業管理PCでDevTools起動が禁止されている場合は無理に解除せず、手動の正規ブラウザ視聴チェックを代替にする。

## 2026-10-28 22:14 JST 実機スクリーンショット追跡

利用者の2回目の実測：
- `landing_http_status:200`、開催節/日付true、レースアイコン選択あり
- `browser_tabs_after_click:2`
- `new_tab_domain:UNRECOGNIZED`, `new_tab_guard_status:UNRECOGNIZED`, `playback_api_requests:0`
- **403が解消したと主張できず、動画バイト/解析フレーム/6艇IDは0**。

改善版では **新タブが`about:blank`状態である場合だけ最大3.6秒ほどURLの変化を待ち**、その後に`new_tab_url_type`（`ABOUT_BLANK_OR_INTERNAL` / `HTTPS_HOST` など）と、HTTPSで安全なDNSホスト名の場合に限り`new_tab_domain`に**ホスト名のみ**表示する。URLのパス・クエリ・認証情報・タイトル等は記録しない。公式として設定済みの3ホスト以外へはブラウザ再読込も認証操作もしない。

- `new_tab_url_type=ABOUT_BLANK_OR_INTERNAL`：新タブが空白や内部ページ。APIまで到達していない。
- `new_tab_url_type=HTTPS_HOST`で`new_tab_domain`が既存許可リストと違う：ホスト名だけを根拠に新しい正規配信元かを**別途確認**。その場で未知のURLを自動追跡しない。
- `POPUP_NOT_ALLOWLISTED_API_UNVERIFIED`：診断を安全のため止めたことを意味し、HTTP403でも動画取得成功でもない。
- `new_tab_guard_status=GUARDED_RELOAD_COMPLETE`：許可済み公式ドメインへの安全な再読込を実施。動画保存の成功ではない。

**実機から送ってほしいのは `new_tab_url_type`、`new_tab_domain`、`new_tab_guard_status`、`playback_api_statuses` の4項目だけ**。機密トークンやURL全体は送らない。ファイルは以前と同じmain GitHubリンクから最新版を1個だけ再ダウンロードし、前回と同じPowerShellコマンドで実行する。

## 2026-10-28 23:01 国内Windowsの追加診断

最新版を実行したユーザーのスクリーンショットでは `browser_tabs_after_click=2`, `new_tab_url_type=NOT_HTTPS`, `new_tab_domain=NOT_DISCLOSED`, `new_tab_guard_status=NOT_ALLOWLISTED_NO_REPLAY`, `playback_api_requests=0`。従って再生APIの200/403は**未確認**、動画取得・解析は0。

今回の改良版では、`NOT_HTTPS`を次のように分類し、URL自体は保存しない：
- `HTTP_HOST_NO_REPLAY`：新タブが通常のHTTP URL。DNSホスト名のみ`new_tab_domain`に記録。**HTTPページを自動再読込しない**。
- `BROWSER_INTERNAL`、`ABOUT_BLANK_OR_INTERNAL`：ブラウザの内部画面や読込途中。
- `LOCAL_FILE_NO_REPLAY`、`NON_HTTP_SCHEME`、`OTHER_SCHEME`：対象外。操作は止めたまま。
- `HOST_NOT_DISCLOSED`：IPアドレス・localhost・不適切なホスト表記。原則的に表示させない。

ユーザーはGitHubの既存スクリプトURLを`check_mikuni_edge_latest.ps1`として上書きダウンロードし、以前と同じコマンドを再実行できる。共有するのは`new_tab_url_type`・`new_tab_domain`・`access_decision`のみ。**資格情報、再生URL全体、画像付きでなくともURLのクエリ値は共有しない。**

## 2026-10-28 23時以降｜通常のEdgeで公式展示リプレイ再生成功（利用者実測）

ユーザーが**普段のEdgeで三国の2026-10-28 1Rを手動再生できた**と報告。国内回線で通常視聴可能なことを示すが、既存の一時・headless Edgeでの再生、映像ファイル取得、6艇解析を証明するものではない。

WindowsのJLC実DOM構造をCIで監査した結果、従来の `img[src*="1R.png"]` は `11R.png` まで一致し、全22件（11日×2つの1R/11R）を誤認。しかも、先頭2件は10/28の1Rと11Rの両方で表示状態だったため、**不正確なレースを開く危険**があった。

修正版：
- `(?:^|/)1R[.]png(?:[?#]|$)` でファイル名の正確な1Rのみ一致。
- `img > a.stream_a > td > tr > tbody > table > center > li > ul > li` の**日付ごとのli**まで遡って、日付文字列が10/28のみであることを厳格確認。
- `race_icon_matches` は厳密なレース番号一致のみ、`race_icon_visible_exact` は表示状態、`race_icon_target_day_matches` は選択日とレース番号の両方が一致する数。
- 対象が**ちょうど1件**で、開催節と日付の選択も成功した場合のみ、元の `a.stream_a` をクリック。曖昧・欠損ならクリックしない。
- 正しくクリックした場合 `CLICKED_EXACT_RACE_VERIFIED_DAY_CONTAINER` と記録。ただし動画の再生API取得成功は別途検証。
- `-LayoutAudit` は安全なHTML構造調査のみでクリック・動画受信せず。主に自動テスト用。

正式予想・収支と元の映像データを変更せず、動画取得と6艇識別の数は実測まで0のまま。
