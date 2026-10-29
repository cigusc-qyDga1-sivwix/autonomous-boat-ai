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

## 2026-10-28 夜｜国内Windowsの新タブがEdge内部画面になる問題

ユーザー実測：JLC公開ページ200、10/28・1Rの厳密一致1件、`race_click_status=CLICKED_EXACT_RACE_VERIFIED_DAY_CONTAINER`、新規タブ2件、`new_tab_url_type=BROWSER_INTERNAL`、再生API GET0、映像取得・解析0。ユーザーの**通常Edgeで同じ公式展示リプレイは手動再生できる**。

原因を切り分けるため、公式HTMLの当該 `a.stream_a` が`href`属性を持たず、インライン`onclick`属性もないことをGitHub Windows Edgeの公開DOM診断で確認。イベントリスナーによる動的挙動などが考えられるが、原因はまだ未確定。

修正版は、これまでの `element.click()`（信頼されたユーザー操作として扱われない場合がある）ではなく、Chromium DevTools Protocol `Input.dispatchMouseEvent` で、**対象日/1Rの唯一のボタンに対するマウス移動→押下→離す操作**を実行。座標は対象要素から直接計算し、範囲を検証。特定日/指定Rの一致が1件でない場合はクリックしない。セルフテストでブラウザ側のクリックイベント `isTrusted === true` を確認。

また、新タブが `BROWSER_INTERNAL` の場合に `new_tab_internal_kind` を追加し、Edgeの新規タブ・Chromiumエラー画面等を区別する。閲覧URL/パス/クエリや認証ヘッダー、Cookie、映像等は保存しない。JLCレースリンクの `race_link_kind`、`race_link_target`、`race_link_has_inline_handler` のような安全なクラス情報のみ表示する。

国内Windowsでの通常操作の成功と、隔離したヘッドレスEdgeでのAPIアクセス成功とは**別**。映像のバイト・フレーム・6艇識別の検証は依然0件。自動でログイン情報を読み出さず、制限回避もしない。

ユーザーは従来の `check_mikuni_edge_latest.ps1` をmainから更新して実行し、`race_click_status`, `new_tab_internal_kind`, `new_tab_url_type`, `playback_api_statuses` の4項目のみ共有。恒久的なPC設定変更やDockerは不要。

## 2026-10-28 追加診断：通常表示Edgeとの比較（未実機検証）

既存のヘッドレス診断で新タブが`BROWSER_INTERNAL`となる一方、利用者の通常Edgeでは同レースを手動再生できた。ブラウザ表示モードによる違いを切り分けるため、オプション`-VisibleEdge`を追加。**通常操作に使っているEdgeに接続せず、毎回一時プロフィールの別Edgeウィンドウを起動**する。Cookieや保存ログイン情報は引き継がない。動画・フレームは保存しない。

