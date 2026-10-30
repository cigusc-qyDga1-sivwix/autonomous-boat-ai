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
