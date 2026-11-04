"""Postrace START x winning-technique proxy for potential 1M interactions.

These are OBSERVED ST contrasts and outcome-conditioned hypotheses, not
confirmed marks, intentional interference, 1M positions, or causal effects.
Historical studies only. Never inject the current race's outcome into forecasts.
Input schema: BoatraceCSV results/realtime columns.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Mapping

VERSION = "start-technique-pressure-proxy-v0.1"
TECHNIQUES = {"逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"}
ATTACK_TECHNIQUES = {"まくり", "まくり差し"}
# Descriptive thresholds for research, not empirically validated cutoffs.
CLOSE_ST_SEC = .03
CLEAR_START_LEAD_SEC = .05


def _int(value, lo, hi, name):
    if isinstance(value, bool):
        raise ValueError(name)
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError(name) from None
    if str(value).strip() != str(n) or not lo <= n <= hi:
        raise ValueError(name)
    return n


def _st(value, flying):
    if value is None or str(value).strip() in ("", "-"):
        return None, "MISSING"
    try:
        st = float(value)
    except (TypeError, ValueError):
        return None, "INVALID"
    if not isfinite(st) or not -.50 <= st <= .99:
        return None, "INVALID"
    if (str(flying).strip().upper() == "F") or st < 0:
        return None, "FLYING"
    return st, "LEGAL"


def interpret(row: Mapping, *, event_date: str, source_sha256: str) -> dict:
    """Strictly result-side descriptive feature extraction.

    Deliberately excludes race odds, speculative boat targeting, and strategy
    scoring. Must not be called in the live forecasting pipeline.
    """
    if not isinstance(row, Mapping):
        raise ValueError("result row mapping required")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("source provenance required")
    try:
        day = date.fromisoformat(event_date)
    except (ValueError, TypeError):
        raise ValueError("event date required") from None
    code = str(row.get("レースコード", ""))
    if len(code) != 12 or not code.isdigit() or code[:8] != day.strftime("%Y%m%d"):
        raise ValueError("result event identity mismatch")
    winner = _int(row.get("1着_艇番"), 1, 6, "winner boat")
    technique = row.get("決まり手")
    if technique not in TECHNIQUES:
        raise ValueError("unknown / missing winning technique")
    boats = {}
    for course in range(1, 7):
        prefix = f"{course}コース_"
        lane = _int(row.get(prefix + "艇番"), 1, 6, "actual course boat")
        if lane in boats:
            raise ValueError("duplicate actual course")
        value, status = _st(row.get(prefix + "スタートタイミング"), row.get(prefix + "F"))
        boats[lane] = {"course": course, "st": value, "st_status": status}
    if set(boats) != set(range(1, 7)):
        raise ValueError("six actual course boats required")
    winner_course = boats[winner]["course"]
    if technique == "逃げ" and winner_course != 1:
        raise ValueError("escape cannot be won from outside course")
    comparisons = []
    for inner_course in range(1, winner_course):
        inside_lane = next(l for l, b in boats.items() if b["course"] == inner_course)
        attacker, inside = boats[winner], boats[inside_lane]
        if technique not in ATTACK_TECHNIQUES:
            continue
        if attacker["st_status"] != "LEGAL" or inside["st_status"] != "LEGAL":
            comparisons.append({
                "inside_lane": inside_lane, "inside_course": inner_course,
                "status": "UNKNOWN_START", "st_gap_sec": None,
                "hypothesis": "cannot_evaluate_start_interaction",
            })
            continue
        # Positive: outer race winner started earlier than inner boat.
        gap = round(inside["st"] - attacker["st"], 3)
        if gap >= CLEAR_START_LEAD_SEC:
            hypothesis = "outer_start_advantage"
        elif abs(gap) <= CLOSE_ST_SEC:
            hypothesis = "close_start_possible_course_contest"
        else:
            hypothesis = "no_clear_start_advantage"
        comparisons.append({
            "inside_lane": inside_lane, "inside_course": inner_course,
            "status": "OBSERVED_START_CONTRAST",
            "st_gap_sec": gap, "hypothesis": hypothesis,
        })
    return {
        "schema": VERSION, "race_code": code, "event_date": event_date,
        "source_sha256": source_sha256, "winner_lane": winner,
        "winner_course": winner_course, "winning_technique": technique,
        "actual_course_order": [next(l for l, b in boats.items() if b["course"] == c)
                                for c in range(1, 7)],
        "st_by_lane": {str(l): boats[l]["st"] for l in range(1, 7)},
        "st_status_by_lane": {str(l): boats[l]["st_status"] for l in range(1, 7)},
        "comparisons": comparisons,
        "confirmed_mark_count": None,
        "interpretation": "POSTRACE_PROXY_NOT_OBSERVED_DEFENSE",
        "eligible_as_same_race_forecast_input": False,
    }


def summarize(records: list[dict]) -> dict:
    """Aggregate evidence categories with UNKNOWN retained; no mark counts."""
    counts = {"outer_start_advantage": 0,
              "close_start_possible_course_contest": 0,
              "no_clear_start_advantage": 0,
              "cannot_evaluate_start_interaction": 0}
    seen = set()
    for record in records:
        if record.get("schema") != VERSION or record.get("race_code") in seen:
            raise ValueError("invalid/duplicate result proxy")
        seen.add(record["race_code"])
        for c in record["comparisons"]:
            if c["hypothesis"] not in counts:
                raise ValueError("unknown hypothesis")
            counts[c["hypothesis"]] += 1
    return {"version": VERSION, "races": len(seen), "comparison_counts": counts,
            "confirmed_mark_count": None,
            "notes": "Multiple inner-course comparisons per race; not unique encounters"}
