"""Prospective 2/3-boat first-place challenger. RESEARCH ONLY.

This module never changes formal bets, trained weights, historical snapshots or
returns. It uses same-time six-boat frozen exhibition inputs and explicitly
separates head selection from conditional second/third probabilities.
Thresholds are hypotheses, NOT calibrated winning probabilities.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from itertools import permutations

from boat_ai.statistical import allocate, digest, distributions
from scripts.corner_attack_formal_v1 import rescore as corner_rescore

VERSION = "inner-23-head-challenger-shadow-v0.1"
POLICY = {
    "version": VERSION,
    "min_average_st_edge_s": 0.015,
    "min_exhibition_st_edge_s": 0.025,
    "min_exhibition_time_edge_s": 0.035,
    "min_motor_edge_points": 8.0,
    "min_skill_edge": 0.7,
    "first_head_log_boost": 0.55,
    "role": "research_shadow",
    "calibrated": False,
}
POLICY_SHA256 = digest(POLICY)
COMBOS = {"-".join(map(str, p)) for p in permutations(range(1, 7), 3)}


def _number(value, lo, hi):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value) if lo <= value <= hi else None


def _mass(ranked, lane):
    return sum(row["score"] for row in ranked
               if row["combination"].startswith(str(lane) + "-"))


def evaluate(snapshot: dict, ranked: list[dict], formal_bets: list[dict]) -> dict:
    """Freeze a like-for-like alternative before cutoff; no outcome access."""
    base = {
        "version": VERSION, "policy_sha256": POLICY_SHA256,
        "model_role": "research_shadow", "not_formal": True,
        "formal_tickets_changed": False, "no_additional_stake": True,
        "result_data_used": False, "odds_used": False, "calibrated": False,
        "prospective_improvement_unproven": True,
    }
    if snapshot.get("phase") != "exhibition" or snapshot.get("venue") == "江戸川":
        return {**base, "status": "NOT_ELIGIBLE"}
    try:
        frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
        cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
    except (KeyError, ValueError, TypeError):
        return {**base, "status": "MISSING_FREEZE_PROOF"}
    if frozen.tzinfo is None or cutoff.tzinfo is None or frozen > cutoff - timedelta(minutes=2):
        return {**base, "status": "NOT_SAFELY_FROZEN"}
    origin = snapshot.get("exhibition_origin") or {}
    evidence = snapshot.get("exhibition_input_check") or {}
    if (origin.get("captured_before_cutoff") is not True or
            evidence.get("verified_before_freeze") is not True or
            evidence.get("six_boats_matched") != 6):
        return {**base, "status": "SIX_BOAT_SOURCE_NOT_VERIFIED"}
    racers = snapshot.get("racers")
    if not isinstance(racers, list) or len(racers) != 6 or any(not isinstance(x, dict) for x in racers):
        return {**base, "status": "INVALID_SIX_BOAT_ENTRY"}
    by_lane = {x.get("lane"): x for x in racers}
    by_course = {x.get("course"): x for x in racers}
    if (set(by_lane) != set(range(1, 7)) or
            set(by_course) != set(range(1, 7))):
        return {**base, "status": "INVALID_SIX_BOAT_ENTRY"}
    if (not isinstance(ranked, list) or len(ranked) != 120 or
            {x.get("combination") for x in ranked} != COMBOS or
            any(_number(x.get("score"), 0, 1) is None or x["score"] <= 0 for x in ranked) or
            abs(sum(x["score"] for x in ranked) - 1) > 1e-6):
        return {**base, "status": "INVALID_CANONICAL_RANKING"}
    if (not isinstance(formal_bets, list) or not 4 <= len(formal_bets) <= 20 or
            sum(x.get("virtual_yen", 0) for x in formal_bets) != 50000 or
            len({x.get("combination") for x in formal_bets}) != len(formal_bets)):
        return {**base, "status": "INVALID_FORMAL_CONTROL"}
    inside = by_course[1]
    qualified = []
    for lane in (2, 3):
        contender = by_lane[lane]
        if contender["course"] not in (2, 3):
            continue  # The boat number and actual course are not interchangeable.
        a = (None if inside.get("average_start_timing_imputed")
             else _number(inside.get("average_start_timing"), .01, .40))
        b = (None if contender.get("average_start_timing_imputed")
             else _number(contender.get("average_start_timing"), .01, .40))
        inside_st = _number(inside.get("exhibition_st"), 0, .50)
        other_st = _number(contender.get("exhibition_st"), 0, .50)
        inside_time = _number(inside.get("exhibition_time"), 5, 10)
        other_time = _number(contender.get("exhibition_time"), 5, 10)
        inside_motor = _number(inside.get("motor_top_2_percent"), 0, 100)
        other_motor = _number(contender.get("motor_top_2_percent"), 0, 100)
        inside_skill = _number(inside.get("national_win_rate"), 0, 10)
        other_skill = _number(contender.get("national_win_rate"), 0, 10)
        start = ((a is not None and b is not None
                  and a - b >= POLICY["min_average_st_edge_s"]) or
                 (inside_st is not None and other_st is not None
                  and inside_st - other_st >= POLICY["min_exhibition_st_edge_s"]))
        corroboration = {
            "exhibition_time": (inside_time is not None and other_time is not None
                                and inside_time - other_time >= POLICY["min_exhibition_time_edge_s"]),
            "motor": (inside_motor is not None and other_motor is not None
                      and other_motor - inside_motor >= POLICY["min_motor_edge_points"]),
            "skill": (inside_skill is not None and other_skill is not None
                      and other_skill - inside_skill >= POLICY["min_skill_edge"]),
        }
        # No unconditional lane-2/3 bonus; require independent start + ability evidence.
        if start and any(corroboration.values()):
            qualified.append({
                "lane": lane, "actual_course": contender["course"],
                "average_st_edge_s": round(a-b, 4) if a is not None and b is not None else None,
                "exhibition_st_edge_s": (round(inside_st-other_st, 4)
                                        if inside_st is not None and other_st is not None else None),
                "confirmed_independent_signals": [k for k, v in corroboration.items() if v],
                "scenario_hypothesis": ("course2_inside_pass" if contender["course"] == 2
                                        else "course3_pressure_or_sweep"),
            })
    if not qualified:
        return {**base, "status": "NO_QUALIFIED_2_3_HEAD_CHALLENGER",
                "frozen_at_utc": snapshot["frozen_at_utc"],
                "formal_bets_sha256": digest(formal_bets),
                "source_ranked_sha256": digest(ranked),
                "qualified": []}
    supported = {row["lane"] for row in qualified}
    adjusted = []
    for row in ranked:
        lane = int(row["combination"].split("-")[0])
        weight = math.exp(POLICY["first_head_log_boost"]) if lane in supported else 1.0
        adjusted.append({"combination": row["combination"], "score": row["score"] * weight})
    total = sum(r["score"] for r in adjusted)
    adjusted = sorted(
        ({"combination": r["combination"], "score": r["score"] / total} for r in adjusted),
        key=lambda x: (-x["score"], x["combination"]),
    )
    trial_bets = allocate(adjusted, len(formal_bets), point_free=False, max_points=20)
    formal_signature = sorted((x["combination"], x["virtual_yen"]) for x in formal_bets)
    trial_signature = sorted((x["combination"], x["virtual_yen"]) for x in trial_bets)
    return {
        **base, "status": "QUALIFIED_FORWARD_SHADOW",
        "frozen_at_utc": snapshot["frozen_at_utc"],
        "cutoff_iso_jst": snapshot["cutoff_iso_jst"],
        "venue": snapshot.get("venue"), "race": snapshot.get("race"),
        "qualified": qualified, "policy": POLICY,
        "formal_bets_sha256": digest(formal_bets),
        "source_ranked_sha256": digest(ranked),
        "trial_ranked_sha256": digest(adjusted),
        "trial_bets_sha256": digest(trial_bets),
        "trial_bets": trial_bets, "same_point_count": len(trial_bets) == len(formal_bets),
        "virtual_stake_yen_each": 50000, "same_time_same_input": True,
        "trial_tickets_or_stakes_changed": trial_signature != formal_signature,
        "formal_top_head": int(formal_bets[0]["combination"].split("-")[0]),
        "trial_top_head": int(trial_bets[0]["combination"].split("-")[0]),
        "before_head_mass": {str(n): round(_mass(ranked, n), 6) for n in (1,2,3)},
        "trial_head_mass": {str(n): round(_mass(adjusted, n), 6) for n in (1,2,3)},
    }


def build(snapshot: dict, model: dict) -> dict:
    """Re-evaluate only AFTER six-boat input proof has been frozen by the builder.

    Do not run inside learned_formal.apply: exhibition_input_check is attached
    downstream, after the six-boat input/output checksum comparison.
    """
    proof = snapshot.get("learned_formal") or {}
    if proof.get("model_sha256") != model.get("model_sha256"):
        return {"version": VERSION, "model_role": "research_shadow",
                "not_formal": True, "formal_tickets_changed": False,
                "status": "MODEL_SHA_MISMATCH", "result_data_used": False}
    allowed = ("lane", "course", "national_win_rate",
               "motor_top_2_percent", "average_start_timing",
               "average_start_timing_imputed", "exhibition_time", "exhibition_st")
    safe = {
        "phase": snapshot.get("phase"),
        "racers": [{k: row.get(k) for k in allowed} for row in snapshot["racers"]],
        "weather_used": {k: (snapshot.get("weather_used") or {}).get(k)
                         for k in ("wind_speed", "wave_height")},
    }
    ranked = distributions(safe, model)
    if (snapshot.get("corner_attack_formal_v1") or {}).get("applied") is True:
        ranked, audit = corner_rescore(ranked, snapshot["racers"])
        if audit.get("applied") is not True:
            return {"version": VERSION, "model_role": "research_shadow",
                    "not_formal": True, "formal_tickets_changed": False,
                    "status": "CORNER_PROVENANCE_MISMATCH", "result_data_used": False}
    report = evaluate(snapshot, ranked, snapshot["bets"])
    report["parent_model_sha256"] = model["model_sha256"]
    report["source_formal_bets_sha256"] = digest(snapshot["bets"])
    return report
