# WEATHER LAB v0.1 — 全国24場の水面気象データ監視

## 目的

BOAT LABの予想計算から独立し、レース場の **風速・風向の生コード・波高・気温・水温** を監視する軽量なデータ収集サービス。収集・鮮度監査・保存を最優先する。

**v0.1は学習済みAIではない。** 外部LLMに毎回推定させる仕組みではなく、定義済みの規則で欠損・時刻・新鮮度を監査する。AIによる場別展開分析は、前向き検証データと風向の真方位情報が整ってから別モジュールで開発する。

## プロジェクト境界

- 予想モデルや展示データ、正式予想SHA、買い目、結果・収支は一切変更しない。
- **専用スクリプト**：`weather_lab/monitor.py`
- **専用GitHub Actions**：`.github/workflows/weather-lab-monitor.yml`
- **専用データ保存先**：同一リポジトリの独立ブランチ `weather-lab-data` の `weather_lab/data/latest.json` と日別JSON。 `main` への5分ごとのデータコミットは行わない。BOAT LABの予想更新とのGit競合を抑制するため。
- 現接続では新しいGitHubリポジトリの新規作成操作が利用できないため、コードと実行を独立させた構成で先行実装。将来別リポジトリへ `weather_lab/` と専用workflowを移植可能。
- 通知はOFF。スマホへのプッシュ通知や実投票は行わない。

## データソースの範囲

- 第一段階：BoatraceCSV `data/previews/sui/YYYY/MM/DD.csv`。
- これは**締切5分前を目安に記録された競走別スナップショット**。固定の連続気象計測ではなく、開催のない場や公開前はデータなしのままとする。
- 資料：https://boatracecsv.github.io/docs/data/previews.html
- 風向はプロバイダーの数値生コードとして保存する。向かい風／追い風／横風の分類は**風向の定義と場別コース真方位の検証後**。
- 水面気象と展示は別データ。気象の `気象観測時刻`（HHMM）を元に観測時刻を再構成するが、日付はレース日から推定したものと明示する。
- BOAT LABで従来除外する江戸川も**取得可否監視**には含めるが、予想対象外フラグを持つ。

### 鮮度判定（仮の研究閾値）

- `fresh_snapshot`：取得日時から15分以内かつ観測時刻から20分以内。
- `stale_source_capture`：取得元が15分より古い。
- `stale_observation`：実測時刻の再構成値が20分より古い。
- `observation_time_unverified`：時刻が無効／未来のため検証不可。
- `incomplete_values`：風速または波高が欠けている。
- `provider_unavailable`：取得元自体が応答しない。
- `no_race_snapshot`：対象場のレースデータがまだない。**取得失敗とは区別**。
- 風速0m/sで風向が未設定の場合は `calm_undefined` とし、障害として誤計上しない。

> 15分／20分は監視の初期設定であり、正式予想への安全条件でも予想精度が実証された閾値でもない。

## 潮位・潮流の取扱い

v0.1では**未取得**。すべての場の `tide` は `not_integrated`、高さ・潮流方向は `null`。

次の段階で、気象庁の天文潮位表・実測潮位と場公式の潮見表を確認する。場ごとに検潮所の対応、水路の接続、測定時刻、データ基準面（潮位の0cmの基準）を検証するまで連携しない。**潮位の増減から潮流の速度や向きを推測で生成しない**。

- 気象庁： https://www.data.jma.go.jp/kaiyou/db/tide/suisan/index.php
- BOATRACE水面解説： https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_01_05_01.html

## 実行

Python 3.11、外部Python依存パッケージ不要。

```bash
python -m unittest discover -s weather_lab/tests -p 'test_*.py' -v
python -m weather_lab.monitor
```

通常の出力は `weather_lab/data/latest.json` と、公開CSVが成功した日に限り `weather_lab/data/YYYY-MM-DD.json`。本番CIでは一時ディレクトリに出力し、**独立データブランチだけ**に記録する。HTTPエラー時は `latest.json` に障害を残し、日別の最後の成功記録を消さない。

ローカル・CIのオフラインテストでは `--fixture` と `--now-iso` を指定できる。実ネットワーク取得時は現在のJST日付から変更できない。

## BOAT LAB向けインターフェース（まだ接続しない）

`weather-lab-data` ブランチに最初の成功・失敗監視が記録されると、読み取り用JSONを取得できる。

```
https://raw.githubusercontent.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/weather-lab-data/weather_lab/data/latest.json
```

