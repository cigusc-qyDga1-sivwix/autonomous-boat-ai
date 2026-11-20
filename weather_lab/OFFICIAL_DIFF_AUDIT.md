# WEATHER LAB: BOATRACE公式直前気象とBOAT LAB OpenAPIの差分監査

研究用・読み取り専用の独立ジョブ。BOATCAST映像のスクレイピングではない。
BOATRACE公式 \`/owpc/pc/race/beforeinfo\` の水面気象パネルから
**風速(m/s)、風向CSSコード(1～17)、波高(cm)** を取得し、
同時実行で取得した Boatrace Open API の \`preview\` と比較する。

## 運用
- Workflow: \`.github/workflows/weather-lab-official-beforeinfo-diff.yml\`
  （JST 06:00～23:59の5分間隔ベストエフォート）
- APIの締切時刻に対して**20分～5分前**のレースだけ比較。公式HTTP取得完了が締切5分前を過ぎたものは比較不可と記録。
- 公式HTMLの \`水面気象情報 HH:MM現在\` を読み取る。20分以内のみ鮮度確認済みとする。
  \`nR時点\` は観測時刻が確定しないので**未確認**。場内気象欄は将来Rでも以前のRの数値を表示し得る。
- 観測時刻の一致は証明できない。API側は提供元での実観測時刻を保証しない。
  一致時 \`VALUES_MATCH_OBSERVATION_TIME_NOT_PAIRED\`、
  差分時 \`DIFFERENCE_POSSIBLE_SOURCE_LAG\`（必ずしも故障ではない）。
- 収集エラー、値の欠落、古い観測、遅延をそれぞれ区別。無風コード17も生値で保持する。
- 公式の風向画像クラス \`is-windN\` と OpenAPI \`wind_direction_number\`
  は同じ番号体系として差分のみ比較。**コース別の有利不利へは自動変換しない**。
- source URL、取得時刻、観測時刻（確認できる時のみ）、気象ブロックSHA、
  締切時刻、差分フィールドを同時保存。
- 独立 \`weather-lab-data\` ブランチ：
  \`weather_lab/data/official_audit/latest.json\` は今回の取得結果、
  \`weather_lab/data/official_audit/YYYY-MM-DD.json\` は追記専用の時系列。
  データと正式予想のSHA、買い目、払戻、学習器は完全に分離。
- GitHub Actions cronの遅延や公式サイトのレイアウト変更は実運用上のリスク。
  5分前の取得成功を保証しない。取得なしの日を「正常」と呼ばない。

## 検証
\`\`\`bash
python -m unittest discover -s weather_lab/tests -p 'test_official_beforeinfo_audit.py' -v
python -m weather_lab.official_beforeinfo_audit --out /tmp/official-weather-diff.json
\`\`\`

予想への昇格前に必要なこと：
(1) 場×R×締切前の一致/差分率、欠損率と遅延率の監査、
(2) 公式の観測値とOpenAPIの提供元観測時刻の照合、
(3) 追い風・向かい風の研究用A/Bとの連携と前向き評価。
**取得できたと確認するまではBOAT LAB正式予想への入力には使わない。**
