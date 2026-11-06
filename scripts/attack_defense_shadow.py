"""Attack/defence conditional ranking as an isolated *forward* research shadow.

Uses ONLY six pre-cutoff racer records and the existing 120 canonical outcomes.
No past-race result, payout, odds, or observed manoeuvre is an input.
Input features may already be counted by the main model: the bounded changes
below are HYPOTHESES for same-time A/B evaluation, not calibrated probabilities.
"""
from __future__ import annotations

import math
from datetime import datetime
from itertools import permutations

VERSION = "attack-defence-six-boat-shadow-v0.1-untrained"
OUTCOMES = {"-".join(map(str, triple)) for triple in permutations(range(1, 7), 3)}
PROHIBITED_FIELDS = {"result", "finish", "rank", "payout", "odds", "actual_start",
                     "actual_finish", "kimarite", "actual_tactic"}


def _finite(v):
    return float(v) if type(v) in (int, float) and math.isfinite(v) else None


def _valid_pre_race(racers, outcomes, captured_at, cutoff_at):
    captured, cutoff = datetime.fromisoformat(captured_at), datetime.fromisoformat(cutoff_at)
    if captured.tzinfo is None or cutoff.tzinfo is None or captured >= cutoff:
        raise ValueError("Capture must be verified before cutoff")
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("Six racers needed")
    by_lane, by_course = {}, {}
    for r in racers:
        if not isinstance(r, dict) or set(r).intersection(PROHIBITED_FIELDS):
            raise ValueError("Post-race input prohibited")
        lane, course = r.get("lane"), r.get("course")
        if type(lane) is not int or type(course) is not int:
            raise ValueError("Explicit actual courses required")
        if not 1 <= lane <= 6 or lane in by_lane or not 1 <= course <= 6 or course in by_course:
            raise ValueError("Six unique actual courses required")
        by_lane[lane], by_course[course] = r, lane
    if set(by_lane) != set(range(1, 7)) or set(by_course) != set(range(1, 7)):
        raise ValueError("Incomplete actual entry")
    if not isinstance(outcomes, list) or len(outcomes) != 120:
        raise ValueError("Canonical 120 outcomes required")
    candidates = {}
    for item in outcomes:
        if not isinstance(item, dict) or set(item).intersection(PROHIBITED_FIELDS):
            raise ValueError("Post-race outcome fields prohibited")
        combination, score = item.get("combination"), _finite(item.get("relative_score"))
        if combination not in OUTCOMES or combination in candidates or score is None or score <= 0:
            raise ValueError("Invalid candidate mass")
        candidates[combination] = score
    if set(candidates) != OUTCOMES or not math.isclose(sum(candidates.values()), 1, abs_tol=1e-6):
        raise ValueError("Missing/unnormalized canonical outcomes")
    return by_lane, by_course, candidates


def _evidence(racer, defender):
    """Threat is a *relative pre-race signal*, not a measured attack.

    Relative signals, rather than absolute ST, avoid calling every outer lane
    an attacker. Exhibition F is excluded; no imputation can create an edge.
    """
    st_a, st_d = _finite(racer.get("average_start_timing")), _finite(defender.get("average_start_timing"))
    ex_a, ex_d = _finite(racer.get("exhibition_time")), _finite(defender.get("exhibition_time"))
    show_a, show_d = _finite(racer.get("exhibition_st")), _finite(defender.get("exhibition_st"))
    start_edge = (st_d - st_a if st_a is not None and st_d is not None
                  and .01 <= st_a <= .40 and .01 <= st_d <= .40
                  and not racer.get("average_start_timing_imputed")
                  and not defender.get("average_start_timing_imputed") else 0.)
    time_edge = ex_d - ex_a if ex_a is not None and ex_d is not None and 5 <= ex_a <= 10 and 5 <= ex_d <= 10 else 0.
    # Exhibition ST is volatile; it only confirms an existing average-ST or time
    # edge, and a flying exhibition start never counts as legal speed evidence.
    show_confirm = (show_a is not None and show_d is not None and
                    0 <= show_a <= .50 and 0 <= show_d <= .50 and
                    show_d - show_a >= .025)
    signals = []
    if start_edge >= .025:
        signals.append("average_st_advantage")
    if time_edge >= .04:
        signals.append("exhibition_time_advantage")
    if not signals:
        return 0., []
    # Do not treat the ordinary sixth boat's 0.05s display-time spread as
    # evidence of a decisive attack. Require two independent pre-race edges,
    # or one clearly large edge confirmed by a legal exhibition start.
    strong_independent = (
        len(signals) >= 2
        or (show_confirm and (start_edge >= .045 or time_edge >= .10))
    )
    if not strong_independent:
        return 0., []
    # Confirmation increases the response marginally; no huge adjustment
    # from one flattering display or raw racer rank.
    pressure = min(1., max(0., start_edge) / .07 * .52 + max(0., time_edge) / .13 * .48)
    if show_confirm:
        signals.append("legal_exhibition_st_confirmation")
        pressure = min(1., pressure * 1.10)
    return round(pressure, 6), signals


