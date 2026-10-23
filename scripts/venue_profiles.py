"""Experimental course-context profiles for all 24 Japanese BOAT RACE venues.

Course-1 reference rates are third-party historical aggregates, not the user's
current-day win probabilities or officially calibrated rates. Shrink strongly,
use *actual* entry course (not frame number), and do not invent wind bearing,
tide height, current direction, race timing or individual maneuver outcomes.

Reference: https://kouei-lab.com/venues.html (historical rolling summary,
aggregation period unspecified; reviewed 2026-10-23). Official Karatsu features:
https://www.boatrace-karatsu.jp/modules/datafile/?page=index_suimen
Other profiles are provisional venue research hypotheses, not measured edges.
"""
from __future__ import annotations

import math

SOURCE = "https://kouei-lab.com/venues.html"
KARATSU_SOURCE = "https://www.boatrace-karatsu.jp/modules/datafile/?page=index_suimen"

# venue code, name, water, course-1 reference win rate, wind exposure,
# tidal/current sensitivity (only a WATCH flag when measurements unavailable),
# layout and tactic to test. The weather risk is not a directional wind prior.
ROWS = [
 ("01","桐生","淡水",.515,"高",False,"風とスタート勘","向かい風・追い風別の逃げ/まくり分岐"),
 ("02","戸田","淡水",.429,"中",False,"狭い1マーク周辺","2〜4コースの仕掛けとインの抵抗"),
 ("03","江戸川","汽水",.477,"高",True,"河川・流れ・波","流向・潮位が未取得なら影響を断定しない"),
 ("04","平和島","海水",.446,"高",True,"風・潮で荒れやすい","差し・まくりと1の残存を分岐"),
 ("05","多摩川","淡水",.535,"低",False,"比較的穏やかな水面","先マイと2コース差しの両立"),
 ("06","浜名湖","汽水",.525,"高",True,"広い水面・進入変化","センターの伸びと外攻めを検討"),
 ("07","蒲郡","汽水",.565,"低",False,"比較的安定した高速水面","先マイ出口の行き足・追走"),
 ("08","常滑","海水",.583,"中",False,"外からの全速戦","イン先マイとセンター攻めの競合"),
 ("09","津","汽水",.564,"高",False,"季節風に注意","強風時のターン失速と差し"),
 ("10","三国","淡水",.525,"高",False,"風と波に注意","2コース差し・3コース攻め"),
 ("11","びわこ","淡水",.534,"高",False,"湖面の風・波","風の変動とまくり差し"),
 ("12","住之江","淡水",.582,"低",False,"比較的穏やかなナイター","インの先マイと2着残存"),
 ("13","尼崎","淡水",.587,"低",False,"1マークの振りが小さい","1先マイと2の差し・センター攻め"),
 ("14","鳴門","海水",.475,"高",True,"潮流と狭い水面の影響","センターのまくりと1の残存"),
 ("15","丸亀","海水",.565,"高",True,"瀬戸内の風・潮","潮流不明時の慎重評価と差し"),
 ("16","児島","海水",.560,"高",True,"広いバックと潮","バック伸び・まくり差し"),
 ("17","宮島","海水",.555,"中",True,"瀬戸内の潮位変化","潮位が分かる場合のみ位置補正"),
 ("18","徳山","海水",.632,"低",True,"比較的穏やかな湾内","先マイ安定性と2・3着残存"),
 ("19","下関","海水",.601,"中",True,"ナイター・潮位変化","先マイと2コース差し"),
 ("20","若松","海水",.581,"高",True,"湾奥・潮と風","潮流が強い日のセンター攻め"),
 ("21","芦屋","淡水",.592,"低",False,"消波された水面","イン先マイと外からの連動"),
 ("22","福岡","汽水",.568,"高",True,"スタート助走が短い","短い助走からの差し・まくり"),
 ("23","唐津","淡水",.557,"中",False,"広い淡水・ピット離れ・風の日内変化","2差し/3まくり差し/4カド/1残存"),
 ("24","大村","海水",.620,"低",True,"インが強めの湾内","イン先マイ優位と2着差し"),
]
VENUE_PROFILES = {
 row[0]: {
   "code":row[0],"name":row[1],"water_type":row[2],
   "course1_reference_rate":row[3],
   "wind_exposure":row[4],"tide_sensitive":row[5],
   "layout_focus":row[6],"tactical_focus":row[7],
   "reference_url":SOURCE,
   "course_prior_provisional":True,
   "source_period":"historical, unspecified on summary: independent verification needed",
 } for row in ROWS
}
VENUE_PROFILES["23"].update({
   "reference_url":KARATSU_SOURCE,
   "stat_reference_url":SOURCE,
   "pit_layout_changed":"2025-12",
   "pit_to_2mark_m":173,
   "wind_pattern":"朝は向かい風、後半は追い風になりやすい（当日の観測を優先）",
   "water_note":"淡水・流れ/水位変化なし。広い水面でスピードを評価。",
   "tactical_focus":"ピット離れ→実進入→1先マイ、2差し、3まくり差し、4カド攻め",
})

def get_profile(venue_code: str) -> dict:
    code = str(venue_code).zfill(2)
    if code not in VENUE_PROFILES:
        raise ValueError(f"Unknown venue code: {venue_code}")
    return dict(VENUE_PROFILES[code])

def adjust_weights(weights: list[float], detail: list[dict], venue_code: str,
                   weather: dict | None = None) -> tuple[list[float], dict]:
    """Apply a *weak and disclosed* course-1 historical prior; no wind direction guess.

    Input scores already include a substantial individual-course advantage.
    Never multiply all lanes by the raw historical win rate. This is an
    experimental low-strength relative correction, NOT a probability model.
    """
    p=get_profile(venue_code)
    if len(weights)!=6 or len(detail)!=6 or any(not math.isfinite(x) or x<=0 for x in weights):
        raise ValueError("Need six positive head weights")
    measured_course=[r.get("course",r.get("lane")) for r in detail]
    if len(set(measured_course))!=6 or set(measured_course)!=set(range(1,7)):
        # Preserve source scores when upstream entry-course data are incomplete.
        return weights[:], {"applied":False,"reason":"進入コースが一意に確定しないため場別補正なし",
                               "profile":p}
    # Raw course 1 win-rate cannot be used as P(1 wins | entrants, weather).
    # Maximum +/- 10% relative shift and deliberately shrunk to 30% of
    # a rough 1-unit sensitivity on historical rate vs 55% reference.
    base=p["course1_reference_rate"]
    shift=max(-.10,min(.10, .30*2.0*(base-.55)))
    inside=measured_course.index(1)
    output=weights[:]
    output[inside] *= math.exp(shift)
    # Special notes and uncertainty flags, not fictitious quantitative bonuses.
    wind=weather.get("wind_speed") if isinstance(weather,dict) else None
    try:wind=float(wind) if wind is not None else None
    except (ValueError,TypeError):wind=None
    caution=(p["wind_exposure"]=="高" and wind is not None and wind>=4)
    return output,{
       "applied":abs(shift)>1e-12,
       "course1_relative_multiplier":round(math.exp(shift),4),
       "course1_reference_rate":base,
       "reference_type":"uncalibrated_weak_prior_third_party",
       "wind_risk": "強風による分岐増を注視（勝ちコースを断定しない）" if caution else None,
       "tide_data_status":"未取得。潮向・潮位の数値補正なし" if p["tide_sensitive"] else "適用対象外",
       "course1_lane":detail[inside].get("lane"),
       "reason":p["tactical_focus"],
       "profile":p,
    }
