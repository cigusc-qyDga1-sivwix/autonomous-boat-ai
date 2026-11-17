"""BOAT LAB venue-aware original exhibition feature contract (RESEARCH ONLY).

All venue timing specifications are provisional metadata until independently
verified on the relevant race. No fixed venue handicaps, head bonuses, bets,
model modification or official-results data enter this transformer.

Source context: BOAT RACE BOATCAST official original exhibition guidance:
https://www.boatrace.jp/owpc/pc/site/news/2025/07/44414/
Venue documentation compiled 2026-11-08, with official source links:
https://hunebaka.com/learn/exhibition/original-times/
"""
from __future__ import annotations
from datetime import datetime, timedelta
import hashlib
import json
import math
from statistics import median

LAP = "lap_time"
HALF = "half_lap_time"
TURN = "turn_time"
STRAIGHT = "straight_time"
METRIC_BOUNDS = {LAP: (30, 55), HALF: (15, 25),
                 TURN: (4, 15), STRAIGHT: (5, 12)}
FULL = (LAP, TURN, STRAIGHT)
HALF_SET = (HALF, TURN, STRAIGHT)
TWO = (LAP, TURN)

# Codes follow BOATRACE's canonical 01–24 numbering.
# "expected" means documented columns, not verified live delivery for every R.
# There are no invented numeric weights or unconditional benefits per venue.
ROWS = [
    ("01", "桐生", HALF_SET, "半周ラップを一周に変換しない", "風・波×半周/旋回×2・3着を検証"),
    ("02", "戸田", FULL, "狭い1M周辺という研究仮説", "差し/まくりの1着・2着を展開別に検証"),
    ("03", "江戸川", (), "独自項目未確認・研究対象外", "オリ展特徴量を生成しない"),
    ("04", "平和島", FULL, "風・潮は当日実測がある場合のみ", "まわり足×波/風と差し残りを検証"),
    ("05", "多摩川", FULL, "まわり足は旋回前後を含む計測", "まわり足×先マイ/差し連動を検証"),
    ("06", "浜名湖", FULL, "独自直線と通常展示は別区間", "独自直線×通常展示の補完性を検証"),
    ("07", "蒲郡", FULL, "通常2周目・1周展示時は1周目", "周回変更を分離して先マイ出口足を検証"),
    ("08", "常滑", FULL, "一周タイムは欠測例あり", "欠測区分を保持して3列それぞれ検証"),
    ("09", "津", FULL, "2026公式攻略本に3項目／現行実配信未検証", "まず実測6艇と公表仕様を照合"),
    ("10", "三国", FULL, "BOATCASTは一周、場独自サイトは半周を配信", "BOATCASTの一周・まわり足を検証"),
    ("11", "びわこ", FULL, "まわり足は1マーク旋回区間", "1Mの旋回力×まくり差し/残りを検証"),
    ("12", "住之江", TWO, "独自直線なし・通常展示で代用禁止", "まわり足×イン残りと2・3着を検証"),
    ("13", "尼崎", TWO, "独自直線なし・通常展示で代用禁止", "まわり足×差し/センター攻めを検証"),
    ("14", "鳴門", FULL, "まわり足・独自直線・通常展示は別区間", "潮/風確認時のターン差を検証"),
    ("15", "丸亀", FULL, "公式案内確認・実配信と区間は逐次検証", "潮とまわり足×2着差しを検証"),
    ("16", "児島", FULL, "2026公式冊子3項目・現行区間詳細未確認", "一周×独自直線と頭抜け/紐抜けを検証"),
    ("17", "宮島", FULL, "旧公式冊子の仕様変更有無は未確認", "潮位実測×旋回/直線の差を検証"),
    ("18", "徳山", TWO, "2026-11-17 2R BOATCAST実通信6艇成功", "まわり足×2着・3着残りを検証"),
    ("19", "下関", FULL, "公式説明で通常2周目を採用", "直線・まわり足×差し/残りを検証"),
    ("20", "若松", FULL, "一周は1周目・他2項目は1/2周の速い方", "周回差を混ぜず独立3列として検証"),
    ("21", "芦屋", FULL, "旋回後直線と通常展示は別区間", "まわり足×外艇の2・3着連動を検証"),
    ("22", "福岡", FULL, "通常展示と独自直線の計測位置差に注意", "進入・STと旋回後の行き足を検証"),
    ("23", "唐津", FULL, "2026-11-17 2R BOATCAST実通信6艇成功", "1M先マイ/差し/まくり差しを比較"),
    ("24", "大村", FULL, "計測区間の変更記録あり・旧図流用禁止", "1号艇残存×旋回タイム・頭選択を検証"),
]

