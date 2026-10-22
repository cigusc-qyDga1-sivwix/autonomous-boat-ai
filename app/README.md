# BOAT LAB v1.0 — iPhone対応競艇AI Webアプリ

この `app/` は既存の `boat_ai/` Python予想処理とは独立した静的なPWAです。

## 機能

- 鳴門・徳山 2026-10-22 計24Rの**発走前固定済み**買い目（8点/R、仮想50,000円）
- レース一覧・WATCH/SKIP切り替え・展開シナリオ・配分表
- 周辺地域の時間帯別気象参考値（**場内実測ではありません**）
- 確定3連単と100円当たり配当の**手入力**で的中・仮想払戻を計算
- 場別的中率・回収率、1着候補捕捉、1・2着一致、3着紐抜け
- 結果CSV、バックアップJSON、予想データJSON読み込み、ローカル保存
- iPhoneホーム画面追加、HTTPS接続時のオフライン再訪に対応

## 起動

```bash
cd app
python3 -m http.server 8000
```

`http://localhost:8000/` を開いてください。 `file://` で開くとJSONロードが制限される場合があります。

## GitHub Pages

`Settings > Pages > Build and deployment > Source: GitHub Actions` を有効にすると、`.github/workflows/boat-lab-pages.yml` が公開を実行します。iPhoneでURLを開いた後、Safariの「共有」>「ホーム画面に追加」を選択できます。

## 検証の注意

本版には展示ST・展示タイム、展示動画解析、直前オッズ、公式結果APIの自動取得、通知、投票機能はありません。結果は端末内に**手入力**で保存し、GitHubや他端末とは同期しません。正式BUYは0Rです。ユーザーが追加インポートした予想は、発走前固定の証明がないため別扱いです。

GitHubの発走前保存コミット: `3f112ba657197212b4a12ce0b86de68cb69bc29b`
