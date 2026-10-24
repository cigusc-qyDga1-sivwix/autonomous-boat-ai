# BOAT LAB — 六艇の相互作用・着順連動 v0.6（独立研究・未校正）

更新: 2026-10-24 / 本実装は統計学習済みモデルではなく、検証可能な**機序仮説**とデータ収集の土台。

## 一次資料（レース観察・ロジックの根拠）
- BOATRACE公式「展開予想とは？」https://www.boatrace.jp/owsp/sp/extra/enjoy/guide/level2/l2_01_08_01.html
- BOATRACE公式「スタート展示／進入」https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_01_02_03.html
- BOATRACE公式「まくり」https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_02_02_02.html
- BOATRACE公式「差し」https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_02_02_04.html
- BOATRACE公式「まくり差し」https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_02_02_03.html
- BOATRACE公式「風向きと攻め」https://www.boatrace.jp/owsp/sp/extra/enjoy/guide/level2/l2_01_05_01.html
- BOATRACE児島「初心者ガイド（道中の2・3着争い）」https://www.kojimaboat.jp/beginner_guide.html

## 問題：艇を独立に評価すると着順が破綻する

予想対象は艇ごとの単独「強さ」だけでなく、次の条件付き状態遷移。

1. **ピット〜進入**：実コース、前付け、スロー／ダッシュ、深イン。実展示進入が怪しいレースはゲートを優先。
2. **スタート〜1M手前**：平均ST・展示ST・行き足の相対差。展示Fは高速スタート扱いしない。
3. **1M入り口**：最短先マイ（1C）／差し（2Cほか）／外からまくり・まくり差し（3C〜）。仕掛けは **成功／未成功** に分岐。
4. **1M周回**：外の仕掛けが内を押さえ、内艇が伸びを落とす／防御して残る。実際の引き波横断はまだ計測できていない。
5. **1M出口〜バック**：攻め艇の直外の艇がついてくるか、内艇の差し残りがあるか。頭が同じでも2着集合が異なる。
6. **2M以降〜ゴール**：3着の残存、抜きによる逆転、事故・失格は一様に処理せず。現在のv0.6は2Mの順位遷移を実測・学習していない。

## v0.6 実装（app/tactical-1m.js）

- 6コースそれぞれが頭の場合の **有向関係グラフ** を作成。
- 始動力／旋回力の相対差による攻め圧 `pressure`、内側各艇への `risk`、直外の追走準備 `follower_readiness` を計算。
- 攻め圧が弱ければ連動ボーナスを発生させない。内側艇は一律全消しにしない。
- `P(2着コース|頭コース・攻め圧)` に相当する**相対重み**を算出、さらに `P(3着|頭・2着の組み合わせ)` を別に再計算する。
- 3連単120通りを内部評価し、従来ルールの4〜12点／仮想50,000円に限る。実測確率、物理シミュレーション、校正済み予測ではない。
- 正式v1.0、独立旧モデルv0.1〜v0.5、SHA固定買い目は変更しない。
- UIは個別レース詳細の v0.6 折りたたみ表。保存済みの正式収支に混ぜない。

## 事後学習データ（予想入力に絶対混ぜない）

`python -m scripts.research_coupling_patterns` は過去の研究用BoatraceCSV出力で、着順・勝者決まり手・コースの **条件付き着順頻度** を数える。重要：このデータだけでは「他艇の1M攻め方」「引き波を横断した瞬間」は観測できない。

ラベル付けに必要：
`entry_course_confirmed, start_lead_per_boat, 1m_attack_course, attack_type, inner_boat_displaced, gap_opened, follower_course, backstretch_order, 2m_order, final_order, video_review_source`

動画から **時刻・6艇座標・ターン開始・交差・受波** を確認できる合法かつ再現性のある手段が揃うまでは、推測を「観測」と記録しない。事後の着順だけから戦法を逆算しない。

## 公正な前向き検証

- `scripts/freeze_coupling_trials.js` が**同一時刻・同一事前データ**で v0.5 対 v0.6 を締切3分超前に別SHAで固定。
- 最大45分より古い入力は除外。結果・配当・後日展示の情報は入力禁止。
- `app/data/experiments/coupling-YYYY-MM-DD.json` と `coupling-status-latest.json` に記録。日を跨いだ後追い作成・既存行上書きは禁止。
- 比較は「頭一致」「1/2着連動一致」「3着紐抜け」「3連単的中」「仮想回収率」に加え、**外4Cのまくり後の5C追走／内1C残存／3C攻め時の2C残り**を別々に検証。
- 条件が多いと小標本になりやすい。各条件は件数と欠損を必ず表示し、少数例で勝率改良と断定しない。
- 動画の6艇行動ラベル＋十分な独立検証が揃えば、将来の確率校正／条件付きモデル学習に進める。

**重大な制約**：v0.6 の有向関係は測定された実船位置・水面の流体計算ではない。アニメーションは予想仮説の模式表現であり、レースの実映像とは異なる。
