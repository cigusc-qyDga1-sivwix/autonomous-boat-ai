# 三国｜個人研究の許可を前提にした動画自動収集 v0.1

**2026-10-28**: BOAT LAB利用者が「三国には個人利用・動画の自動保存・AI解析について確認し、問題ないとの回答を得た。動画は無断転載しない」と申告。**書面や提供元の直接動画URLは未取得**であり、ここにある記録は「使用者の申告」であって許諾書の代わりではない。

## 2026-10-28：YouTubeチャンネルの404診断と公式APIフォールバック

三国公式ページの「YouTube LIVE」は、運営が指定するチャンネルの **`https://www.youtube.com/channel/UCu-yP6WJQ0zcx5nmWhxvJEg/live`** にリンクする。チャンネル自体は有効で、2026年10月28日には「スポーツクラブ新田塚アーク杯 最終日 8:00〜」のライブ配信予定がBOATCASTにも確認された。

しかし、GitHub Actionsからチャンネル公開Atom `feeds/videos.xml?channel_id=...` の取得は HTTP 404 が発生した。YouTubeのRSSで一時的な404問題が過去にも報告されており、**404だけでチャンネル不存在と断定しない**。新しい自動発見は (1) `www.youtube.com` RSS、(2) `youtube.com` RSS、(3) 任意の**公式YouTube Data API v3**という順序。配信タイトルが「レース」「LIVE」ではなく大会名と「最終日」だけの場合もレース候補として認識する。

**APIバックアップを有効にするには**、GitHub `Settings → Secrets and variables → Actions` に Repository secret `MIKUNI_YOUTUBE_DATA_API_KEY` を設定する。Google Cloudで有効化した YouTube Data API v3 のキーが必要で、利用者の手動登録が必要。`channels.list(part=contentDetails,id=<公式ID>)`から公式アップロードプレイリストを特定し、`playlistItems.list`で公開**メタデータ**を読む。これらは低クォータの正規APIメソッドで、取得できるのは動画ID・公開日時・タイトル等のみ（動画本体の配布APIではない）。キー未設定でもRSSチェック・既存の展示収集は継続。

**動画データ取得の別の障害**：三国から個人研究利用の許可があっても、YouTubeや配信会社の利用条件と動画ファイル提供方法は別である。YouTube動画を非公認のダウンロードツールで収集する処理は実装していない。機械解析の実動画データが必要なら、権利者が直接交付するMP4ファイルや承認済みHTTPS提供URLを `MIKUNI_VIDEO_SOURCE_TEMPLATE` に設定する。書き込む生動画はCIの一時領域のみ、元動画公開・配布なし。

**もう一つの参考経路**：<https://boatrace-replay.jp/> にはログイン式の「動画共有システム」が存在する。ただし三国に利用権限があるシステムだと確認できたわけではないため、無断ログイン・認証突破・推測リクエストはしない。提供元の協力が得られたときだけ検討する。

## 追加検証：2025年4月1日改定の三国公式規程と正規の公開経路

公式の新しい規程 `https://www.boatrace-mikuni.jp/uploads/cdn/faq/files/20250401_race_eizo.pdf` により、**映像使用が認められる公開元は三国の公式YouTubeチャンネル**と指定されていることを確認した：
`https://www.youtube.com/channel/UCu-yP6WJQ0zcx5nmWhxvJEg`

ユーザーは三国場から「個人研究の自動保存・AI解析に問題なし」と説明されたと申告している。ただし、その口頭説明だけでは **YouTube利用規約に基づくYouTubeからの動画ダウンロード権限**や、JLCの配信サーバーに対する自動取得権限を証明できない。現時点で、適法な動画**ファイル**取得・解析成功は0件。

- 公式YouTube公開情報（Atom/RSS）だけは`scripts/mikuni_official_video_catalog.py`で定期確認。動画名・動画ID・公開日・公式再生URL候補を記録し、**動画や動画フレームは一切取得しない**。
- `app/data/experiments/mikuni-video-catalog-YYYY-MM-DD.json`に監査を保存する。`source_status=OFFICIAL_CHANNEL_RSS_METADATA_READ`は公開**メタデータ**の取得成功であり映像ファイル取得成功と同義ではない。
- `MIKUNI_VIDEO_SOURCE_TEMPLATE`は、YouTubeの再生URLやJLCリプレイのURLを入れる欄ではない。**公開元・配信事業者が実際に許可した直接動画ファイルのHTTPS提供先があるときだけ**設定する。公式規程で許される媒体に限定し、別提供元の例外利用が認められる場合はその明示的な確認が必要。
- 正式な実映像解析への最短ルートは三国が保有する動画の**直接提供**または明示的に承認した動画ファイル取得API。動画のIDをYouTubeの公式チャンネルから発見できても、映像バイトを取得するAPIとは異なる。

