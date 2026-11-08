# BOAT LAB 正式v2.3：1着→2着条件付き分散と前日比検証

適用開始ゲート：**2026-11-09 00:00 JST**（2026-11-08 15:00 UTC）以降に発走前生成される新規スナップショット。適用の実際の開始はPRのmain統合・自動予想の実行・公開確認後。古いv2.2の固定SHA・買い目・結果は改変しない。

## ユーザー承認の変更
- 正式モデルID：`four-factor-v2.3-conditional-second-primary-untrained`。既存v2.2の全120組・選手・実進入・ST・場別・引き波条件を同一参照元とし、買い目の選択段階に1着→2着ペア分散を追加。
- **採用制限は緩めない。** v2.2の`justified_selection`が選んだ採用数は維持し、先頭4点は保護。ペア分散で差し替えるのは重複した1着→2着の組み合わせのうち、元のチケットと同等のモデル根拠・採用基準を満たし、候補相対スコアが差替前の75%以上のものに限る。
- もともとの各レースの入力・補正・根拠・買い目・元SHAは発走前に固定。結果・払戻・事後STは正式予想の特徴量に入れない。
- 仮想5万円、1000円単位。根拠区分別の最大8/12/24点は維持。自動BUYへの強制昇格なし。無料のWATCH研究であり実投票機能は持たない。
- 追加候補が根拠を満たさなければv2.2の選択結果と同じ買い目を維持し、`NO_ELIGIBLE_SWAP`として保存。必ず差し替わる・回収改善するとは主張しない。

## 同一レース比較と前日比
- 正式v2.3は同じレース・同じ時点のv2.2買い目を`interaction_primary.same_race_v22_control_bets`に保存する。ここは検証専用で、正式収支に加算しない。
- 公式結果と照合する`app/data/live/audit/YYYY-MM-DD.json`の`by_ticket_status.formal`だけから、前日比（的中率、1/2着一致率、回収率、頭/2着/3着抜け、仮想収益）を計算する。
- 独立ワークフロー`.github/workflows/boat-lab-daily-formal-compare.yml`を日本時間07:00に実行し、前日と前々日の完了済みの暦日を比較し、結果をGitHub Actionsの14日ではなく**30日間**のArtifactに保存。未確定レースを自動負けとしない。スケジュールの遅延・不実行やその日の公式結果の更新遅延はあり得る。
- 前日比は開催場・相手関係・レース構成が異なるため因果比較ではない。精度向上の判定には同一レースv2.2対照と100R以上の前向き照合も併用する。

## 独立研究との関係
PR #215の従来の`scripts/freeze_second_place_trials.js`と`audit_second_place_trials.js`は元のSHADOWモデル研究として残す。これらは正式v2.3と混同せず、過去の対照データを上書きしない。正式v2.3から過去のレースへ遡って試験予想を作ることはない。

## 安全確認
- `python -m pytest -q tests/test_conditional_second_primary.py tests/test_compare_daily_formal.py`
- `node app/tests/primary-evaluation-alignment.test.js`
- 既存の全Python / Node CIと公開デプロイ確認が必要。CI成功は的中・収益の改善証明ではない。
