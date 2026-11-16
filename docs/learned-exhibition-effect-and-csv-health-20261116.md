# BOAT LAB 同一モデル・同時点展示効果比較（2026-11-16）

## 発見した接続不備

2026-11-16の本番収集実績では、照合済み正式展示85Rに対し、
オリジナル展示（まわり足・直線・一周）の6艇完備は各0R。
BoatraceCSV importer の4つのプレビュー入力（stt/tkz/sui/original）は
`app/data/exhibition/status-latest.json` でいずれも0行だった。

学習済み正式v1は実進入・平均ST・展示タイム・展示ST等を入力する一方、
`original_exhibition` を学習済み重みに渡していない。
通常展示6艇が確認されたことと、全詳細展示が正式予想に効いたことを混同しない。

また同日の展示前/後85組はモデルIDまたはモデルSHAが異なるため、
履歴の買い目差を展示の純効果と断定してはならない。

## 実装（正式買い目は変更しない）

- `scripts/learned_exhibition_ablation.py`: 同一の学習モデルSHA・6艇・平均ST・進入・
  気象・点数・仮想5万円を固定し、`exhibition_time` と `exhibition_st` を除く条件だけを
  前向きで再計算した **研究用シャドー** を、保存時6艇照合成功後に生成。
- 元の正式買い目・分類・SHA・履歴を変更しない。条件不整合時は保存しない。
- `forecast-sync-latest.json` の `exhibition_similarity_audit` に
  `same_time_learned_ablation_frozen`／変更件数／最上位頭変更件数を保存。
  旧来の異モデル・異SHA baseline は比較対象に入れない。
- `forecast_audit.py` で公式確認済み・同時凍結・SHA一致のみ結果照合。
  回収率・的中率は同点数同額の対照比較であり、過去の事後再構成ではない。
- `scripts/ingest_boatracecsv_exhibition.py` はrawとPagesそれぞれの
  HTTP/ネットワーク取得失敗を `status-latest.json.fetch_health` に保存。
  取得できない時は OpenAPI の通常展示を従来どおり利用し、未取得の詳細値を捏造しない。

## 次に必要な根本改良

1. `fetch_health` で各ソースのHTTP 404・遅延・空配信・通信エラーを特定。
2. 正式反映する詳細展示の収集経路を確立し、6艇の実測日時と測定単位を検証。
   場別の未測定項目・桐生半周・住之江/尼崎/徳山の2項目を区別する。
3. 詳細展示の特徴量・場別重みを追加する場合は、既存 `conditional-choice-v1`
   とは別スキーマ／別モデル／別SHAにして学習と前向き検証を実施する。
4. 独立の公式照合済み共通100R以上で、頭抜け・2着抜け・3着抜け、
   的中率と回収率の改善を確認するまで正式昇格しない。
