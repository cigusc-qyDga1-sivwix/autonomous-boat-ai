"""BOAT LAB: forward-only strong-field / competitive-head diagnostic.

This does NOT modify formal bets. Grade names, odds, and final results must not
create a reason to spread tickets. All relative head shares are uncalibrated.
Thresholds are research heuristics pending pre-cutoff prospective validation.
"""
from __future__ import annotations

from math import isfinite

VERSION = "strong-field-parity-diagnostic-v0.2-head-exposure-untrained"
MIN_STRONG_RATE = 6.0
MAX_TOP_FOUR_RATE_SPREAD = 1.5
MAX_HEAD1_MASS = 0.45
MAX_TOP_TWO_GAP = 0.10


def analyze(racers: list[dict], head_shares: list[dict], formal_bets: list[dict],
            *, phase: str, grade_context: dict | None = None) -> dict:
    """Separate 'strong field' from 'uncertain winner'; identify head coverage gaps.

    National rate is a *proxy* for pre-race ability, not a course-adjusted
    probability. Head shares come from the already-frozen 120-combination model
    and are similarly not calibrated probabilities.
    """
    report = {
        "version": VERSION,
        "status": "INSUFFICIENT_EVIDENCE",
        "model_role": "pre_cutoff_risk_diagnostic",
        "not_formal_model": True,
        "changes_bets": False,
        "changes_stake": False,
        "odds_used": False,
        "results_used": False,
        "calibrated": False,
        "phase": phase,
        "grade": (grade_context or {}).get("grade")
                 if (grade_context or {}).get("status") == "SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK"
                 else None,
        "grade_not_used_as_eligibility": True,
    }
    if phase not in ("baseline", "exhibition"):
        return report
    if (not isinstance(racers, list) or len(racers) != 6
            or not isinstance(head_shares, list) or len(head_shares) != 6
            or not isinstance(formal_bets, list) or not formal_bets):
        return report
    strengths, observed_lanes, courses = [], set(), set()
    for racer in racers:
        if not isinstance(racer, dict):
            return report
        lane, course, value = (racer.get("lane"), racer.get("course"),
                               racer.get("national_win_rate"))
        if (type(lane) is not int or lane not in range(1, 7)
                or lane in observed_lanes or type(course) is not int
                or course not in range(1, 7) or course in courses
                or type(value) not in (float, int)
                or not isfinite(value) or not 0 <= value <= 10):
            return report
        observed_lanes.add(lane)
        courses.add(course)
        strengths.append((lane, float(value)))
    masses = {}
    for item in head_shares:
        if not isinstance(item, dict):
            return report
        lane, score = item.get("lane"), item.get("relative_share")
        if (type(lane) is not int or lane not in range(1, 7)
                or lane in masses or type(score) not in (float, int)
                or not isfinite(score) or not 0 <= score <= 1):
            return report
        masses[lane] = float(score)
    if set(masses) != observed_lanes or abs(sum(masses.values()) - 1) > 0.01:
        return report
    heads_bought = set()
    for bet in formal_bets:
        name = bet.get("combination") if isinstance(bet, dict) else None
        parts = name.split("-") if isinstance(name, str) else []
        if (len(parts) != 3 or len(set(parts)) != 3
                or any(part not in "123456" for part in parts)):
            return report
        heads_bought.add(int(parts[0]))
    # Course 1 is not necessarily lane 1 after a verified entry change.
    inside_lane = next(racer["lane"] for racer in racers if racer["course"] == 1)
    if any(type(bet.get("virtual_yen")) is not int or bet["virtual_yen"] <= 0
           for bet in formal_bets):
        return report
    total_stake = sum(bet["virtual_yen"] for bet in formal_bets)
    inside_stake = sum(bet["virtual_yen"] for bet in formal_bets
                       if bet["combination"].split("-")[0] == str(inside_lane))
    inside_stake_share = inside_stake / total_stake
    modeled_inside_share = masses[inside_lane]
    values = sorted((rate for _, rate in strengths), reverse=True)
    top = sorted(masses.items(), key=lambda kv: (-kv[1], kv[0]))
    strong_lanes = [lane for lane, rate in strengths if rate >= MIN_STRONG_RATE]
    strong_field = (len(strong_lanes) >= 4 and
                    values[0] - values[3] <= MAX_TOP_FOUR_RATE_SPREAD)
    close_heads = (top[0][1] <= MAX_HEAD1_MASS and
                   top[0][1] - top[1][1] <= MAX_TOP_TWO_GAP)
    contenders = [lane for lane, share in top
                  if share >= max(0.12, top[0][1] * 0.7)]
    missed = [lane for lane in contenders if lane not in heads_bought]
    # The risk case is NOT limited to strong fields. The model can have
    # materially close head contenders even when national rates are ordinary.
    uncovered_close_heads = bool(close_heads and missed)
    # A relative mass is not a calibrated win probability. This is an
    # untrained exposure alert, not a direction to reallocate formal wagers.
    inside_overexposure = bool(
        phase == "exhibition" and inside_stake_share >= 0.75
        and modeled_inside_share <= 0.55
        and inside_stake_share - modeled_inside_share >= 0.20
    )
    risk_flags = []
    if uncovered_close_heads:
        risk_flags.append("MODEL_CLOSE_HEAD_UNCOVERED")
    if inside_overexposure:
        risk_flags.append("INSIDE_TICKET_CONCENTRATION")
    if strong_field and close_heads:
        status = "STRONG_FIELD_CLOSE_HEADS"
    elif strong_field:
        status = "STRONG_FIELD_HEAD_SEPARATED"
    elif close_heads:
        status = "MODEL_CLOSE_HEADS_NOT_STRONG_FIELD"
    else:
        status = "NO_STRONG_FIELD_PARITY_SIGNAL"
    report.update({
        "status": status,
        "strong_field": strong_field,
        "modeled_heads_close": close_heads,
        "strong_racers_count": len(strong_lanes),
        "strong_racers_lanes": sorted(strong_lanes),
        "national_win_rate_top_four_spread": round(values[0] - values[3], 4),
        "national_win_rate_range": [round(values[-1], 4), round(values[0], 4)],
        "head_marginal_top_two": [
            {"lane": lane, "relative_share": round(score, 6)}
            for lane, score in top[:2]
        ],
        "head_gap": round(top[0][1] - top[1][1], 6),
        "head_candidates_from_uncalibrated_mass": contenders,
        "head_candidates_absent_from_tickets": missed,
        "head_coverage_warning": uncovered_close_heads,
        "inside_course_lane": inside_lane,
        "inside_course_modeled_head_share": round(modeled_inside_share, 6),
        "inside_course_ticket_stake_share": round(inside_stake_share, 6),
        "inside_course_stake_yen": inside_stake,
        "ticket_stake_yen": total_stake,
        "inside_allocation_minus_model_mass": round(
            inside_stake_share - modeled_inside_share, 6),
        "inside_overexposure_research_warning": inside_overexposure,
        "risk_flags": risk_flags,
        "risk_severity": "REVIEW" if risk_flags else "NONE",
        "risk_assessment_before_result": True,
        "ticket_heads_present": sorted(heads_bought),
        "classification_note": (
            "Multiple highly rated entrants with close modeled 1st-place shares; "
            "review 1M tactics and unresolved head coverage."
            if strong_field and close_heads else
            "Modeled 1st-place contenders are close; review uncovered heads."
            if uncovered_close_heads else
            "Inspect excessive course-1 ticket concentration against model mass."
            if inside_overexposure else
            "No demonstrated reason to widen or alter formal tickets."
        ),
        "thresholds_are_research_only": {
            "strong_rate_min": MIN_STRONG_RATE,
            "top_four_rate_spread_max": MAX_TOP_FOUR_RATE_SPREAD,
            "leading_head_mass_max": MAX_HEAD1_MASS,
            "head_gap_max": MAX_TOP_TWO_GAP,
            "candidate_mass_fraction_of_leader": 0.7,
            "inside_ticket_share_min": 0.75,
            "inside_modeled_share_max": 0.55,
            "inside_ticket_minus_model_min": 0.20,
        },
        "recommendation": (
            "WATCH_CONTESTED_HEAD" if strong_field and close_heads else
            "WATCH_HEAD_RISK" if risk_flags else "KEEP_DEFAULT"
        ),
        "inference_limit": (
            "Neither a G1 title nor an equal national win rate proves actual "
            "race parity; no probabilistic calibration or profit edge measured."
        ),
    })
    return report
