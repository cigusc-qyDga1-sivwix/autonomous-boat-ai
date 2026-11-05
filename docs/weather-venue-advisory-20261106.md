# BOAT LAB 気象注意条件 v0.1（2026-11-06、研究シャドー）

## 位置付け
- **2026-11-05 の発走前固定予想、買い目、SHA、仮想収支は一切変更しない。** 本PRは `weather_lab` の読み取り専用観測に場別研究用の注意信号を付与するのみ。
- 締切前の実測（水面気象）と近隣 Open-Meteo 格子予報を混同しない。レース別観測時刻を確認。20分/15分はモニターの暫定的鮮度閾値であり、正式化基準ではない。
- 風速5m/s・8m/s、波高5cm・10cmは**研究用の共通監視目安**。場別勝率・着順の係数やBUY条件に変換しない。場別公式例：津は約5m、尼崎は6m以上を解説。
- 気象CSVの**風向数値生コードは方向へ変換しない**。風向きの真方位/場のスタート方向を正式に検証するまで追い風／向かい風判定不可。
- 潮位と潮流は未取得。検潮所・時差・水門運用を対応づけるまで値を生成しない。特に**常滑は潮位を水門で制御、下関は2017年防波堤改修で外海の波が入りにくい**ため、近隣の海上潮位を機械的に艇へ反映しない。
- 後から観測データを取得して過去の正式予想へ挿入しない。江戸川は情報監視のみで正式予想対象外。