def rescore(outcomes: list[dict], racers: list[dict], venue: str,
            captured_at_utc: str, cutoff_at_utc: str, *, exhibition_verified: bool):
    """Produce bounded scenario-only ranking; NEVER changes formal main tickets.

    Return None when fresh six-boat exhibition evidence is unavailable.
    Venue is a grouping dimension for matched forward validation, NOT a
    retrospective venue-specific penalty inferred from recent losses.
    """
    if not exhibition_verified:
        return None
    by_lane, by_course, ranked = _valid_pre_race(
        racers, outcomes, captured_at_utc, cutoff_at_utc)
    inside_lane = by_course[1]
    inside = by_lane[inside_lane]
    threat = {}
    for course in range(2, 7):
        lane = by_course[course]
        intensity, signals = _evidence(by_lane[lane], inside)
        if intensity >= .18:
            threat[lane] = {"course": course, "pressure": intensity,
                            "signals": signals,
                            "inside_defender_lane": inside_lane}
    if not threat:
        return None
    max_pressure = max(x["pressure"] for x in threat.values())
    significant_outer = [x for x in threat.values() if x["course"] >= 4]
    outer_pressure = max((x["pressure"] for x in significant_outer), default=0.)

    adjusted = []
    for combo, score in ranked.items():
        head, second, third = (int(x) for x in combo.split("-"))
        factor = 1.
        # A pressured inside lane is not guaranteed to defend successfully.
        if head == inside_lane:
            factor -= .11 * max_pressure
        # A threatening outside boat can attack successfully, but attack
        # *failure* also opens a separate inside-counter opportunity.
        if head in threat:
            factor += .10 * threat[head]["pressure"]
            follower = by_course.get(threat[head]["course"] + 1)
            if follower in (second, third):
                factor += .025 * threat[head]["pressure"]
            if inside_lane == second:
                factor += .025 * threat[head]["pressure"]
        if outer_pressure > 0 and by_lane[head]["course"] in (2, 3):
            # The attacking boat may run wide. Its neighbours can counter.
            factor += .065 * outer_pressure
        if head != inside_lane and inside_lane not in (second, third):
            factor += .035 * max_pressure
        # The total change remains bounded even with multiple simultaneous
        # threats and is still an uncalibrated relative-score experiment.
        factor = max(.84, min(1.16, factor))
        adjusted.append({"combination": combo, "relative_score": score * factor})
    total = sum(x["relative_score"] for x in adjusted)
    normalized = [{**x, "relative_score": x["relative_score"] / total} for x in adjusted]
    normalized.sort(key=lambda x: (-x["relative_score"], x["combination"]))
    old_head = {i: 0. for i in range(1, 7)}
    new_head = {i: 0. for i in range(1, 7)}
    for key, score in ranked.items():
        old_head[int(key[0])] += score
    for row in normalized:
        new_head[int(row["combination"][0])] += row["relative_score"]
    return {
        "version": VERSION,
        "model_role": "shadow_validation",
        "status": "BOUNDED_HYPOTHESIS_UNCALIBRATED",
        "not_formal": True,
        "result_data_used": False,
        "calibrated": False,
        "no_additional_stake": True,
        "venue": venue,
        "inside_lane": inside_lane,
        "actual_entry": {str(course): by_course[course] for course in range(1, 7)},
        "threats": {str(lane): value for lane, value in sorted(threat.items())},
        "conditional_scenarios": [
            "inside_defends_attack", "outer_attack_succeeds",
            "outer_attack_overruns_inside_counter",
            "inside_displaced_from_top3",
            "actual_course_follower_tracks_attack",
        ],
        "head_marginal_prior": {str(k): round(v, 8) for k, v in old_head.items()},
        "head_marginal_trial": {str(k): round(v, 8) for k, v in new_head.items()},
        "max_pre_normalization_relative_change": .16,
        "same_time_pre_cutoff_input": True,
        "double_counting_risk": "same_ST_exhibition_metrics_already_in_v2.2; forward_A_B_only",
        "outcomes": normalized,
    }