## 技術面の結論

三国の公式ページ：<https://www.boatrace-mikuni.jp/>、展示リプレイ案内：<https://livebb.jlc.ne.jp/bb_top/sp_bb/tvod_10.php>。

上記は再生**ページ**であり、MP4/WebM/AVIの直接動画ソースではない。JLC/BOATCASTを経由する場合には、配信システムの利用条件も別途適用される。公開ページを見られることだけでは、Pythonから動画本体を取得できる証明にはならない。

取得元が**直接のHTTPS動画ファイルURL**を提供したとき、手入力不要で毎レースの保存・フレーム研究を自動実行するための安全な収集器を配置：

- `scripts/mikuni_video_autocollect.py`：三国（jcd=10）専用。数値展示の6艇レース行があるRだけ、自動でURLを構築する。後日収集の場合も発走前予想SHAと混同しない。
- `.github/workflows/mikuni-authorized-video.yml`：三国モーニング時間帯に**10分間隔のベストエフォート実行**（GitHub Actionsは遅延や中止があり得る）。GitHubの別ジョブ、既存予想生成/結果照合処理は変更しない。
- `app/turn-vision-pilot-20261028.html`：**展示数値の取得R数／フレーム研究として動画取得できたR数／①〜⑥の真の艇識別・ターン計測数**を明確に分けて表示。
- 動画ファイルの生データはGitHubへ書き込まず、Actionsランナー上に一時保存し、フレーム色領域の候補カウント、内容ハッシュ、記録時刻のみ研究記録として保存する。許諾済み動画を他者に公開しない。
- 取得済みSHAと競走日・Rを用いて重複取得を避ける。取得失敗・HTTPエラーは状態のみ記録し、プライベートな直接動画URLやトークンをログや研究JSONに出さない。
- SSRF/不正なソースの遮断：HTTPSと管理者が明示したホスト名のみ許容し、異なるホストへリダイレクトされた場合は拒否。ウェブページ、HLSマニフェスト、暗号化された動画の不正取得やDRM解除は行わない。

### 有効化のための設定

GitHubリポジトリ `cigusc-qyDga1-sivwix/autonomous-boat-ai` の **Settings → Secrets and variables → Actions** に以下を設定する。

| 種別 | 名前 | 設定値 |
|---|---|---|
| Repository secret | `MIKUNI_VIDEO_SOURCE_TEMPLATE` | 供給元が承認した **動画ファイルのHTTPS URLテンプレート**。`{yyyymmdd}`, `{race2}`, `{race}`, `{jcd}`, `{date}`, `{venue}` が利用可能。URLの認証情報は外部に出さずsecretだけに置く。 |
| Repository variable | `MIKUNI_VIDEO_ALLOWED_HOSTS` | URLと全リダイレクト先の公式・承認済みホスト名（カンマ区切り）。**JLCやBOATCAST等は利用条件が確認できない限り追加しない**。 |

例として`https://videos.provider.example/mikuni/{yyyymmdd}/{race2}.mp4` という**架空URL**を示すが、実在のURLではなくこれを設定しても動画は取得できない。

上記２つが未設定の場合は、研究台帳に`AUTHORIZED_SOURCE_CONFIGURATION_MISSING`を記録して停止。**「自動収集成功」や「動画解析済み」としてカウントしない。** 動画ソースを勝手に推測して外部配信から収集しない。

### 現段階での解析能力

取得できた動画について、最大40フレーム・色領域候補をOpenCVで抽出する。`video_races_observed` は「動画が取得・フレームデコードできたレース数」であり**全6艇のターン測定成功数ではない**。

①〜⑥の真の艇識別、ターンマーク座標、カメラの俯瞰/透視補正、スタートライン0〜5/5〜15/15〜30m速度は引き続き未検証。既存の動画試作`boat-ai-pro/boat_ai/six_boat_motion.py`と接続するためには検証済み軌跡・水面座標が必要。正式予想や買い目、実際の投票、結果を一切自動変更しない。

### テスト

```bash
python3 -m unittest discover -s tests -p test_mikuni_video_autocollect.py
```

`cv2` が入っている環境では合成動画で色領域の簡易試験も実行される。GitHub Actionsでは、許可済みソースを設定した際だけ`opencv-python-headless`を導入する。元動画をダウンロードできない環境では、レースの動画解析結果を捏造しない。
