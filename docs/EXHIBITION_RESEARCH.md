# 展示データの独立収集・研究（2026-10-23）

BOAT LABでは、発走前に固定済みの予想（app/data/live/）と、後から収集した展示実測・結果（app/data/exhibition/）を別々の情報系統として保存する。

## 現時点の実績

10月23日10:35頃のBoatraceCSVソースでは9場21Rの展示情報（126艇分）、参考として確定結果13R・3連単払戻15Rが取得できた。app/data/exhibition/2026-10-23.json に保存。公開データは更新ごとに増えるためこれは途中経過。

## 取得方法

- python scripts/ingest_boatracecsv_exhibition.py でJST当日分をダウンロード。
- 任意の日は python scripts/ingest_boatracecsv_exhibition.py --date 2026-10-23。
- stt（展示ST・進入）、tkz（展示タイム・チルト）、sui（場内気象）、original_exhibition（場別一周・まわり足・直線など）、results/realtime（決まり手・着順）、results/payouts を12桁のレースコードでJOIN。
- 6艇の展示が揃わないレースは無理に補完せず、結果が一時的に消えても取得済みの参考結果は保持する。
- GitHub Actionsの通常定期実行から追加で呼び出す。公開ページの更新遅延はあり得る。
- iPhoneではBOAT LAB → 展示記録で6艇分の実測値と参考結果を閲覧する。

## データ品質・重要な境界

1. 展示タイム最速でも1着とは限らない。展示STの負値は展示フライングで、速い合法スタートと評価しない。
2. 結果と払戻はBoatraceCSV由来の研究用参考値。公式BOATRACE照合済みの結果・正式な仮想収支には昇格させない。
3. 後から取得した展示を発走前に知っていたことにはせず、発走前固定予想（時刻・買い目・ハッシュ）を変更しない。
4. モデル調整・事後再解析には利用可能だが、未知データに対する精度評価とは分ける。
5. BOATERSサイトを自動取得しない。元ソースの利用条件変更や遅延時には収集を停止し、保全済み記録を残す。

出典: https://boatracecsv.github.io/docs/data/previews.html

既存予想ロジックは未変更。リアルタイム予想への接続は、締切前取得の実績を確認してから試験導入する。
