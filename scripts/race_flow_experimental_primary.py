"""Forward-only, deliberately aggressive BOAT LAB race-flow *experiment*.

This is NOT a calibrated probability or observed 1M manoeuvre. It modifies
NEW exhibition-stage formal research forecasts only after explicit activation
in the caller, with a same-time unaffected control for each race. It does not
read results, payouts or odds and does not force an outside winner without
at least two independent verified pre-cutoff signals.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from itertools import permutations
from math import isfinite
from boat_ai.statistical import digest

VERSION = "race-flow-head-experiment-v1-20261120-uncalibrated"
POLICY = {
    "version": VERSION,
    "min_independent_signals": 2,
    "avg_st_edge_s": 0.018,
    "exhibition_time_edge_s": 0.045,
    "motor_edge_points": 9.0,
    "national_win_rate_edge": 1.0,
    "exhibition_st_confirmation_s": 0.025,
    "relative_first_head_boost": {"2": 2.2, "3": 3.0, "4": 4.0},
    "inside_head_multiplier_2": 0.62,
    "inside_head_multiplier_3plus": 0.48,
    "corner_guard_bonus": 1.15,
    "follower_second_multiplier": 1.30,
    "inside_survival_second_multiplier": 1.22,
    "max_single_outcome_multiplier": 5.25,
    "mode": "explicit_experimental_formal_not_calibrated",
}
POLICY_SHA256 = digest(POLICY)
ALL = {"-".join(map(str, t)) for t in permutations(range(1, 7), 3)}
BLOCKED = {"result", "finish", "actual_finish", "actual_start", "payout",
           "odds", "kimarite", "actual_tactic", "observed_maneuver"}


def _num(value, low, high):
    if type(value) not in (int, float) or not isfinite(value):
        return None
    v = float(value)
    return v if low <= v <= high else None


def _ts(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("naive_time_rejected")
    return t


def _inputs(racers):
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("six_racers_required")
    by_course, lanes = {}, set()
    for boat in racers:
        if not isinstance(boat, dict) or BLOCKED.intersection(boat):
            raise ValueError("postrace_or_invalid_input")
        c, lane = boat.get("course"), boat.get("lane")
        if type(c) is not int or type(lane) is not int or c not in range(1, 7) or lane not in range(1, 7):
            raise ValueError("explicit_course_and_lane_required")
        if c in by_course or lane in lanes:
            raise ValueError("duplicate_course_or_lane")
        by_course[c] = {
            "lane": lane,
            "avg": None if boat.get("average_start_timing_imputed") else _num(boat.get("average_start_timing"), .01, .4),
            "show": _num(boat.get("exhibition_st"), 0, .5),
            "ex": _num(boat.get("exhibition_time"), 5, 10),
            "motor": _num(boat.get("motor_top_2_percent"), 0, 100),
            "win": _num(boat.get("national_win_rate"), 0, 10),
        }
        lanes.add(lane)
    return by_course


def rescore(ranked, racers, *, frozen_at_utc, cutoff_iso_jst, exhibition_verified):
    frozen, cutoff = _ts(frozen_at_utc), _ts(cutoff_iso_jst)
    if frozen >= cutoff - timedelta(minutes=2):
        raise ValueError("late_snapshot_cannot_change_formal")
    if not isinstance(ranked, list) or len(ranked) != 120:
        raise ValueError("canonical_120_required")
    scores = {}
    for r in ranked:
        if not isinstance(r, dict) or BLOCKED.intersection(r):
            raise ValueError("postrace_ranking_input")
        name = r.get("combination")
        score = _num(r.get("score"), 1e-14, 1)
        if name not in ALL or name in scores or score is None:
            raise ValueError("invalid_canonical_ranked")
        scores[name] = score
    if len(scores) != 120 or abs(sum(scores.values()) - 1) > 1e-5:
        raise ValueError("unnormalized_canonical")
    boats = _inputs(racers)
    audit = {
        "version": VERSION, "policy_sha256": POLICY_SHA256,
        "status": "UNVERIFIED_EXHIBITION", "experimental": True,
        "calibrated": False, "trained_coefficient": False, "results_used": False,
        "odds_used": False, "formal_bets_changed": False,
        "frozen_at_utc": frozen_at_utc, "source_complete": False,
        "independent_signals_by_course": {}, "first_head_before": {},
        "first_head_after": {}, "first_head_shift_max": 0.0,
    }
    if not exhibition_verified:
        return [dict(x) for x in ranked], audit
    # Do not create evidence from a missing/F exhibition ST or an unverified
    # inside exhibition time. Other skill/motor/average values may be missing.
    if any(boats[c]["show"] is None or boats[c]["ex"] is None for c in range(1, 7)):
        audit["status"] = "INCOMPLETE_EXHIBITION"
        return [dict(x) for x in ranked], audit
    audit["source_complete"] = True
    inside = boats[1]
    challenges = {}
    for course in range(2, 6):
        a = boats[course]
        signals = []
        if a["avg"] is not None and inside["avg"] is not None and inside["avg"] - a["avg"] >= POLICY["avg_st_edge_s"]:
            signals.append("average_start_advantage")
        if inside["ex"] - a["ex"] >= POLICY["exhibition_time_edge_s"]:
            signals.append("exhibition_speed_advantage")
        if a["motor"] is not None and inside["motor"] is not None and a["motor"] - inside["motor"] >= POLICY["motor_edge_points"]:
            signals.append("motor_advantage")
        if a["win"] is not None and inside["win"] is not None and a["win"] - inside["win"] >= POLICY["national_win_rate_edge"]:
            signals.append("racer_skill_advantage")
        # Exhibition ST is ONE uncertain confirmation, not a standalone
        # independent reason to promote an outside winner.
        show_confirm = inside["show"] - a["show"] >= POLICY["exhibition_st_confirmation_s"]
        audit["independent_signals_by_course"][str(course)] = {
            "lane": a["lane"], "signals": signals,
            "exhibition_st_confirmed": show_confirm,
        }
        if len(signals) < POLICY["min_independent_signals"]:
            continue
        boost = POLICY["relative_first_head_boost"][str(min(len(signals), 4))]
        if show_confirm:
            boost *= 1.12
        if course == 4:
            guard = boats[3]
            if (guard["show"] - a["show"] >= .025
                    and guard["avg"] is not None and a["avg"] is not None
                    and guard["avg"] - a["avg"] >= .012):
                boost *= POLICY["corner_guard_bonus"]
        challenges[course] = min(4.7, boost)
    if not challenges:
        audit["status"] = "NO_TWO_INDEPENDENT_ATTACK_SIGNALS"
        return [dict(x) for x in ranked], audit
    max_signals = max(len(audit["independent_signals_by_course"][str(c)]["signals"]) for c in challenges)
    inside_multiplier = (POLICY["inside_head_multiplier_3plus"] if max_signals >= 3
                         else POLICY["inside_head_multiplier_2"])
    by_lane = {boat["lane"]: course for course, boat in boats.items()}
    modified = {}
    for combo, score in scores.items():
        head, second, third = (int(x) for x in combo.split("-"))
        h, s, t = by_lane[head], by_lane[second], by_lane[third]
        factor = inside_multiplier if h == 1 else challenges.get(h, 1.0)
        if h in challenges and s == 1:
            factor *= POLICY["inside_survival_second_multiplier"]
        if h == 1 and s in challenges:
            factor *= 1.16
        if h == 4 and h in challenges and s == 5:
            follower = boats[5]
            corner = boats[4]
            if (follower["show"] <= corner["show"] + .035
                    and follower["ex"] <= corner["ex"] + .065):
                factor *= POLICY["follower_second_multiplier"]
        if h in challenges and t == 1 and s != 1:
            factor *= 1.09
        modified[combo] = score * min(factor, POLICY["max_single_outcome_multiplier"])
    total = sum(modified.values())
    out = [
        {"combination": combo, "score": value / total}
        for combo, value in modified.items()
    ]
    out.sort(key=lambda row: (-row["score"], row["combination"]))
    for lane in range(1, 7):
        x = str(lane)
        audit["first_head_before"][x] = round(sum(v for k, v in scores.items() if k.startswith(x + "-")), 6)
        audit["first_head_after"][x] = round(sum(r["score"] for r in out if r["combination"].startswith(x + "-")), 6)
    audit["first_head_shift_max"] = round(max(abs(audit["first_head_after"][x] - audit["first_head_before"][x]) for x in audit["first_head_before"]), 6)
    audit["challenging_courses"] = {str(c): {"lane": boats[c]["lane"], "multiplier": round(v, 4)} for c, v in sorted(challenges.items())}
    audit["status"] = "APPLIED_EXPERIMENTAL_UNCALIBRATED"
    audit["formal_bets_changed"] = None  # caller fills this after allocation
    return out, audit
