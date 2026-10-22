# Autonomous Boat AI

競艇の予測・事前固定・結果照合を行う初期実装。実データ取得と自動学習は未実装。予測は研究用であり精度は未検証です。

## Test

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```


## BOAT LAB v1.0 — iPhone対応予想アプリ

[アプリのソースと使い方](./app/README.md) を追加しました。鳴門・徳山の2026-10-22発走前固定24Rについて、競輪形式の買い目・仮想5万円配分・結果手入力・成績分析ができます。

GitHub Pagesの公開はリポジトリ設定で **Settings → Pages → Source: GitHub Actions** を有効にする必要があります。公開が有効になってから `.github/workflows/boat-lab-pages.yml` でデプロイできます。

展示動画解析・展示実測値・オッズ・公式結果の自動連携は未実装です。アプリの収支は仮想・手入力です。
