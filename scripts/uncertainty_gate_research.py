"""Outcome-blind pre-race uncertainty triage for BOAT LAB research only.

The gate is NOT a calibrated probability or a production SKIP signal.
Choose the fixed thresholds BEFORE seeing the next day's outcomes.
Exhibition-F, actual entry, wind/wave and six-boat time-versus-turn evidence
must be present in the immutable PRE-CUTOFF snapshot.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite

VERSION = "uncertainty-precutoff-shadow-v0.1"


def _number(value, lo, hi):
    return float(value) if type(value) in (float, int) and isfinite(value) and lo <= value <= hi else None


def evaluate(snapshot: dict) -> dict:
    """Evaluate independently of finish, payout, realized ST, odds and bets."""
    base = {
        "version": VERSION, "model_role": "research_shadow",
        "formal_bets_changed": False, "model_weights_changed": False,
        "result_data_used": False, "calibrated": False,
        "retrospective_thresholds_not_validated": True,
        "not_a_formal_buy_or_skip": True,
    }
    if snapshot.get("venue") == "江戸川":
        return {**base, "status": "OUT_OF_SCOPE"}
    if snapshot.get("phase") != "exhibition":
        return {**base, "status": "HOLD_NO_PRE_CUTOFF_EXHIBITION"}
    try:
        frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
        cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
        if frozen.tzinfo is None or cutoff.tzinfo is None or frozen > cutoff - timedelta(minutes=2):
            return {**base, "status": "HOLD_UNPROVEN_PRE_CUTOFF"}
    except (KeyError, TypeError, ValueError):
        return {**base, "status": "HOLD_UNPROVEN_PRE_CUTOFF"}
    racers = snapshot.get("racers")
    if not isinstance(racers, list) or len(racers) != 6 or any(not isinstance(x, dict) for x in racers):
        return {**base, "status": "HOLD_INCOMPLETE_SIX_BOATS"}
    if {x.get("lane") for x in racers} != set(range(1, 7)):
        return {**base, "status": "HOLD_INCOMPLETE_SIX_BOATS"}
    courses = [x.get("course") for x in racers]
    if set(courses) != set(range(1, 7)):
        return {**base, "status": "HOLD_UNVERIFIED_ENTRY"}
    st = [_number(x.get("exhibition_st"), -.5, .5) for x in racers]
    times = [_number(x.get("exhibition_time"), 5, 10) for x in racers]
    if any(x is None for x in st + times):
        return {**base, "status": "HOLD_INCOMPLETE_EXHIBITION"}
    turns = [_number((x.get("original_exhibition") or {}).get("turn_time"), 4, 15)
             for x in racers]
    f_count = sum(x < 0 for x in st)
    entry_changed = any(x["course"] != x["lane"] for x in racers)
    weather = snapshot.get("weather_used") or {}
    wind = _number(weather.get("wind_speed"), 0, 30)
    wave = _number(weather.get("wave_height"), 0, 100)
    extreme_weather = (wind is not None and wind >= 5) or (wave is not None and wave >= 5)
    # Contradictory evidence: an outside challenger (2-4) is much faster in
    # exhibition but slower in turning than the inside boat. Race-specific,
    # no winner information. This is an uncertainty marker, not an advantage.
    contradictory = False
    if turns[0] is not None:
        contradictory = any(
            times[0] - times[i] >= .06 and
            turns[i] is not None and turns[i] - turns[0] >= .10
            for i in (1, 2, 3)
        )
    points = (2 if f_count >= 2 else 1 if f_count == 1 else 0)
    points += int(entry_changed) + int(extreme_weather) + int(contradictory)
    signals = {
        "exhibition_f_count": f_count,
        "entry_rearranged": entry_changed,
        "strong_wind_or_wave": extreme_weather,
        "exhibition_speed_vs_turn_contradiction": contradictory,
        "turn_time_coverage": sum(x is not None for x in turns),
    }
    status = "SKIP_SHADOW" if points >= 2 else "WATCH_SHADOW" if points else "KEEP_SHADOW"
    return {
        **base, "status": status, "risk_points": points, "signals": signals,
        "snapshot_frozen_at_utc": snapshot["frozen_at_utc"],
        "cutoff_iso_jst": snapshot["cutoff_iso_jst"],
        "hypothesis": "Multiple independent uncertainties can undermine exact 3連単 ranking",
        "research_policy": "Separate from clean-candidate research cohort for comparison only; never exclude from training or formal bets without forward validation",
        "threshold_policy": "F>=2 yields 2 risk points; each other independent signal 1; skip threshold >=2",
    }
