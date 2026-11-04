# BOAT LAB — 展開予想の資料監査と着順連動研究（2026-11-04）

## 根拠資料（公式・分析・実データ仕様）

1. [BOATRACE公式：展開予想とは](https://www.boatrace.jp/owsp/sp/extra/enjoy/guide/level2/l2_01_08_01.html) — ピットアウト→進入→スタート→1M攻防。1Mの進路選択が重要。
2. [公式：スタート展示／進入](https://www.boatrace.jp/owsp/sp/extra/enjoy/guide/level2/l2_01_02_03.html) — 前付け・深イン・カドによる助走差。枠と実際の進入コースを混同しない。
3. [公式：差し](https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_02_02_04.html)、[まくり](https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_02_02_02.html)、[まくり差し](https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_02_02_03.html) — 内艇の進路、引き波、外艇の攻撃と差し場の相互作用。
4. [公式：風向と戦法](https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_01_05_01.html) — 追い風と向かい風の1Mへの影響。ただし場別の実測風向・風速がないと個別補正を断定できない。
5. [中日スポーツ：連動する不確実性](https://static.chunichi.co.jp/chuspo/pages/feature/kyotei/statistical_structure_of_uncertainties_in_boat_races.html) — 2024年の統計モデルで2C–3Cの不確実性相関は -0.340、3C–5Cは -0.274。これは**モデルの推定値**であり現在の全場・全選手に移植する係数ではない。
6. [BoatraceCSV：スリット隊形検証](https://boatracecsv.github.io/docs/design/slit_tenkai.html) — 41,776レースの事後実測STの説明力は高いが、展示STの本番ST相関は約0.05。全国平均STとの差を区別する。**当該レース実測STを事前予測に入力するのはリーク**。
7. [BoatraceCSV：確率的スリットの実験結果](https://boatracecsv.github.io/docs/design/slit_sim_plan.html) — 複数隊形の確率予測が Phase 0 の基準を下回り、最終的にST範囲表示のみ採用。確率的隊形だからといって精度向上は自明でない。
8. [BoatraceCSV：結果CSV仕様](https://boatracecsv.github.io/docs/data/results.html) — 実進入・実測ST・1〜6着・決まり手。解析用の着順連動ラベルを作れるが、1Mの航跡や牽制回数は確定できない。

## コードの追加

- `scripts/conditional_st_coupling_study.py`: BoatraceCSV形式の結果CSV（事前取得の許諾済みデータ）から、**23場・実進入コース別・実測スリット隊形別・勝者条件付き2/3着**の観測表を構築。江戸川(03)は除外。
- `conditional_followups_by_winner_course`: 例えば「3コース勝利のとき、2コースは2着か3着に残ったか」を分母付きで計測。
- `adjacent_course_conditional_finish`: 外側コースが1着だったレースとそれ以外のレースで、内隣コースが2/3着に入る割合を比較（各条件20件未満なら数値を出さない）。
- 実測STの0.04秒幅は研究上の**仮閾値**。スタート隊形の観測分類にのみ使用し、事前の勝率係数として使わない。
- 新しい`interaction_scenarios.evaluate`の `conditional_places_by_head` は従来の**同一120組の相対スコアから算出した、1着艇ごとの2・3着候補**。未校正であり新たな優位性の証明ではない。正式スナップショットに診断用メタデータを保存するが、買い目順位・点数・仮想5万円は変更しない。

## 次の改善候補（未検証／未採用）

- 3Cがまくった時2Cは残存するか、5Cが外攻めした時3Cは残存するか、を**場別・コース別・スタート隊形別**で学習する。
- 「攻撃成功」／「攻撃不発」／「差し場が開く」／「イン残存」／「イン3着外」は各シナリオの関係として同時に評価する。勝者だけに一律加点し、2着3着に同じ条件を適用するのは避ける。
- 実測STで分類したレースから学ぶ場合、ターゲットより前に完了したレースのみ使用。予想側は平均ST・展示・進入・モーター・事前場別気象だけを使う。
- 評価は前向き固定SHA・同一レース同一点数5万円の対照・2/3着抜け率・コース別条件付き校正、200R程度で実施。係数が良く見える過去事例のみの採用禁止。
- 映像追跡で1Mの物理的な通過位置が検証できるまで、**牽制を実測したとは呼ばない**。

## 実行例
```sh
python scripts/conditional_st_coupling_study.py \
  --input /path/to/authorized_results_20261103.csv \
  --event-date 2026-11-03 \
  --before-date 2026-11-04 \
  --out /tmp/conditional_st_20261103.json
python -m pytest -q tests/test_conditional_st_coupling_study.py tests/test_interaction_scenarios.py
```

**状態**：研究と診断コードは追加済み。実データの自動収集、統計の実数値、正式予想係数の更新、精度向上は未検証。既存の正式買い目・収支・過去保存データは変更しない。