## 全国24場の優先監視条件（江戸川のみ正式予想除外）
| コード | 場 | 公式説明を踏まえた注目条件 | 潮の観測検討 | 公式根拠 |
|---|---|---|---|---|
| 01 | 桐生 | 冬春の赤城おろし／強風と水面荒れ | 必要性未立証 | [水面特性](https://www.kiryu-kyotei.com/modules/datafile/?page=index_suimen) |
| 02 | 戸田 | 狭い1マーク・風によるスタート／旋回の乱れ | 必要性未立証 | [水面特性](https://www.boatrace-toda.jp/data/suimen_guide.html) |
| 03 | 江戸川 | 河川の流れ・潮・風（取得監視のみ、正式予想対象外） | 要確認 | [水面特性](https://www.boatrace.jp/owpc/pc/site/place/stadium/br03/) |
| 04 | 平和島 | 潮位差・冬の向かい風・2マークの道中逆転 | 要確認 | [水面特性](https://www.heiwajima.gr.jp/01suimen/01suimen.htm) |
| 05 | 多摩川 | 比較的静穏でも突風・風向変化は当日観測で確認 | 必要性未立証 | [水面特性](https://www.boatrace.jp/owpc/pc/site/place/stadium/br05/) |
| 06 | 浜名湖 | 広い水面・冬の追い風／夏の向かい風・水位変化 | 要確認 | [水面特性](https://www.boatrace-hamanako.jp/sp/index.php?page=datafile-suimen) |
| 07 | 蒲郡 | 普段は静穏、例外的な風・波と2マーク逆転 | 必要性未立証 | [水面特性](https://www.gamagori-kyotei.com/sp/01data/01data.htm) |
| 08 | 常滑 | 水位は自動制御。外海の潮位を補正に直結させない | 直結禁止 | [水面特性](https://www.boatrace-tokoname.jp/modules/datafile/?page=index_suimen) |
| 09 | 津 | 強風で急に荒れる。公式が風速約5mを注意目安と説明 | 必要性未立証 | [水面特性](https://www.boatrace-tsu.com/modules/datafile/?page=index_suimen) |
| 10 | 三国 | 冬の北風と追い風、1マーク流れからの差し・2マーク引き波 | 必要性未立証 | [水面特性](https://www.boatrace-mikuni.jp/sp/index.php?page=datafile-suimen) |
| 11 | びわこ | 春夏の沖からの風・湖面の波・標高 | 必要性未立証 | [水面特性](https://www.boatrace.jp/owpc/pc/site/place/stadium/br11/) |
| 12 | 住之江 | 護岸からの反射波と冬の2マーク付近のビル風 | 必要性未立証 | [水面特性](https://www.suminoe.gr.jp/asp/suminoe/sp/suimen/suimen.asp) |
| 13 | 尼崎 | 通常は静水面。公式は6m以上の風と波立ちを注意 | 必要性未立証 | [水面特性](https://www.boatrace-amagasaki.jp/sp/index.php?page=datafile-suimen) |
| 14 | 鳴門 | 水面の狭まり・干満差と攻め艇のターン | 要確認 | [水面特性](https://n14.jp/modules/datafile/?page=index_suimen) |
| 15 | 丸亀 | 冬の向かい風・潮の出入り・満潮時2マークの荒れ | 要確認 | [水面特性](https://www.marugameboat.jp/01suimen/01suimen.htm) |
| 16 | 児島 | 満潮時のうねり、満潮と追い風の複合条件 | 要確認 | [水面特性](https://www.kojimaboat.jp/01suimen/01suimen.htm) |
| 17 | 宮島 | 大きな干満差・満潮時のうねり・潮向 | 要確認 | [水面特性](https://www.boatrace-miyajima.com/surface.html) |
| 18 | 徳山 | 上げ潮と風の重なり・2マーク引き波 | 要確認 | [水面特性](https://www.boatrace-tokuyama.jp/sp/index.php?page=datafile-suimen) |
| 19 | 下関 | 2017年の堤防改修後は外海の波が入りにくい。潮位からの一律補正禁止 | 直結禁止 | [水面特性](https://www.boatrace-shimonoseki.jp/sp/index.php?page=datafile-suimen) |
| 20 | 若松 | 2マーク側からの潮の出入り・満潮時1マーク潮だまり | 要確認 | [水面特性](https://www.wmb.jp/modules/datafile/?page=index_suimen) |
| 21 | 芦屋 | 1マーク裏の葦による消波。強風時は現地波高を確認 | 必要性未立証 | [水面特性](https://www.boatrace.jp/owpc/pc/site/place/stadium/br21/) |
| 22 | 福岡 | 河口近くの1マーク、満潮時の難水面とセンター攻め | 要確認 | [水面特性](https://www.boatrace.jp/owpc/pc/site/place/stadium/br22/) |
| 23 | 唐津 | 朝夕の向かい風・追い風切替、ピット位置変更後の進入 | 必要性未立証 | [水面特性](https://www.boatrace-karatsu.jp/modules/datafile/?page=index_suimen) |
| 24 | 大村 | 時間帯による風向変化、満潮時2マークを監視 | 要確認 | [水面特性](https://omurakyotei.jp/suimen/) |

## 本日11/6からの前向き試験
1. 11月6日（金）の公式開催予定11場のうち、江戸川を除く10場を対象。桐生・戸田・多摩川・常滑・三国・びわこ・住之江・鳴門・宮島・福岡・唐津の開催を確認（このうち江戸川を除外、開催数は確認時の公式日程に従う）。同じ開催・R・締切前時刻の正式予想はそのまま固定し、気象証拠だけ独立保存。
2. 各Rの気象観測時刻・取得時刻・予想凍結SHA・出走者6艇の展示情報・予報/実測種別・生風向コード・風速・波高・気温・水温を保存し、欠損と遅延を明示。
3. 研究用注意信号が出たレースについて、1着捕捉・条件付き2着・3着抜け・的中・返還込み回収率を、気象有無・場別・風速帯ごとに検証。ただし同一場の少数Rで効果断定しない。
4. 風向正規化（データ提供元のコード定義＋場内コース軸の公式地図で照合）と潮位マッピングが完了するまで、勝ち筋を変える気象倍率は**OFF**。実測・予報を混ぜず、環境×展開の交互作用は先に独立学習。
5. 全23場を同じ係数で補正せず、最終的な正式版への取り込みは発走前の前向き同点数比較で効果が認められた条件だけ。

## 確認条件
- `python -m unittest discover -s weather_lab/tests -p 'test_*.py' -v`
- `node app/tests/weather-lab-pwa.test.js`
- モデル・台帳・結果・収支・正式買い目・通知設定への変更はゼロ。

## 11月6日開始の追加運用（発走前気象エビデンス）

- `weather_lab/forward_freeze.py` は実際にWEATHER LABが取得した `collected_at_utc` が各Rの**締切3分前以前**かを再確認してから、風・波・生風向コード・温度・観測時刻を最初の1件だけ固定する。
- 発走後に初めて収集された観測は**正式な発走前気象証拠にならない**。同じレースの取得をやり直しても最初の証拠を上書きしない。
- 証拠の保存先は独立 `weather-lab-data` ブランチの `weather_lab/data/forward/YYYY-MM-DD.json`。正式買い目、SHA、収支、モデル出力には変更を加えない。
- 風向きコードの方角への変換・潮流推定・気象による勝率変更はまだ未実装。気象による精度上昇は検証前であり、表現しない。
- 開催予定と出走中止・荒天中止を区別。予定レース数と実施レース数は一致するとは限らない。
- https://boatrace.jp/owsp/sp/race/monthlyschedule