同じGitHubの最新`.ps1`をダウンロードし、ダウンロードフォルダで次を実行する：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check_mikuni_edge_nodocker.ps1 -Date 2026-10-28 -Race 1 -VisibleEdge
```

比較指標は`edge_start_mode`（`VISIBLE_ISOLATED` / `HEADLESS_ISOLATED`）、`race_click_status`、`new_tab_url_type`、`new_tab_internal_kind`、`playback_api_statuses`。新タブへの接続条件が同じになるかを確かめるための**試験機能**で、Windows実機での成功はまだ確認していない。通常ブラウザのCookieを抜き出したり、配信制限を回避したりしない。共有する際は動画のURL全文・クエリ・Cookie・トークンを貼らない。


## 2026-10-29｜自動再生のタブ不検出フォールバック（実機追試待ち）

利用者のWindows実測：`-VisibleEdge -AutoPlay` にて、`race_icon_target_day_matches=1`、`race_click_status=TRUSTED_MOUSE_CLICK_EXACT_DAY_AND_RACE`、`browser_tabs_after_click=1`、`playback_auto_click=NOT_ATTEMPTED`。他方、利用者スクリーンショットでは正規JLCプレイヤー `streamer26pi.php` が別のEdge窓で開き、手動再生ができている。**再生ボタンへの自動クリック自体は未試行**であった。

対応：選択日と正確なRが1件だけ確認済みで、CDP検出ページが1つのときに限り、利用者が通常表示できたJLC公式**プレイヤーページ**（`https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pi.php`）へ同一CDPタブから移動し、正規の再生ボタンを自動クリックする。ページURLは`tenji=1&jo=10&race=01&date=20261028`の形式で日付・レースから構成し、API秘密情報は使わない。

`-AutoPlay`明示時だけメディアのリクエストブロックを解除して**ブラウザでの通常の動画視聴**を許す（動画ファイル／フレーム／認証情報を収集・保存しない）。`playback_auto_click` と新しい `replay_navigation_mode` をログに表示。再生確認には実機で`VIDEO_ELEMENT_PLAYING`が必要。プレイヤー側がiframeや独自UIを使う場合は、現状`PLAY_CONTROL_NOT_UNIQUE`等で安全停止する。回避技術や無差別クリックは行わない。

使い方：`-Date 2026-10-28 -Race 1 -VisibleEdge -AutoPlay`。実測未完了のため、正式予想・結果・収支は変えない。


## 2026-10-29｜「File not found.」実機障害への修正

実機の `-VisibleEdge -AutoPlay` で、以前の修正による `Page.navigate` の直リンク（`streamer26pi.php`）から「File not found.」が表示された。公式の展示一覧には2026年10月28日開催が引き続き掲載されているため、日付の期限切れかどうかは未確定。直接構築したURLは、一覧経由の通常操作と同等と見なせない。

**修正：** 手動構築した公式プレイヤーURLへの強制遷移を廃止。既存のJLC一覧画面から正確な日付/レースを操作した後、同じCDPセッションの唯一のタブが公式プレイヤー自身になっている場合だけ再生ボタンを検査。確認できない場合は `PLAYER_TARGET_NOT_ATTACHED_NO_CLICK` と `NATIVE_CLICK_ONLY_NO_DIRECT_URL` を返し、再生ページを憶測で生成しない。既知のサーバーエラーテキストは `SERVER_REPLAY_FILE_NOT_FOUND` と区別。動画の保存/URLクエリ出力/認証回避は行わない。

この修正は安全な診断の正確性を改善するものであり、別プロセスのEdge窓を自動制御できる保証はまだない。結果のスクリーンショットから、実際にUIで再生できたか、CDP側が公式プレイヤーを捉えられたかを分けて確認する。


## 2026-10-29｜PLAYER_TARGET_NOT_ATTACHED_NO_CLICK の原因分離

利用者のWindows検証で `browser_tabs_after_click=1`、`playback_auto_click=PLAYER_TARGET_NOT_ATTACHED_NO_CLICK` が再現。公式JLCのプレイヤー自体は以前に別Edgeウィンドウで表示可能だった。CDP監視下のタブが1個であることは、ポップアップが実際に存在しない証拠ではない。

診断機能に `Page.windowOpen` イベント監視を追加した。イベントのURLは保存・出力せず、`window_open_events` 件数と、公式JLCプレイヤーで `date/jo/race` が厳密一致したかを `window_open_kind` として記録。 `OFFICIAL_PLAYER_MATCHED` なら、JavaScriptが公式プレイヤーのウィンドウを開く要求を発したことは確認できるが、別プロセスの実在・自動操作・再生成功までは示さない。

`NO_WINDOW_OPEN_EVENT` の場合はフォーム送信、別プロトコル、プレイヤー側イベント経路などを調べる。既定の診断や `-VisibleEdge -AutoPlay` に追加リスクはなく、再生の強行・URL推測・認証回避・映像保存はしない。Windows実機の次回観測待ち。


## 2026-10-29｜CDPポップアップイベント0件／通信遮断との切り分け

実機で`window_open_events=0`、`PLAYER_TARGET_NOT_ATTACHED_NO_CLICK`、`opaque_requests_blocked=1` が確認された。これは1RにCDPのマウス操作を送信したことを示すが、クリックが本当に対象リンクに到達したかは未確認。また診断用のXHR遮断が公式サイトの正常な画面遷移に影響した可能性がある。根本原因はまだ断定しない。

変更：
- 再生を明示した`-VisibleEdge -AutoPlay`のみに限り、日付とRを厳密に確認してから、公式ページのリンクをクリックする**直前**に`Fetch.disable`を行う。一般的な診断・CIは従来の通信遮断を維持する。ブラウザの通常視聴通信を許可するだけで、映像ファイル/フレーム/認証データはプログラムへ保存しない。
- `document.elementFromPoint`でクリック座標に本物のリンクまたは子要素があることを検証。曖昧な場合はクリックしない。
- `race_click_hit_verified`（座標検証）、`race_click_event_observed`（ページ側のクリック発火）、`fetch_mode_at_race_click`（通信モード）、`opaque_requests_blocked_before_click`（事前遮断数）を追加。
- URLの組み立て・直アクセスを再導入しない。メディア取得成功・6艇識別は未確認のまま。正式予想/照合/収支は変更しない。


## 2026-10-29｜実機race_click_hit_verified=falseの座標補正

ユーザーPCで `race_icon_target_day_matches=1`、`race_icon_visible_exact=1`、しかし `race_click_hit_verified=false` のためクリック停止。旧コードは1Rアイコンを含む`<a>`の矩形中心で`elementFromPoint`を検証していたが、リンク矩形の中心が画像自身の位置と一致する保証がない。

改修：ユニークな対象日・対象Rの画像そのものをスクロールし、**画像矩形の内部**の中心と限定した4つの近傍を検証する。位置を突き抜ける別リンク・オーバーレイがあるときにはクリックしない。クリック可能な1Rアイコン内に本来のリンクか子孫がある場合のみ`race_click_hit_verified=true`にする。

新フィールド`race_click_hit_reason` は `EXACT_DAY_RACE_ICON_HIT`、`ICON_OFFSCREEN`、`ICON_OBSCURED_BY_OTHER_ELEMENT` 等の非機密分類。画像のスクリーンショット／座標・URL全文・動画を保存しない。正式予想/結果/収支には触れない。Windows GitHub CIは自己テストであり、現地PCの動画自動再生成功ではない。


## 2026-10-29 夜｜クリック検証成功・内部タブを誤って公式プレイヤー扱いしない

利用者のWindows実機で `race_click_hit_verified=true`、`EXACT_DAY_RACE_ICON_HIT`、`browser_tabs_after_click=2` を達成。ただし追加タブは `new_tab_url_type=BROWSER_INTERNAL`、`new_tab_internal_kind=EDGE_OTHER_INTERNAL`、`window_open_events=0`、`race_click_event_observed=NOT_OBSERVED`。従来の `OBSERVED_OFFICIAL_POPUP` という表示は誤解を招くため修正。

- Edge/Chromiumの内部タブを公式プレイヤーとは呼ばず、`BROWSER_INTERNAL_NOT_OFFICIAL_REPLAY` および `NO_VERIFIED_PLAYER_TARGET_NO_CLICK` と明記。自動クリックしない。
- DOM側の正しい1Rリンクに届いた**信頼されたclickイベント**が一時的に記録されると、DevToolsの `Runtime.consoleAPICalled` に固定マーカーを発行。診断はこの固定文字列だけを識別して `trusted_race_click_delivered` を出力。ページ内の他のコンソールログやURLは取得・保存しない。ページがすぐ遷移してもイベント通知が届けば切り分け可能。
- 既存の `race_click_event_observed` が `NOT_OBSERVED` でも、ページ遷移によるリセット等で観測できない場合があるため、それだけでイベント未到達と断定しない。
- 手動ログイン・アクセス制御の回避なし。動画・フレーム保存なし。正式買い目/結果/収支不変更。再生の実機成功は未確認。


## 2026-10-29｜信頼されたクリック未観測時のマウス入力経路検証

現地Windows実測で対象1Rのヒットテスト成功（`EXACT_DAY_RACE_ICON_HIT`）にもかかわらず、`trusted_race_click_delivered=false`、`race_click_event_observed=NOT_OBSERVED`、新タブ1件だった。これはマウス入力イベントが届かなかった可能性と、監視側の取りこぼしを区別できない。

今回の改善は：1Rのリンクでだけ `mousedown`、`mouseup`、`click` の **信頼された**イベントをそれぞれ固定マーカーに変換して記録する。対象のページは `Page.bringToFront` で前面化し、レースリンクがDOM内に残っていて元のマウス座標下にあることを再検証。途中で対象が消失・移動すればクリックを打たずに `RACE_TARGET_CHANGED_BEFORE_CLICK_NO_CLICK` と報告する。ログに `race_mouse_down_seen`、`race_mouse_up_seen`、`race_click_seen`、`race_click_point_rechecked` を追加。旧 `document.addEventListener(...,{once:true})` は別クリックで消費され得るため改めた。

PowerShellのヘッドレス自己テストでこの3種類のイベント観測が正しく動くことを検証する。Windows/Edgeの実機自動再生成功、動画バイト取得、6艇の追跡は依然未確認。動画・認証・ページ内の機密情報保存なし、正式予想や収支には変更なし。


## 2026-10-30｜JLC PC版へ転換（初期診断版）

ユーザーのWindows/EdgeでPC版 `https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl=1` の三国展示リプレイが**手動再生できた**ことを確認。PC版は公式にWindowsおよびChromium Edgeをサポートするため、スマホ版の自動クリック修正は保留にしPC版へ移行。

既存スクリプトに `-PcSite -VisibleEdge` を追加。公式PCの入口ページだけへ遷移し、その後は一時プロファイルのEdgeでユーザーが**手動**で三国展示リプレイを再生する。PowerShellのEnterで制御下のJLCページについて、同一オリジンフレーム内の動画要素・再生中要素の件数、展示リプレイ/レース選択メニュー候補数を取得する。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check_mikuni_edge_nodocker.ps1 -PcSite -VisibleEdge
```

