"""Pre-cutoff race-flow cues for BOAT LAB (research-only, no bets).

Interpret attack/guard/follower tension from verified, actual-course exhibition
inputs. Cues describe *possible* 1M paths, not observed moves, calibrated
probabilities, or instructions to change the formal forecast.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite

VERSION = "race-flow-cues-v0.1-research-only"
FORBIDDEN = {"result", "finish", "actual_finish", "actual_start", "payout",
             "odds", "kimarite", "actual_tactic", "observed_maneuver"}


def _number(value, low, high):
    if type(value) not in (int, float) or not isfinite(value):
        return None
    return float(value) if low <= value <= high else None


def _timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone_aware_capture_required")
    return dt


def inspect(racers, *, captured_at_utc, cutoff_at_utc, exhibition_verified):
    """Build explainable cues without reading result data or altering tickets.

    Requires explicit actual course and lane for all six boats, a verified
    pre-cutoff source, and a two-minute freeze margin. Returns NO_EVIDENCE
    rather than imputing missing ST or turn data. No betting recommendation.
    """
    captured, cutoff = _timestamp(captured_at_utc), _timestamp(cutoff_at_utc)
    if captured > cutoff - timedelta(minutes=2):
        raise ValueError("late_exhibition_snapshot")
    audit = {
        "version": VERSION, "role": "research_shadow", "not_formal": True,
        "results_used": False, "odds_used": False, "calibrated": False,
        "bets_modified": False, "captured_at_utc": captured_at_utc,
        "scenarios": [], "evidence": {}, "status": "NO_EVIDENCE",
    }
    if not exhibition_verified:
        audit["status"] = "UNVERIFIED_EXHIBITION"
        return audit
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("six_actual_course_racers_required")
    by_course, lanes = {}, set()
    for row in racers:
        if not isinstance(row, dict) or FORBIDDEN.intersection(row):
            raise ValueError("outcome_data_or_invalid_racer")
        c, lane = row.get("course"), row.get("lane")
        if type(c) is not int or type(lane) is not int or c not in range(1, 7) or lane not in range(1, 7):
            raise ValueError("explicit_actual_entry_required")
        if c in by_course or lane in lanes:
            raise ValueError("duplicate_course_or_lane")
        original = row.get("original_exhibition")
        if isinstance(original, dict) and FORBIDDEN.intersection(original):
            raise ValueError("outcome_data_in_exhibition")
        by_course[c] = row
        lanes.add(lane)
    if len(by_course) != 6 or len(lanes) != 6:
        raise ValueError("missing_actual_course")
    features = {}
    for course, row in by_course.items():
        raw = row.get("original_exhibition")
        if not isinstance(raw, dict) or row.get("average_start_timing_imputed"):
            audit["status"] = "INCOMPLETE_PRE_CUTOFF_FEATURES"
            return audit
        avg = _number(row.get("average_start_timing"), .01, .40)
        st = _number(row.get("exhibition_st"), 0, .45)  # F-start is not valid proof
        exhibit = _number(row.get("exhibition_time"), 5, 10)
        turn = _number(raw.get("turn_time"), 4, 15)
        if None in (avg, st, exhibit, turn):
            audit["status"] = "INCOMPLETE_PRE_CUTOFF_FEATURES"
            return audit
        features[course] = {"lane": row["lane"], "avg": avg, "st": st,
                            "exhibit": exhibit, "turn": turn}

    inside, guard, corner, follower = (features[x] for x in (1, 3, 4, 5))
    corner_st_gap = guard["st"] - corner["st"]
    corner_avg_gap = guard["avg"] - corner["avg"]
    corner_turn_gap = guard["turn"] - corner["turn"]
    # Independent support from average ST AND turn performance, rather than
    # one flattering exhibition ST. Thresholds are hypotheses, not fitted.
    start_pressure = corner_st_gap >= .025 and corner_avg_gap >= .015
    turn_pressure = corner_turn_gap >= .035 and corner["exhibit"] <= guard["exhibit"] + .04
    corner_pressure = start_pressure and turn_pressure
    guard_resists = guard["turn"] <= corner["turn"] + .06 and guard["avg"] <= corner["avg"] + .03
    follower_close = (
        follower["st"] <= corner["st"] + .03
        and follower["turn"] <= corner["turn"] + .10
        and follower["exhibit"] <= corner["exhibit"] + .06
    )
    inside_competitive = (
        inside["turn"] <= corner["turn"] + .15
        and inside["avg"] <= corner["avg"] + .06
    )
    audit["evidence"] = {
        "actual_course_to_lane": {str(c): v["lane"] for c, v in features.items()},
        "corner_minus_guard_exhibition_st_s": round(-corner_st_gap, 4),
        "corner_average_st_advantage_s": round(corner_avg_gap, 4),
        "corner_turn_advantage_s": round(corner_turn_gap, 4),
        "start_pressure": start_pressure,
        "turn_pressure": turn_pressure,
        "corner_pressure": corner_pressure,
        "guard_can_resist": guard_resists,
        "follower_can_track": follower_close,
        "inside_can_counter": inside_competitive,
    }
    if corner_pressure:
        audit["scenarios"].append("FOUR_COURSE_CORNER_ATTACK_POSSIBLE")
        if guard_resists:
            audit["scenarios"].append("THREE_COURSE_GUARD_RESISTANCE_POSSIBLE")
        if follower_close:
            audit["scenarios"].append("FIVE_COURSE_FOLLOWER_OPPORTUNITY")
        if inside_competitive:
            audit["scenarios"].append("INSIDE_SURVIVAL_OR_COUNTER_PATH")
        audit["status"] = "SUPPORTED_PRE_CUTOFF_CUES"
    else:
        audit["status"] = "NO_INDEPENDENT_CORNER_SIGNAL"
    return audit
