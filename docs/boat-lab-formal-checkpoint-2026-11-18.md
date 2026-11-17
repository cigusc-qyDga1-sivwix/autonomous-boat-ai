# BOAT LAB 2026-11-18 正式予想・朝運転チェックポイント

**保存日**: 2026-11-18 JST
**用途**: 現行正式ロジックと運転設定を再現可能な基準点として記録する。過去レースの再生成・過去台帳の書き換えを許可しない。

## 最新版の正式予想（基準状態）

- GitHub repository: `cigusc-qyDga1-sivwix/autonomous-boat-ai`
- 対象 branch: `main`
- 直近の正式ロジック反映: PR #293 / merge commit `f5c2f7b6dcff675cf234b8a813beb12342b6bf69`
- 学習済み正式一次モデル: `scripts/learned_formal.py`, model version `four-factor-learned-v1-conditional-choice-trained`
- 2026-11-18 0時台の学習モデル証拠: `app/data/statistical/latest-model.json`, SHA256 `0fdc5cacba60dd9af6e1d1cb562b7a868644e99922662298ac3cd62c7572dc96`, trained through 2026-11-16, 3,700R。**毎日の新しいモデルに追従する設計を維持**し、このSHAを将来の固定モデルとして強制しない。
- 23場オリジナル展示正式補正: `scripts/original_venue_formal_v1.py` + `config/original-venue-v1-profiles.json`。学習元594R。江戸川はこの補正の適用対象外。
- 新しい3・4コース攻防補正: `scripts/corner_attack_formal_v1.py`, `corner-guard-forward-v0.1`。進入コース3/4/5と、通常展示ST・展示タイム・選手平均STの**発走前照合済み値**のみで作用。最大+0.04 logの4コース1着、条件を満たす場合だけ最大+0.025 logの4→5条件付き2着。暫定ヒューリスティック、未校正・効果未証明。
- 独自展示v1が揃えば、上記新補正と合成し二重補正しない。取得・6艇照合・締切前固定・別SHA必須。
- 既存の学習モデル、固定済み予想、公式結果、仮想収支、BUY研究シャドーの区分を過去に遡って書き換えない。

## 朝の自動運転

- ワークフロー: `.github/workflows/boat-lab-auto.yml` / **BOAT LAB nationwide auto forecasts**
- cron (UTC): `2-59/5 21-23 * * *` と `2-59/5 0-14 * * *`
- 想定JST: **06:02から約5分間隔で23:57まで**。GitHub Actionsは遅延・スキップする可能性があるため、正確な分単位の動作を保証しない。
- Actions は現在の `main` 上で取得→締切前固定→GitHub台帳書き込み→アプリ用JSON同期を実行する。追加された `corner_attack_formal_v1.py` とテストファイルも、変更時の自動起動対象に含める。
- 予想処理前に `test_corner_attack_formal_v1.py` を毎回実行する。落ちれば正式予想公開前に停止し、不具合を隠して予想を更新しない。
- 既存の新規発走前固定済みレースのみを予想・成績として扱い、展示データ不足時は新補正を掛けない。展示未確認を「正式展示反映済み」と表示しない。
- 日中の独自展示補正は締切4〜20分前の取得機会に依存し、取得ゼロの日には新しい買い目変更は発生しない場合がある。

## 検証証拠・これから確認する内容

- PR #293 最終SHA `c34076c5ceae7980ca4ff306ebffe388c5424177` に対する4件のテストが成功。
- mainのコミット `f5c2f7b6dcff675cf234b8a813beb12342b6bf69` に対する自動全国予想ワークフロー成功を確認。
- 2026-11-18 00:52 JSTの `app/data/live/forecast-sync-latest.json`: 予想120R、展示反映0R、独自展示v1正式0R。**開催前であり、朝の実レースへの新補正成功を立証するものではない**。
- 朝の最初の正常実行について `app/data/live/forecast-sync-latest.json` の `event_date`, `captured_at_utc`, `status`, `final_exhibition_verified_races`, `original_exhibition_v1_formal_races` を検証する。
- 以降は各レースの `corner_attack_formal_v1`、予想固定SHA・時刻、旧ロジック対照、公式照合結果から1着抜け・2着抜け・3着抜け、的中率、仮想回収率を追跡。正式予想と研究用シャドーを混ぜない。