これは**PC版のDOM構造・ブラウザ再生状態を把握する診断**であり、日付・Rを選ぶ自動操作はまだ搭載していない。動画要素はクロスオリジンiframeに埋め込まれている場合があるため、0件は再生失敗の断定ではない。動画本体やスクリーンショット、ページ文字列、URL全文、Cookie、認証情報を収集・保存しない。従来スマホ版フロー、正式予想、結果照合、収支は一切変更なし。

次の段階でPC画面構造に基づいた「展示→三国→日付→1R→再生」各操作の自動化を個別に実装する。動画フレーム取得・6艇追跡はまだ未完成。


## 2026-10-30｜PC版のvideo未検出原因を分類

ユーザーのWindowsでは`iframe_count=2`、`accessible_frame_count=2`（親ページ込み）、`video_elements=0`、`playing_video_elements=0`。PC版の再生失敗を示すとは限らず、クロスオリジンiframeまたは別の埋込方式があり得る。診断用Edge内で実際に再生したかも前の診断では不明。

`-PcSite -VisibleEdge` のHTML観測に、`inaccessible_frame_count`・`object_elements`・`embed_elements`・`canvas_elements`を追加。終了時に**この診断で開いたEdgeで再生できたか**をY/Enterで入力し、`pc_manual_playback_reported`を記録。これは目視の自己申告とプログラムが検出したHTML動画の再生を混同しないため。