VENUE_SPECS = {
    code: {"venue_code": code, "venue": name, "expected_metrics": metrics,
           "measurement_note": note, "hypothesis_to_test": hypothesis,
           "research_only": True}
    for code, name, metrics, note, hypothesis in ROWS
}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO8601 string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def venue_features(capture: dict, *, frozen_at_utc: str,
                   cutoff_at_jst: str) -> dict:
    """Return relative same-race timing evidence, NEVER tickets/predictions.

    Must be actual same-day six-boat source capture *before* immutable freeze.
    A 2-minute cutoff margin is mandatory; historical replays return no data.
    Do not mark provider data official merely because six values are present.
    """
    if not isinstance(capture, dict):
        raise ValueError("capture must be object")
    code = capture.get("venue_code")
    if code not in VENUE_SPECS:
        raise ValueError("unknown venue code")
    spec = VENUE_SPECS[code]
    if not spec["expected_metrics"]:
        return {"status": "VENUE_EXCLUDED", "research_only": True,
                "venue_code": code, "features": {}}
    observed = _time(capture.get("captured_at_utc"))
    frozen = _time(frozen_at_utc)
    cutoff = _time(cutoff_at_jst)
    if observed > frozen or frozen >= cutoff - timedelta(minutes=2):
        raise ValueError("capture not proven before eligible freeze")
    if observed.date() != cutoff.date() and (
            observed.astimezone(cutoff.tzinfo).date() != cutoff.date()):
        raise ValueError("different race day")
    if capture.get("status") != "SIX_BOAT_PARSED_RESEARCH_ONLY" or not capture.get("research_only"):
        raise ValueError("source not verified as six-boat research capture")
    if capture.get("formal_forecast_eligible") is not False:
        raise ValueError("must not masquerade as formal certified source")
    day = cutoff.date()
    race = capture.get("race_number")
    if type(race) is not int or not 1 <= race <= 12:
        raise ValueError("invalid race")
    canonical = (f"https://race.boatcast.jp/txt/{code}/"
                 f"bc_oriten_{day:%Y%m%d}_{code}_{race:02d}.txt")
    if capture.get("source_url") != canonical or capture.get("date") != day.isoformat():
        raise ValueError("unexpected source identity")
    boats = capture.get("boats")
    if not isinstance(boats, list) or len(boats) != 6 or (
            {b.get("lane") for b in boats if isinstance(b, dict)}
            != set(range(1, 7))):
        raise ValueError("six distinct boat entries required")
    if capture.get("measurement_sha256") != digest(boats):
        raise ValueError("measurement digest mismatch")
    ordered = sorted(boats, key=lambda b: b["lane"])
    available = capture.get("metrics")
    if not isinstance(available, list):
        raise ValueError("metric manifest absent")
    features = {}
    status = {}
    for metric in spec["expected_metrics"]:
        if metric not in available:
            status[metric] = "NOT_OFFERED"
            continue
        raw = [b.get(metric) for b in ordered]
        lo, hi = METRIC_BOUNDS[metric]
        if not all(type(v) in (int, float) and math.isfinite(v)
                   and lo <= v <= hi for v in raw):
            status[metric] = "MISSING_OR_INVALID_SIX_BOAT"
            continue
        mid = median(raw)
        fastest = min(raw)
        features[metric] = {
            str(b["lane"]): {
                "seconds": round(v, 5),
                "advantage_over_race_median_seconds": round(mid - v, 5),
                "gap_to_fastest_seconds": round(v-fastest, 5),
                "within_race_midrank": round(
                    1 + sum(a < v for a in raw) +
                    (sum(a == v for a in raw)-1)/2, 2),
            }
            for b, v in zip(ordered, raw)
        }
        status[metric] = "SIX_BOAT_COMPLETE"
    return {
        "schema": "boatlabs.venue_original_relative_features.v0.1",
        "status": "RESEARCH_ONLY",
        "venue_code": code,
        "race_number": race,
        "venue": spec["venue"],
        "source_url": canonical,
        "capture_sha256": digest(capture),
        "raw_measurement_sha256": capture["measurement_sha256"],
        "captured_at_utc": capture["captured_at_utc"],
        "frozen_at_utc": frozen_at_utc,
        "metric_status": status,
        "features": features,
        "research_only": True,
        "formal_tickets_changed": False,
        "formal_model_eligible": False,
        "not_estimated_probabilities": True,
        "no_outcomes_or_payouts_used": True,
    }