`schema = weather_lab.water_surface_monitor.v1`、`collected_at_utc`、`provider.fetch_status`、`venues[24]`、`races[]`を持つ。

**単にリンクが存在するだけでは正式予想に使わない。** 将来のBOAT LAB連携には、6艇展示と同様に締切前取得・測定の鮮度・時刻の証明・バックテストと前向き比較が必要。

## 優先する次工程

1. 全24場について開催日にデータが揃うか日別監査（未開催は母数から除外）。
2. 収集失敗率、観測値の古さ、提供元更新間隔、GitHub Actionsの遅延を計測。
3. 風向コード変換とレースコース方位の一次資料照合。
4. 潮位は鳴門・徳山・宮島などの水理的影響場から観測地点を検証。
5. BOAT LABとは別に、条件付き展開影響の独立シャドー分析・前向き検証を開始。


## 専用スマホWebアプリ（PWA）

WEATHER LAB v0.2では、既存のBOAT LAB公開サイト内に**別のホーム画面アプリとしてインストールできるPWA**を追加。予想モデル・正式買い目へのアクセスや書き込みは不要。

公開ページ（GitHub Pagesのデプロイ成功後）：

```
https://cigusc-qydga1-sivwix.github.io/autonomous-boat-ai/weather/
```

アプリのソースは `app/weather/index.html`, `weather.css`, `weather.js`, `manifest.webmanifest`, `service-worker.js`, `icon.svg`。GitHub Pagesは既存の `app/` 公開処理を利用するが、PWAのスコープ・キャッシュ・独立データの読み込み元は `/weather/` 専用。

### 表示機能

- 全国24場の取得状況をカードで表示。江戸川も監視するが予想対象外。
- 実データがある場・新鮮・要注意・未取得フィルター、レース場検索。
- 1〜12Rの風速、波高、風向の**生コード**、気温・水温、観測時刻、元データ取得時刻。
- 観測から20分、元データ取得から15分超で、**閲覧時刻を基準に再判定**する。保存当時「新鮮」だった値も時間経過後は「古い」と表示。
- 潮位/潮流は未取得と表示。風向コードは向かい風・追い風に勝手に変換しない。
- 60秒ごとに保存済みJSONを再取得。元の収集ジョブは5分間隔の**ベストエフォート**であり、アプリ側の更新操作が新たな気象観測を強制するわけではない。
- 通知・実投票なし。

iPhoneのSafariで開き、共有メニューから**「ホーム画面に追加」**すると、WEATHER LABをBOAT LABとは別のアイコン・別画面として開ける。WebアプリはネイティブApp Store配信ではない。

保存データは `weather-lab-data` ブランチの `weather_lab/data/latest.json` をHTTPSで**読み取り専用**取得。通信に失敗した場合は成功を偽装せず警告を出す。静的画面はオフラインキャッシュ可能だが、外部の気象JSONはキャッシュしない。

UIテスト：
```bash
node app/tests/weather-lab-pwa.test.js
```

UI専用のGitHub Actions `WEATHER LAB app smoke tests` で、BOAT LABの巨大な日別予想台帳を展開せずに検証する。

## 2026-11-06からの前向き気象エビデンス固定

`forward_freeze.py` を監視ジョブに追加し、取得できたレース別気象のうち**監視ジョブ自体の取得完了時刻が締切3分前より前**のものだけ、独立データブランチの `weather_lab/data/forward/YYYY-MM-DD.json` に初回固定する。過去の予想SHA・買い目・結果は変更しない。気象記録は予想ではなく、2026-11-06以降に同一Rの比較に使う独立した事前証拠。sourceの取得時刻と監視ジョブ取得時刻を区別し、後から取り寄せた情報で発走前取得を装わない。風向生コードと潮流未接続は継続。

## 広域気象の独立取得（11月6日開始）

展示公開より前に24場周辺の風・気温・降水の予報を取得する。
Open-Meteo JMA APIは気象庁MSM/GSMモデルの第三者配信で、アメダス実測ではない。
モデル予報の有効時刻と取得時刻を別々に保存し、場内の風・波を上書きしない。
保存場所：weather_lab/data/regional/latest.json（独立データブランチ）。
収集頻度は30分ごと、24時間。非商用・出典表示を守る。
WeathernewsのWxTech APIには契約時のキーが必要で、現時点は未接続。
正式予想・買い目・結果は変更せず、あくまでも補正研究に利用する。