動画・映像フレーム・全文URL・認証情報は収集しない。正式予想・結果照合・収支と従来のスマホ版診断はそのまま。


## 2026-10-30｜PC版場番号の修正：桐生01→三国10

ユーザー実機で`-PcSite -VisibleEdge`実行時に桐生ページが表示されることを確認。原因はスクリプト内のPCエントリー`?tpl=1`が桐生（01）を意味するのに、三国のつもりで固定していたこと。

公式JLCの場リンクに対応する`https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl=10`（三国）へ修正。これが場の入口であって再生動画URLではないことを明示。新診断`pc_requested_venue=MIKUNI_10`と`pc_venue_url_verified=true`はサイトURLの選択チェックであり、動画/レースの選択成功を意味しない。

スマホ版・正式予想・結果・収支・動画保存処理は変更していない。次は診断Edgeで三国のページが表示されるか確認する。


## 2026-10-30｜JLC PC版の別ドメインiframeをCDPで判定

実機診断：`pc_manual_playback_reported=true`（ユーザーが診断専用Edgeで目視再生）、`pc_inaccessible_frames_observed=1`、`pc_video_surface_diagnosis=CROSS_ORIGIN_OR_UNAVAILABLE_IFRAME`、`pc_playing_video_elements=0`。動画再生は目視で確認されているが、再生中のHTMLVideoElement自体をプログラムが確認したわけではない。

読み取り専用CDP `Page.getFrameTree` と `Target.getTargets` で、フレーム総数、JLC公式のフレーム数、別HTTPSホストのフレーム数、メインページと別オリジンのフレーム数、独立したiframeターゲット数を計測。URL全文・動画バイト・フレーム画像・認証情報・ページタイトル・CDPフレームIDは記録しない。

追加結果：`pc_observed_targets[].frame_topology`、`pc_frame_topology_status`、`pc_cross_origin_frames_total`、`pc_oopif_target_count`。

`iframe_target_total=0` でも別ドメインiframeが無いと断定しない。フレームが独立したレンダラープロセスに分かれていない場合、iframeターゲットが独立表示されないことがある。プレイヤー実体の特定、許可範囲の映像解析および自動再生は未完了。正式予想・結果・収支は一切変更しない。


## 2026-10-30｜独立した外部HTTPS iframeの再生状態を読み取り専用で検査

実機で `frame_total=2`、`frame_official_jlc=2`、`iframe_target_total=1`、`iframe_target_external_https=1` を確認。一方 `pc_manual_playback_reported=false` なので、今回の実行で動画が目視再生されたとは証明されていない。外部 iframe の実体が動画かどうかも未確定。

PC専用診断に `Get-Pc-External-Iframe-Video-Metrics` を追加。JLC公式ページを手動で表示したユーザーの隔離Edgeで、HTTPS外部iframeターゲットだけに`Target.attachToTarget(flatten=true)`で一時的に接続し、`Runtime.evaluate`でHTMLVideoElementの存在と再生中要素数、およびcanvas要素数のみ計測。完了後にセッションをdetachする。対象は最大4件。

追加ログ：`pc_observed_targets[].external_iframe_video_probe`、`pc_external_iframe_probe_status`、`pc_external_iframe_video_elements`、`pc_external_iframe_playing_elements`。

CDPコマンドにセッションIDを指定できるようにするが、従来の送信は変更しない。動画URL・トークン・フレームバイト・音声・スクリーンショット・Cookie・ページ本文は一切取得／保存しない。アクセス不能なら`EXTERNAL_IFRAME_NOT_ATTACHED_OR_UNAVAILABLE`を返し、再生成功扱いしない。今回も動画保存や正式予想修正はしない。
