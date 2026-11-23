"""2026-11-24 onward: strictly pre-cutoff 5/6-course head scenario SHADOW.

This research-only alternative never replaces formal tickets or stakes. It is
frozen inside the original SHA-addressed race snapshot, so post-race payouts
cannot influence its picks. Thresholds are hypotheses, NOT calibrated edges.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from itertools import permutations
import math

from boat_ai.statistical import digest

VERSION = "outside-head-5-6-precutoff-shadow-v0.1"
ACTIVATE = date(2026, 11, 24)
CANONICAL = {"-".join(map(str, x)) for x in permutations(range(1, 7), 3)}
FORBIDDEN = {"result", "finish", "actual_finish", "actual_start", "payout",
             "odds", "kimarite", "observed_maneuver", "official_pay"}
THRESHOLDS = {
    "min_exhibition_st_advantage_to_inside_sec": 0.03,
    "min_course6_exhibition_st_advantage_to_course5_sec": 0.015,
    "max_average_st_disadvantage_to_inside_sec": 0.02,
    "max_exhibition_time_disadvantage_to_inside_sec": 0.04,
    "max_motor_2rate_disadvantage_pct_points": 10.0,
    "max_5_st_lag_behind_4_sec": 0.025,
    "max_5_time_lag_behind_4_sec": 0.06,
    "min_candidate_score_as_fraction_of_replaced": 0.45,
    "protected_formal_top_picks": 4,
}
POLICY_SHA256 = digest({"version": VERSION, **THRESHOLDS})


def _number(value, low, high):
    if type(value) not in (float, int):
        return None
    if not math.isfinite(value) or not low <= value <= high:
        return None
    return float(value)


def _sig(bets):
    return sorted((b["combination"], b["virtual_yen"]) for b in bets)


def build(snapshot: dict, ranked: list[dict]) -> dict:
    """Freeze one evidence-gated 5/6-head alternative at equal points and 50k.

    The formal tickets are read-only. Return status/reasons even if no swap is
    justified; no result or payout inputs are used, and no retrospective runs.
    """
    base = {"version": VERSION, "policy_sha256": POLICY_SHA256,
            "model_role": "research_shadow", "not_formal": True,
            "formal_tickets_changed": False, "result_data_used": False,
            "odds_used": False, "calibrated": False,
            "no_historical_rewrite": True, "actual_purchase": False,
            "same_budget_yen": 50000}
    if not isinstance(snapshot, dict) or FORBIDDEN.intersection(snapshot):
        return {**base, "status": "REJECTED_POSTRACE_INPUT"}
    try:
        frozen = datetime.fromisoformat(snapshot["frozen_at_utc"].replace("Z", "+00:00"))
        cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, TypeError, ValueError):
        return {**base, "status": "INVALID_FREEZE_PROVENANCE"}
    if (frozen.tzinfo is None or cutoff.tzinfo is None or
            cutoff.date() < ACTIVATE or
            frozen >= cutoff - timedelta(minutes=2) or frozen > cutoff):
        return {**base, "status": "NOT_PROSPECTIVELY_ELIGIBLE"}
    if (snapshot.get("phase") != "exhibition"
            or (snapshot.get("exhibition_origin") or {}).get("captured_before_cutoff") is not True):
        return {**base, "status": "NO_PRE_CUTOFF_EXHIBITION"}
    racers = snapshot.get("racers")
    if not isinstance(racers, list) or len(racers) != 6:
        return {**base, "status": "INVALID_SIX_BOAT_INPUT"}
    by_course, lanes = {}, set()
    for racer in racers:
        if not isinstance(racer, dict) or FORBIDDEN.intersection(racer):
            return {**base, "status": "INVALID_OR_POSTRACE_RACER"}
        c, lane = racer.get("course"), racer.get("lane")
        if (type(c) is not int or type(lane) is not int or
                c not in range(1, 7) or lane not in range(1, 7) or
                c in by_course or lane in lanes):
            return {**base, "status": "INVALID_SIX_BOAT_ENTRY"}
        lanes.add(lane)
        by_course[c] = racer
    if set(by_course) != set(range(1, 7)) or lanes != set(range(1, 7)):
        return {**base, "status": "INVALID_SIX_BOAT_ENTRY"}
    def evidence(r):
        if r.get("average_start_timing_imputed") is True:
            return None
        keys = (("exhibition_st", 0, 0.45), ("exhibition_time", 5, 10),
                ("average_start_timing", .01, .40), ("motor_top_2_percent", 0, 100))
        values = {key: _number(r.get(key), low, high) for key, low, high in keys}
        return values if all(v is not None for v in values.values()) else None
    values = {c: evidence(r) for c, r in by_course.items()}
    if any(v is None for v in values.values()):
        return {**base, "status": "INCOMPLETE_OR_IMPUTED_EXHIBITION"}
    if not isinstance(ranked, list) or len(ranked) != 120:
        return {**base, "status": "INVALID_RANKED_OUTCOMES"}
    scores = {}
    for row in ranked:
        if not isinstance(row, dict) or FORBIDDEN.intersection(row):
            return {**base, "status": "INVALID_RANKED_OUTCOMES"}
        k, score = row.get("combination"), row.get("score")
        if k not in CANONICAL or k in scores or _number(score, 1e-15, 1) is None:
            return {**base, "status": "INVALID_RANKED_OUTCOMES"}
        scores[k] = float(score)
    if set(scores) != CANONICAL or abs(sum(scores.values()) - 1.0) > 0.0001:
        return {**base, "status": "INVALID_RANKED_OUTCOMES"}
    control = snapshot.get("bets")
    if (not isinstance(control, list) or not 5 <= len(control) <= 20
            or sum(b.get("virtual_yen", 0) for b in control if isinstance(b, dict)) != 50000):
        return {**base, "status": "INVALID_FORMAL_CONTROL"}
    if (any(not isinstance(b, dict) or b.get("combination") not in scores
            or type(b.get("virtual_yen")) is not int or b["virtual_yen"] < 1000
            or b["virtual_yen"] % 1000 for b in control)
            or len({b["combination"] for b in control}) != len(control)):
        return {**base, "status": "INVALID_FORMAL_CONTROL"}

    inside, corner, course5 = values[1], values[4], values[5]
    supported = []
    for course in (5, 6):
        outer = values[course]
        if not (
            inside["exhibition_st"] - outer["exhibition_st"] >=
                THRESHOLDS["min_exhibition_st_advantage_to_inside_sec"]
            and outer["average_start_timing"] - inside["average_start_timing"] <=
                THRESHOLDS["max_average_st_disadvantage_to_inside_sec"]
            and outer["exhibition_time"] - inside["exhibition_time"] <=
                THRESHOLDS["max_exhibition_time_disadvantage_to_inside_sec"]
            and inside["motor_top_2_percent"] - outer["motor_top_2_percent"] <=
                THRESHOLDS["max_motor_2rate_disadvantage_pct_points"]):
            continue
        # 5 follows 4's attack; 6 requires an opening past course 5.
        if course == 5 and not (
            outer["exhibition_st"] - corner["exhibition_st"] <=
                THRESHOLDS["max_5_st_lag_behind_4_sec"]
            and outer["exhibition_time"] - corner["exhibition_time"] <=
                THRESHOLDS["max_5_time_lag_behind_4_sec"]):
            continue
        if course == 6 and not (
            course5["exhibition_st"] - outer["exhibition_st"] >=
                THRESHOLDS["min_course6_exhibition_st_advantage_to_course5_sec"]):
            continue
        supported.append({"course": course, "lane": by_course[course]["lane"],
                          "exhibition_st_advantage_to_inside_s":
                              round(inside["exhibition_st"] - outer["exhibition_st"], 3),
                          "average_st_advantage_to_inside_s":
                              round(inside["average_start_timing"] - outer["average_start_timing"], 3),
                          "exhibition_time_advantage_to_inside_s":
                              round(inside["exhibition_time"] - outer["exhibition_time"], 3)})
    meta = {**base, "frozen_at_utc": snapshot["frozen_at_utc"],
            "cutoff_iso_jst": snapshot["cutoff_iso_jst"],
            "control_bets_sha256": digest(control),
            "control_bets": control,
            "source_input_sha256": digest([
                {k: r.get(k) for k in ("lane", "course", "exhibition_st",
                    "exhibition_time", "average_start_timing",
                    "average_start_timing_imputed", "motor_top_2_percent")}
                for r in racers]),
            "supported_outer_1st_signals": supported,
            "hypothesis": "5-course corner follow / 6-course overtakes 5: uncalibrated"}
    if not supported:
        return {**meta, "status": "NO_SUPPORTED_OUTSIDE_HEAD"}
    formal_combos = {b["combination"] for b in control}
    alternatives = []
    for signal in supported:
        course = signal["course"]
        head = str(signal["lane"])
        # A 5/6 head may leave the inside second, or bring a genuine outside
        # follower. Rank by the *pre-cutoff* model's conditional score.
        second_lanes = {by_course[1]["lane"]}
        if course == 5:
            follower = values[6]
            if (follower["exhibition_st"] <= values[5]["exhibition_st"] + .03
                    and follower["exhibition_time"] <= values[5]["exhibition_time"] + .07):
                second_lanes.add(by_course[6]["lane"])
        if course == 6:
            second_lanes.add(by_course[5]["lane"])
        for combo, score in scores.items():
            h, s, _ = (int(v) for v in combo.split("-"))
            if h == int(head) and s in second_lanes and combo not in formal_combos:
                alternatives.append((score, combo, course))
    if not alternatives:
        return {**meta, "status": "ALREADY_COVERED_OR_NO_CONDITIONAL_PAIR"}
    alternatives.sort(key=lambda x: (-x[0], x[1]))
    pair_counts = Counter("-".join(b["combination"].split("-")[:2]) for b in control)
    for candidate_score, candidate, course in alternatives:
        for i in range(len(control) - 1, THRESHOLDS["protected_formal_top_picks"] - 1, -1):
            victim = control[i]
            victim_combo = victim["combination"]
            victim_pair = "-".join(victim_combo.split("-")[:2])
            if pair_counts[victim_pair] <= 1:
                continue  # Preserve every existing head->second scenario.
            if candidate_score < scores[victim_combo] * THRESHOLDS[
                    "min_candidate_score_as_fraction_of_replaced"]:
                continue
            alternative_bets = [dict(b) for b in control]
            alternative_bets[i] = {
                "combination": candidate,
                "virtual_yen": victim["virtual_yen"],
                "relative_score": candidate_score,
            }
            if (_sig(control) == _sig(alternative_bets)
                    or len({b["combination"] for b in alternative_bets}) != len(control)
                    or sum(b["virtual_yen"] for b in alternative_bets) != 50000):
                raise ValueError("shadow_swap_budget_or_uniqueness_broken")
            return {**meta, "status": "PRE_CUTOFF_SHADOW_SWAP_FROZEN",
                    "replacement": {"added": candidate, "removed": victim_combo,
                                    "outside_course": course},
                    "shadow_alternative_bets": alternative_bets,
                    "shadow_bets_sha256": digest(alternative_bets),
                    "same_point_count": True, "same_virtual_budget_yen": 50000,
                    "actual_ticket_change": True,
                    "no_proven_performance_gain": True}
    return {**meta, "status": "NO_SAFE_EQUAL_POINT_REPLACEMENT"}
