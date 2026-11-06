# G1選手競争力・1着集中評価シャドー v0.1（2026-11-07）

## 結論

**G1で苦戦した**という観測と、**G1だから苦戦した**という因果推論は別。
住之江の11/5・11/6の成績が悪かったことだけを理由に、
場や時刻でメインの係数を変更しない。すべて前向きA/B試験。

## 事実：外部出走表にグレードがある

出走表元は BOATRACE **非公式** Open API v1。
- レース情報の \`programs.stadiums.{stadium}.races.{race}.grade_number\` は発走前データ。
- 公開コード表の値は **1=SG、2=G1、3=G2、4=G3、5=一般、6=PG1**。
  数値は**序列ではなくカテゴリ**。大きい方が格上などとみなさない。
- 取得元の \`grade_number_source\`（G1b等）も照合し、食い違えば
  \`CONFLICT\`、欠損なら \`UNKNOWN\` で試験を止める。
- official-grade として独立照合済みと偽らない。
- 仕様: https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/schema.md
- コード表: https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/codes.md

## 仮説：G1でも出走6選手が近接しているときだけ過集中を緩める

\`scripts/grade_competition_shadow.py\`:
1. G1 (\`grade_number==2\`)、発走前の6艇進入・展示が全て検証済み、
   全国勝率6人全員が明示・5.5以上・最大と最小の差が2.0以内、
   かつ本番の最大1着相対シェアが30%以上の場合のみ発動する。
2. 現行v2.2から**同一120着順の相対評価**を受け取り、
   本命と他の1着候補の分布を弱く平準化する。最大補正は12%。
3. この係数は実験用で未校正。全国勝率の情報は本番v2.2にも存在し
   **二重計上・過適用リスク**がある。結果が悪ければ不採用。
4. 1号艇を無条件に低くせず、最も頭シェアが高い艇に対して相対化する。
   G1と会場の補正を混同しない。

## 実装範囲

- \`scripts/autonomous_daily.py\` に \`grade_context\` を発走前固定。
- G1のみ \`grade_competition_shadow\` という**別の事前予想候補**
  （\`model_role=shadow_validation\`、\`not_formal=true\`）を作る。
- 本番\`bets\`/配分/ \`model_version\` は変更しない。
- 過去の11/5・6のSHA・予想・結果を遡って書き換えない。
- エビデンスが揃っていないレースは「不適用」と記録。弱いデータから
  外枠を強引に1着へ引き上げない。
- 住之江・鳴門はG1比較の最初の調査対象。
  PG1・SG・G2・G3・一般は今のところ明示的な未介入対照群。

## 試験

\`\`\`bash
python -m unittest discover -s tests -p 'test_grade_competition*.py'
python -m scripts.audit_grade_competition_shadow \
  --ledger app/data/live/2026-11-07.json \
  --out /tmp/g1-parity-audit-2026-11-07.json
\`\`\`

\`scripts/audit_grade_competition_shadow.py\` は同一レース・同時刻・
同一点数・仮想5万円・公式払戻済み・SHA固定済みだけを集計。
時間帯、場別の的中率・回収率・1着、2着、3着抜けを検証する。
未収集／欠損／中止／照合紛争は標本から除外する。

## 今後必要な検証

1. まず本番の成績を**開催グレード別**（一般/G3/G2/G1/PG1/SG）
   と、同じ場・R・朝/昼/夜で整理する。2日だけの原因断定は禁止。
2. 少なくとも100R程度の前向き同条件比較を蓄積し、G1内で
   シャドーの頭抜け・1/2/3着・回収率を正式v2.2と対比。
3. より重要な将来課題は **同格相手との成績** の履歴を正式に整備し、
   全国勝率の狭さという代理指標より説明可能な条件に改良すること。
4. 新モデルの効果未確認なら正式昇格しない。正式買い目を変える
   場合は別の評価とPRで行い、過去的中実績は絶対に再計上しない。
