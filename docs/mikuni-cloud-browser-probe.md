# 三国公式映像：GitHubクラウドEdge到達性テスト

ユーザーの自宅Windowsからは三国のJLC PC版で手動レース選択後に動画自動再生成功。ユーザー申告で個人研究の動画自動保存・AI解析の利用許可は取得済み。**GitHubから実動画を扱えるかは別の技術課題**。

この研究ブランチではGitHub ActionsのWindows hosted runnerでEdgeを起動し、JLCの公式PC入口（tpl=10）を**通常のブラウザ**で開く。公開画面の展示メニュー、1R候補、iframeやvideo要素の件数だけ調査する。日付・レースをプログラムが未選択なら再生成功を宣言しない。動画の取得、隠しURL収集、配信保護回避、画像・原本保存は行わない。

結果はGitHub Actionsの7日間保持の数値JSONアーティファクト。これでWindows PCを持たないGitHubクラウドから公式表示が可能かを確認し、続く日付/RのUI選択自動化の実装可否を判断する。

ステータスは OFFICIAL_PC_SITE_UNAVAILABLE、OFFICIAL_PC_ENTRY_ONLY、EXHIBITION_UI_VISIBLE_REPLAY_NOT_SELECTED、VIDEO_ELEMENT_FOUND_REPLAY_NOT_VERIFIED のいずれか。実映像を取得したり6艇を追跡した証拠とは扱わない。正式予想・結果・収支は不変更。


## 2026-10-31：展示リプレイの日付と1R選択群を見つける二段階診断

実際のGitHub Windows runnerでは公式JLC PC版の読み込み成功（`site_loaded=true`、1R候補33件、video要素0）。次にJLC公式スマホの展示一覧`/bb_top/sp_bb/tvod_10.php`をブラウザで開き、対象10月28日が表示されているか、日付セクション内に12個のR選択画像と1R画像が1個だけ存在するか数で確認する。

結果`archive_requested_day_visible`、`archive_day_group_candidates`、`archive_status`を追加する。場所や日にちの候補が正しく特定できても**まだクリックしない**。サイトの直接動画URLを推測せず、動画ファイル/画像を保存しない。


## 2026-10-31：GitHubで展示アーカイブを日付別に選択し、公式プレイヤーを確認

GitHubクラウドで10月28日の一意な12Rグループが見つかったため、そのグループ内の1R画像のみ通常のクリックで選択する試験を追加。開いたページの公式JLCホスト・再生ページ・`tenji=1`・`jo=10`・`race=01`・`date=20261028`を検証した場合のみ、HTMLVideoElement.play()を試し時計の進行を測る。正規の画面操作であり、隠し動画URLを推測・取得しない。

`player_status`が`CLOUD_OFFICIAL_REPLAY_CLOCK_ADVANCING`になるまでは成功を宣言しない。動画ファイル・画像・生画素は記録せず、正式予想・結果・収支は変更しない。


## 実測で確認した未突破箇所（2026-10-31）

クラウドEdgeでJLC三国公式ページと展示アーカイブは200系で表示され、10/28の対象日グループが1件に絞れた。だが`meeting_toggle_clicked=true`、`day_toggle_clicked=true`は見出しへのクリック発行を意味するだけで、折りたたみが展開された証拠ではない。実際の対象`1R`画像は`target_image_visible=false`であり、Playwrightは安全のためクリックを見送った。クラウド再生は**未達成**。

以降は非表示を明示的に`TARGET_IMAGE_COLLAPSED_NO_CLICK`として記録。誤レースのクリック、画像取得、隠しストリームURLの探索を行わない。開催節/日付が実際に開いたかをブラウザDOMの可視性で判定する修正が必要。

## 2026-10-31：開催節・日付を構造に沿って展開する方式へ変更

GitHub hosted Windows Edgeの実DOMでは、開催節・日付の両方が直接子要素`p`（見出し）と`ul`（格納されたパネル）で構成され、当初は両`ul`が`display:none`だった。

対象日に属する唯一の1R画像から`li`祖先をたどり、開催節の`p`と日付の`p`のみクリックする実装へ修正。結果、`meeting_children_visible=true`、`day_children_visible=true`、`target_image_visible=true`、`target_click_hit_verified=true`、`ui_click_attempted=true`をクラウドで実測した。

ただしその後のプレイヤーを確認できず、`NO_EXACT_OFFICIAL_DAY_RACE_PLAYER_OBSERVED`。別タブ、ポップアップ、埋込フレームから公式URL/日付/場/Rの一致を検証しても、当該プレイヤーを取得できなかった。HTML動画の再生・映像フレームの解析はまだ実証できていない。

## RAM内限定のAI映像研究モジュール

`scripts/mikuni_cloud_frame_research.py`では、**公式プレイヤーの対象日・場・Rが一致し、HTMLVideoElementの時計進行が確認された場合だけ**、Playwrightから見えている動画要素のPNGスナップショットをRAM内で最大10枚取得する。画像のデコード・動きの有無・色候補追跡をRAM内で実行し、数値のみ研究JSONへ反映する。PNG/JPEG/映像原本はファイルに保存しない。

停滞時計・静止/黒画面・複数動画要素などは「取得成功」と判定せず、初期色検出が6艇候補を返しても艇番本人確認・実距離較正・正式買い目への利用は未承認とする。

これを実映像で検証するには、配信元が提供する直接動画ファイル入力経路（既存の`mikuni_video_ephemeral.py`）か、クラウドの公式再生ページで実際に動画の時刻が進むことが必要。
