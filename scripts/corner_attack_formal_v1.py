"""Conservative, forward-only 3-course guard / 4-course corner attack overlay.

This is an explicitly provisional heuristic, NOT a learned probability.
Only the six pre-cutoff exhibition inputs already present in a forecast are
used. Retrospective outcome/cohort data MUST NOT enter live inference.
"""
from __future__ import annotations

from collections import defaultdict
import math

from boat_ai.statistical import digest

POLICY = {
    "version": "corner-guard-forward-v0.1",
    "corner_course": 4,
    "guard_course": 3,
    "follower_course": 5,
    "min_corner_exhibition_st_lead_s": 0.03,
    "max_corner_exhibition_time_deficit_s": 0.03,
    "max_corner_average_st_deficit_s": 0.025,
    "max_follower_exhibition_st_lag_s": 0.025,
    "max_follower_exhibition_time_deficit_s": 0.05,
    "max_follower_average_st_deficit_s": 0.03,
    "first_log_boost": 0.04,
    "follower_second_log_boost": 0.025,
    "training_status": "hypothesis_not_calibrated",
}
POLICY_SHA256 = digest(POLICY)


def _numeric(value, low, high):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return value if math.isfinite(value) and low <= value <= high else None


def _inputs(racers):
    """Actual course, not lane 3/4/5, determines the corner/guard comparison."""
    if not isinstance(racers, list) or len(racers) != 6:
        return None
    courses = {}
    for row in racers:
        if not isinstance(row, dict):
            return None
        course, lane = row.get("course"), row.get("lane")
        if type(course) is not int or type(lane) is not int or not 1 <= lane <= 6:
            return None
        if course in courses:
            return None
        courses[course] = row
    if set(courses) != set(range(1, 7)):
        return None
    for course in (3, 4):
        row = courses[course]
        if row.get("average_start_timing_imputed") is True:
            return None
        if any(_numeric(row.get(field), lo, hi) is None for field, lo, hi in (
            ("exhibition_st", 0, 0.40),
            ("exhibition_time", 6, 9),
            ("average_start_timing", 0.05, 0.40),
        )):
            return None
    return courses


def rescore(ranked: list[dict], racers: list[dict]) -> tuple[list[dict], dict]:
    """Boost a verified corner attack and its plausible 5-course follower.

    Preserve the conditional third-place distribution. The first-head mass
    and conditional second-place mass are each separately normalized; never
    add or drop ticket combinations.
    """
    audit = {
        "version": POLICY["version"], "policy_sha256": POLICY_SHA256,
        "formal_component": False, "applied": False,
        "trained_coefficient": False, "calibrated": False,
        "result_data_used": False, "odds_used": False,
        "prospective_accuracy_improvement_unproven": True,
    }
    courses = _inputs(racers)
    if courses is None:
        return ranked, {**audit, "reason": "incomplete_or_imputed_exhibition"}
    guard, corner = courses[3], courses[4]
    gap = float(guard["exhibition_st"]) - float(corner["exhibition_st"])
    if not (
        gap >= POLICY["min_corner_exhibition_st_lead_s"]
        and float(corner["exhibition_time"]) - float(guard["exhibition_time"])
            <= POLICY["max_corner_exhibition_time_deficit_s"]
        and float(corner["average_start_timing"]) - float(guard["average_start_timing"])
            <= POLICY["max_corner_average_st_deficit_s"]
    ):
        return ranked, {**audit, "reason": "no_verified_corner_attack_signal",
                        "corner_minus_guard_exhibition_st_s": round(-gap, 4)}

    follower = courses[5]
    good_follower = (
        follower.get("average_start_timing_imputed") is not True
        and all(_numeric(follower.get(field), lo, hi) is not None
                for field, lo, hi in (
                    ("exhibition_st", 0, .40),
                    ("exhibition_time", 6, 9),
                    ("average_start_timing", .05, .40)))
        and float(follower["exhibition_st"]) - float(corner["exhibition_st"])
            <= POLICY["max_follower_exhibition_st_lag_s"]
        and float(follower["exhibition_time"]) - float(corner["exhibition_time"])
            <= POLICY["max_follower_exhibition_time_deficit_s"]
        and float(follower["average_start_timing"]) - float(corner["average_start_timing"])
            <= POLICY["max_follower_average_st_deficit_s"]
    )
    corner_lane, follower_lane = corner["lane"], follower["lane"]
    first_mass = defaultdict(float)
    pair_mass = defaultdict(float)
    parsed = []
    if len(ranked) != 120:
        return ranked, {**audit, "reason": "noncanonical_distribution"}
    for row in ranked:
        try:
            triple = tuple(int(x) for x in row["combination"].split("-"))
            score = float(row["score"])
        except (ValueError, TypeError, AttributeError, KeyError):
            return ranked, {**audit, "reason": "invalid_distribution"}
        if (len(triple) != 3 or len(set(triple)) != 3
                or not all(1 <= n <= 6 for n in triple)
                or not math.isfinite(score) or score <= 0):
            return ranked, {**audit, "reason": "invalid_distribution"}
        parsed.append((row["combination"], triple, score))
        first_mass[triple[0]] += score
        pair_mass[triple[:2]] += score
    if (len({t for _, t, _ in parsed}) != 120
            or first_mass[corner_lane] <= 0):
        return ranked, {**audit, "reason": "invalid_distribution"}

    first_factor = math.exp(POLICY["first_log_boost"])
    follower_factor = math.exp(POLICY["follower_second_log_boost"]) if good_follower else 1.0
    total = sum(first_mass.values())
    head_normalizer = (total + (first_factor - 1) * first_mass[corner_lane]) / total
    second_normalizer = (
        1 + (follower_factor - 1) *
        pair_mass.get((corner_lane, follower_lane), 0) / first_mass[corner_lane]
    )
    adjusted = []
    for combination, (h, s, t), score in parsed:
        updated = score * (first_factor if h == corner_lane else 1) / head_normalizer
        if h == corner_lane:
            updated *= (follower_factor if s == follower_lane else 1) / second_normalizer
        adjusted.append({"combination": combination, "score": updated})
    adjusted.sort(key=lambda r: (-r["score"], r["combination"]))
    audit.update({
        "applied": True, "formal_component": True,
        "reason": "corner_exhibition_st_and_speed_vs_guard_verified",
        "corner_course": 4, "guard_course": 3,
        "corner_lane": corner_lane, "guard_lane": guard["lane"],
        "follower_course": 5, "follower_lane": follower_lane,
        "follower_second_adjusted": bool(good_follower),
        "corner_st_lead_s": round(gap, 4),
        "max_first_log_boost": POLICY["first_log_boost"],
        "max_follower_second_log_boost": (
            POLICY["follower_second_log_boost"] if good_follower else 0),
        "input_sha256": digest({
            "courses": [{k: r.get(k) for k in (
                "lane", "course", "exhibition_st", "exhibition_time",
                "average_start_timing", "average_start_timing_imputed")}
                for _, r in sorted(courses.items())],
            "policy_sha256": POLICY_SHA256,
        }),
        "third_place_conditional_distribution_preserved": True,
        "no_extra_tickets": True,
    })
    return adjusted, audit
