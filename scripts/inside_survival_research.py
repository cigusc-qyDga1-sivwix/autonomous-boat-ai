"""Pre-cutoff lane-1 defence / residual-place RESEARCH diagnostic.

Never changes formal tickets, ranking, stakes, training model or historical
snapshots. The fixed thresholds below are exploratory hypotheses from the
2026-11-13 review and MUST NOT be presented as calibrated probabilities.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from itertools import permutations
from math import isfinite, isclose

VERSION = "inside-survival-forward-shadow-v0.1"
COMBOS = {"-".join(map(str, p)) for p in permutations(range(1, 7), 3)}


def _num(value, low, high):
    return (float(value) if type(value) in (int, float) and
            isfinite(value) and low <= value <= high else None)


def _turn(boat):
    original = boat.get("original_exhibition")
    return _num(original.get("turn_time"), 4, 15) if isinstance(original, dict) else None


def evaluate(snapshot: dict, ranked: list[dict], bets: list[dict]) -> dict:
    """Measure three mutually exclusive hypotheses using only frozen inputs.

    Returns a research-only companion diagnostic for a NEW forecast snapshot.
    Result, payout, actual ST, odds, and later racing video are never inspected.
    The supplied formal ranking is summarized, NOT reranked or reallocated.
    """
    base = {
        "version": VERSION, "model_role": "research_shadow",
        "formal_tickets_changed": False, "actual_purchase": False,
        "result_data_used": False, "odds_used": False, "calibrated": False,
        "thresholds_prospectively_validated": False,
        "no_extra_stake": True, "no_historical_overwrite": True,
    }
    if snapshot.get("phase") != "exhibition" or snapshot.get("venue") == "江戸川":
        return {**base, "status": "NOT_ELIGIBLE"}
    try:
        frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
        cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
        if frozen.tzinfo is None or cutoff.tzinfo is None or frozen > cutoff - timedelta(minutes=2):
            return {**base, "status": "NO_SAFE_PRE_CUTOFF_FREEZE"}
    except (KeyError, TypeError, ValueError):
        return {**base, "status": "NO_SAFE_PRE_CUTOFF_FREEZE"}

    racers = snapshot.get("racers")
    if not isinstance(racers, list) or len(racers) != 6:
        return {**base, "status": "MISSING_SIX_BOATS"}
    if any(not isinstance(r, dict) for r in racers):
        return {**base, "status": "MISSING_SIX_BOATS"}
    lanes = {r.get("lane") for r in racers}
    courses = {r.get("course") for r in racers}
    if lanes != set(range(1, 7)) or courses != set(range(1, 7)):
        return {**base, "status": "INVALID_ACTUAL_ENTRY"}
    by_lane = {r["lane"]: r for r in racers}
    by_course = {r["course"]: r for r in racers}
    if by_course[1]["lane"] != 1:
        return {**base, "status": "LANE_ONE_NOT_IN_COURSE_ONE"}

    metrics = {}
    for course, boat in by_course.items():
        time = _num(boat.get("exhibition_time"), 5, 10)
        turn = _turn(boat)
        if time is None or turn is None:
            return {**base, "status": "MISSING_SIX_BOAT_TURN_AND_TIME"}
        avg_st = (None if boat.get("average_start_timing_imputed")
                  else _num(boat.get("average_start_timing"), .01, .40))
        legal_show = _num(boat.get("exhibition_st"), 0, .50)
        metrics[course] = {"lane": boat["lane"], "time": time, "turn": turn,
                           "average_st": avg_st, "legal_show_st": legal_show}

    if not isinstance(ranked, list) or len(ranked) != 120:
        return {**base, "status": "INVALID_CANONICAL_RANKING"}
    scores = {}
    for item in ranked:
        if not isinstance(item, dict):
            return {**base, "status": "INVALID_CANONICAL_RANKING"}
        key = item.get("combination")
        val = _num(item.get("score"), 0, 1)
        if key not in COMBOS or key in scores or val is None:
            return {**base, "status": "INVALID_CANONICAL_RANKING"}
        scores[key] = val
    if set(scores) != COMBOS or not isclose(sum(scores.values()), 1, abs_tol=0.00001):
        return {**base, "status": "INVALID_CANONICAL_RANKING"}
    if not isinstance(bets, list) or any(not isinstance(b, dict) for b in bets):
        return {**base, "status": "INVALID_FORMAL_BETS"}
    selected = [b.get("combination") for b in bets]
    if len(set(selected)) != len(selected) or any(k not in COMBOS for k in selected):
        return {**base, "status": "INVALID_FORMAL_BETS"}

    inside = metrics[1]
    threats = []
    for course in range(2, 7):
        outsider = metrics[course]
        st_edge = (inside["average_st"] - outsider["average_st"]
                   if inside["average_st"] is not None and outsider["average_st"] is not None
                   else None)
        time_edge = inside["time"] - outsider["time"]
        turn_edge = inside["turn"] - outsider["turn"]
        # Require two independent signals; a flattering exhibition ST alone
        # cannot switch the first-place candidate.
        qualified = ((st_edge is not None and st_edge >= .018 and
                      (time_edge >= .05 or turn_edge >= .10)) or
                     (time_edge >= .06 and turn_edge >= .15))
        if not qualified:
            continue
        show_confirmation = (
            inside["legal_show_st"] is not None and
            outsider["legal_show_st"] is not None and
            inside["legal_show_st"] - outsider["legal_show_st"] >= .035
        )
        # Independent from attack success: may the defender still retain
        # second/third despite the challenger winning?
        survives = (inside["turn"] <= outsider["turn"] + .10 or
                    inside["time"] <= outsider["time"] + .04)
        threats.append({
            "challenger_lane": outsider["lane"], "challenger_course": course,
            "average_st_edge": round(st_edge, 4) if st_edge is not None else None,
            "time_edge": round(time_edge, 4),
            "turn_edge": round(turn_edge, 4),
            "legal_exhibition_st_confirmation": show_confirmation,
            "inside_second_third_path_supported": survives,
            "inside_displacement_hypothesis": not survives,
        })

    def mass(predicate):
        return round(sum(v for k, v in scores.items() if predicate(k.split("-"))), 7)

    inside_head = mass(lambda c: c[0] == "1")
    inside_second = mass(lambda c: c[0] != "1" and c[1] == "1")
    inside_third = mass(lambda c: c[0] != "1" and c[2] == "1")
    inside_out = mass(lambda c: "1" not in c)
    return {
        **base, "status": "ATTACK_PATHS_PRESENT" if threats else "NO_QUALIFIED_ATTACK_PATH",
        "source_frozen_at_utc": snapshot["frozen_at_utc"],
        "source_cutoff_iso_jst": snapshot["cutoff_iso_jst"],
        "inside_lane": 1, "inside_actual_course": 1,
        "source_metrics": ["exhibition_time", "original_exhibition.turn_time",
                           "nonimputed_average_start_timing", "legal_exhibition_st"],
        "actual_entry": {str(c): metrics[c]["lane"] for c in range(1, 7)},
        "threats": threats,
        "scenario_relative_mass_unCALIBRATED": {
            "inside_escapes_head": inside_head,
            "inside_second_after_attack": inside_second,
            "inside_third_after_attack": inside_third,
            "inside_absent_from_top3": inside_out,
        },
        "formal_ticket_coverage": {
            "inside_head": sum(c.split("-")[0] == "1" for c in selected),
            "inside_second_after_attack": sum(c.split("-")[0] != "1" and c.split("-")[1] == "1" for c in selected),
            "inside_third_after_attack": sum(c.split("-")[0] != "1" and c.split("-")[2] == "1" for c in selected),
            "inside_absent_from_top3": sum("1" not in c.split("-") for c in selected),
            "original_ticket_count": len(selected),
        },
        "validation_policy": ("Same-race, same-point, pre-cutoff frozen forward comparison; "
                              "do not modify MAIN on this evidence alone."),
    }
