"""Evidence-only four-leg exhibition breakdown. NOT formal inference.

Produces four distinguishable evidence categories without inventing motor power,
acceleration, absolute scores, predictive probabilities, or video observations.
The strict venue_features contract checks pre-cutoff, source URL, six boats and SHA.
"""
from __future__ import annotations

from datetime import datetime
import math
import re
import unicodedata
from statistics import median

from scripts.original_exhibition_venue_research import VENUE_SPECS, venue_features

SCHEMA = "boatlabs.four_leg_exhibition_evidence.research.v0.1"


def _name(value: object) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def _number(value: object, lo: float, hi: float) -> float | None:
    if type(value) not in (int, float):
        return None
    return float(value) if math.isfinite(value) and lo <= value <= hi else None


def _relative(metric: dict | None, lane: int) -> dict | None:
    if not isinstance(metric, dict):
        return None
    row = metric.get(str(lane))
    if not isinstance(row, dict):
        return None
    return {
        "seconds": row["seconds"],
        "advantage_over_race_median_seconds": row["advantage_over_race_median_seconds"],
        "within_race_midrank": row["within_race_midrank"],
    }


def assess(snapshot: dict, capture: dict) -> dict:
    """Label what is observed vs inferred for each of six boats.

    This only accepts a true pre-cutoff normal-exhibition snapshot plus
    an exact same-race BOATCAST original source with six boat names.
    It is standalone research, never mutates the snapshot or formal tickets.
    """
    if not isinstance(snapshot, dict) or snapshot.get("phase") != "exhibition":
        raise ValueError("a frozen exhibition snapshot is required")
    origin = snapshot.get("exhibition_origin") or {}
    if origin.get("captured_before_cutoff") is not True:
        raise ValueError("normal exhibition was not verified before cutoff")
    values = venue_features(capture, frozen_at_utc=snapshot["frozen_at_utc"],
                            cutoff_at_jst=snapshot["cutoff_iso_jst"])
    if values.get("status") == "VENUE_EXCLUDED":
        return {
            "schema": SCHEMA, "status": "VENUE_EXCLUDED",
            "research_only": True, "formal_tickets_changed": False,
            "axis_scores_calibrated": False,
        }
    code = capture["venue_code"]
    if ((VENUE_SPECS[code]["venue"] != snapshot.get("venue"))
            or capture.get("race_number") != snapshot.get("race")):
        raise ValueError("venue or race does not match formal snapshot")
    racers = snapshot.get("racers")
    if (not isinstance(racers, list) or len(racers) != 6
            or {r.get("lane") for r in racers if isinstance(r, dict)} != set(range(1, 7))
            or {r.get("course") for r in racers if isinstance(r, dict)} != set(range(1, 7))):
        raise ValueError("six actual course positions required")
    by_lane = {r["lane"]: r for r in racers}
    by_original = {b["lane"]: b for b in capture["boats"]}
    if any(_name(by_lane[lane].get("name")) != _name(by_original[lane].get("name"))
           for lane in range(1, 7)):
        raise ValueError("six racer names do not match original capture")
    times = [_number(by_lane[i].get("exhibition_time"), 5, 10) for i in range(1, 7)]
    sts = [_number(by_lane[i].get("exhibition_st"), -.5, 1) for i in range(1, 7)]
    if any(t is None for t in times) or any(st is None for st in sts):
        raise ValueError("normal six-boat exhibition lacks measured time or ST")
    middle = median(times)
    mapped = values["features"]
    result = []
    for lane in range(1, 7):
        row = by_lane[lane]
        turn = _relative(mapped.get("turn_time"), lane)
        straight = _relative(mapped.get("straight_time"), lane)
        lap = _relative(mapped.get("lap_time"), lane)
        half = _relative(mapped.get("half_lap_time"), lane)
        regular = {
            "seconds": times[lane-1],
            "advantage_over_race_median_seconds": round(middle-times[lane-1], 5),
            "measurement": "normal_exhibition_segment_not_independent_entrance_acceleration",
        }
        result.append({
            "lane": lane, "course": row["course"],
            "行き足": {
                "status": "UNQUANTIFIABLE_WITH_TIMES_ALONE",
                "direct_acceleration_data": False,
                "exhibition_st_seconds_context_only": sts[lane-1],
                "requires": ["start_exhibition_video_position_time",
                             "run_up_start_point_and_distance",
                             "same_race_actual_entry_and_wind"],
                "numeric_score": None,
            },
            "出足": {
                "status": "INDIRECT_EVIDENCE_ONLY" if turn or straight else "NO_SEGMENT_EVIDENCE",
                "turn_interval_seconds": turn,
                "post_turn_straight_interval_seconds": straight,
                "direct_acceleration_data": False,
                "requires": ["turn_exit_video_speed_over_time", "consistent_measurement_boundaries"],
                "numeric_score": None,
            },
            "伸び足": {
                "status": "MEASURED_TIMING_PROXY",
                "normal_exhibition_relative": regular,
                "original_straight_relative": straight,
                "venue_note": ("福岡の通常展示はターン出口からの加速成分も含む"
                               if code == "22" else
                               "通常展示と独自直線の計測区間は必ずしも一致しない"),
                "numeric_score": None,
            },
            "まわり足": {
                "status": ("MEASURED_TURN_INTERVAL_PROXY" if turn else
                           "TURN_INTERVAL_NOT_AVAILABLE"),
                "original_turn_relative": turn,
                "whole_lap_relative": lap,
                "half_lap_relative": half,
                "pure_motor_power_not_isolated": True,
                "numeric_score": None,
            },
        })
    return {
        "schema": SCHEMA, "status": "SIX_BOAT_EVIDENCE_RESEARCH_ONLY",
        "venue": snapshot["venue"], "venue_code": code, "race": snapshot["race"],
        "capture_sha256": values["capture_sha256"],
        "measurement_sha256": values["raw_measurement_sha256"],
        "source_url": values["source_url"],
        "captured_at_utc": values["captured_at_utc"],
        "frozen_at_utc": values["frozen_at_utc"],
        "original_metric_status": values["metric_status"],
        "boats": result,
        "research_only": True, "formal_tickets_changed": False,
        "predictive_probabilities_calibrated": False,
        "no_results_odds_or_payouts_used": True,
        "not_a_trained_or_verified_four_leg_model": True,
    }
