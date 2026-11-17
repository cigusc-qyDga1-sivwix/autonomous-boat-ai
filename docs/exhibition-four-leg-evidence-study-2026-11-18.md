# 2026-11-18 BOAT LAB 舟足4軸（行き足・出足・伸び・まわり足）研究

Status: **RESEARCH ONLY。正式モデルと買い目は変更しない。**

## 1. 結論：直接測れるのは「区間タイム」、舟足4軸そのものではない

| 項目 | 利用できる展示情報 | 証拠の強さ | これだけでは言えないこと |
| --- | --- | --- | --- |
| 伸び足 | 通常展示150m、場独自直線の6艇内相対差 | 直線区間の速度代理として比較的強い | 出足と最高速の厳密分離 |
| まわり足 | 独自まわり足区間、一周/半周の補助 | 旋回区間の速さとして比較的強い | 選手のターン技術・引き波を除いた純粋機力 |
| 出足 | まわり足とターン後の独自直線（ある場のみ） | 間接的・推定 | 出口加速度そのもの、独立した秒数 |
| 行き足 | 展示STの状況情報とスタート展示映像 | 数値だけでは不十分 | 展示STが速いだけで行き足良好と断定 |

- **通常展示**は公式の区間速度指標。**福岡**は旋回後から測るため、行き足の成分も含む。
- **独自直線**は場により「伸び寄り」または「旋回後の中間速寄り」。同一意味で一括学習しない。
- **独自まわり足**は旋回操作と旋回後の立ち上がりが混ざりうる。出足の純粋な計測値と誤認しない。

### 一次資料
- BOAT RACE / BOATCAST: https://www.boatrace.jp/owpc/pc/site/news/2025/07/44414/
- BOAT RACE 周回展示の通常展示タイム: https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_01_02_07.html
- BOAT RACE 行き足の定義: https://www.boatrace.jp/owsp/sp/extra/enjoy/guide/level2/l2_01_02_05.html
- BOAT RACE 出足型と伸び型: https://www.boatrace.jp/owpc/pc/extra/enjoy/guide/level2/l2_03_01_04.html
- 平和島の場別資料（直線は出足・行き足の参考）: https://www.heiwajima.gr.jp/tok/20grandprix/data.htm
- 福岡の計測位置と各タイムの過去集計: https://www.boatrace.jp/owpc/pc/extra/race/22_20210323/monthly/kokowomiru_2.html
- 桐生の過去集計（2016年、現在の予測率には流用しない）: https://www.boatrace.jp/owpc/pc/extra/race/01_20160823/monthly/dataroom.html

## 2. 場別の取扱い

- 福岡: 通常展示はターン後の加速も反映。伸び足の純粋なラベルにしない。
- 住之江・尼崎・徳山: 独自直線なしの場別契約。通常展示値を独自直線と偽って二重入力しない。
- 桐生: 半周ラップは一周と別指標。
- 若松: 一周は1周目、独自まわり足/直線は複数周の最良値の可能性。区間値を引き算し出足タイムを捏造しない。
- 蒲郡: 2周展示と短縮1周展示は区別。常滑: 欠測は0秒や最下位に変換しない。
- 1号艇と外艇では引き波・走行ラインが異なる。同じRの6艇内中央値差を記録し、会場をまたぐ秒数比較をしない。
- 現在の仕様表: scripts/original_exhibition_venue_research.py の VENUE_SPECS。江戸川は現時点の独自展示モデルの研究対象外。

## 3. BOAT LAB既存実装との照合（11月18日00:58 JST）

- scripts/boatcast_oriten_smoke.py はBOATCASTの一周/半周、まわり足、直線の6艇実測取得経路を持つ。
- scripts/original_exhibition_venue_research.py は発走前6艇、SHA、場・日付・締切余裕を検証し、各指標の中央値差・順位を作る。
- scripts/original_venue_formal_v1.py は上記の一周/半周・まわり足・直線を場別補正として**条件付き正式導入済み**。
- 一次学習モデルは通常展示タイムと展示STを使用。独自3項目は別の場別正式補正の経路。
- 当日 app/data/live/forecast-sync-latest.json は事前予想120R、展示反映0R、独自展示v1正式0R。展示公開前なのでこれだけで不具合とは断定しない。
- 当日 app/data/exhibition/status-latest.json の旧BoatraceCSVデータ取得はHTTP404。BOATCAST直接取得と混同しない。

## 4. 新規の研究用コード

- scripts/four_leg_exhibition_evidence_research.py の assess(snapshot, capture) は研究用4軸エビデンス分類器。
- 既存の厳格なvenue_features検証と正式予想の同一レース・6艇・選手名・進入を照合する。
- 伸び足とまわり足は元の相対秒数を示す。出足はターン+旋回後の直線の**間接根拠**を示す。行き足は展示STを文脈情報として示し、**映像なしでは定量化不可**と明示。
- **4軸の架空スコアを生成しない。正式買い目・配分・既存学習係数を変更しない。自動学習・スケジュールには未接続。**
- tests/test_four_leg_exhibition_evidence_research.py で、6艇の同一性、時間条件、場別欠測、独自直線不在、通常展示と艇番/進入の区別を検証する。

## 5. 実証してから正式予想へ採用

1. まず同日・同場・同Rの6艇実測件数と取得時刻を継続監査する。
2. BOAT VISION AIのスタート展示で起こし位置→スリットを追跡し、位置・時刻の校正がある場合に限り行き足の加速を推定する。
3. 周回展示で入口→頂点→出口→直線を分け、出足・旋回速度保持を分離。映像未取得の場合は推測に留める。
4. 公式結果を見る前に旧正式vs研究用4軸を独立SHAで前方固定。1着抜け、2着抜け、3着抜け、的中率、仮想回収率を場/進入/グレード別に比較。
5. 独立した前方検証でプラス寄与が再現された項目のみ、正式化を検討する。

**結論：展示から4種類の根拠を整理できるが、数字だけで4軸を独立した機力として精密推定したとは言えない。**

## 2026-11-18: 発走前固定の自動証拠蓄積

- `scripts/four_leg_live_freeze.py`: 全国自動予想で取得したBOATCASTの6艇独自展示を、同じ開催日・場・R・予想固定SHA・測定SHAで結び付け、4軸研究の証拠を上書きせず保存する。新たなネットワークアクセスや結果参照は行わない
- `scripts/autonomous_daily.py`: 予想計算直後・公式結果取得前に実行する。出力は `app/data/exhibition/four-leg/YYYY-MM-DD.json` と `app/data/exhibition/four-leg/status-latest.json`。GitHub Actionsの既存 `git add app/data/exhibition/` で同日中に公開保存する
- `tests/test_four_leg_live_freeze.py`: 予想の保全、6艇一致、予想SHAごとの不変保存、結果からの逆算防止、BOATCAST測定SHA・時刻不一致の拒否を検証
- **正式予想とは別管理**。研究側が失敗しても正式買い目を上書きせず、研究側は `ERROR_RESEARCH_FAIL_CLOSED` と報告する
- データ未公開でオリ展取得0件の場合は正式予想から独自4軸評価を生成しない。朝6時のベースライン起動は展示公開済みを意味しない
- **まだ行き足/出足の独立した物理的計測も、予測精度向上も証明されていない**。次は実レースの前方保存件数と公式着順を分離して照合する
