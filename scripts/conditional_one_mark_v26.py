"""Forward-only v2.6 conditional second/third ranking; no hindsight or blanket lane-1 penalty.

Evidence-guarded bounded reranking of SAME canonical 120 outcomes. Every head's
marginal mass is preserved exactly: only its 2nd/3rd conditional distribution
can change. Requires pre-cutoff six-boat source. Estimates are uncalibrated.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from math import isfinite
from itertools import permutations

VERSION = "conditional-one-mark-v2.6-forward-untrained"
ALL = {"-".join(p) for p in permutations("123456", 3)}
POST = {"finish", "result", "actual_finish", "actual_start", "odds", "payout", "kimarite"}


def _number(x, low, high):
    return float(x) if type(x) in (float, int) and isfinite(x) and low <= x <= high else None


def rescore(ranked, racers, *, frozen_at_utc, cutoff_at_utc):
    """Return (normalized canonical ranked, audit metadata) without changing sources."""
    frozen = datetime.fromisoformat(frozen_at_utc.replace("Z", "+00:00"))
    cutoff = datetime.fromisoformat(cutoff_at_utc.replace("Z", "+00:00"))
    if (frozen.tzinfo is None or cutoff.tzinfo is None
            or not frozen <= cutoff - timedelta(minutes=2)):
        raise ValueError("late_or_non_timezone_frozen_forecast")
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("missing_six_boats")
    if not isinstance(ranked, list) or len(ranked) != 120:
        raise ValueError("missing_canonical_120")
    scores = {}
    for row in ranked:
        if not isinstance(row, dict) or POST.intersection(row):
            raise ValueError("forbidden_score_source")
        combo = row.get("combination")
        score = _number(row.get("relative_score"), 1e-12, 1)
        if combo not in ALL or combo in scores or score is None:
            raise ValueError("invalid_120_scores")
        scores[combo] = score
    if set(scores) != ALL or abs(sum(scores.values()) - 1) > 1e-5:
        raise ValueError("invalid_canonical_normalization")
    boats = {}
    lanes = set()
    for boat in racers:
        if not isinstance(boat, dict) or POST.intersection(boat):
            raise ValueError("forbidden_racer_source")
        c, lane = boat.get("course"), boat.get("lane")
        if type(c) is not int or type(lane) is not int or c not in range(1, 7) or lane not in range(1, 7):
            raise ValueError("invalid_actual_course")
        if c in boats or lane in lanes:
            raise ValueError("duplicate_actual_course")
        boats[c] = boat
        lanes.add(lane)
    if set(boats) != set(range(1, 7)) or lanes != set(range(1, 7)):
        raise ValueError("missing_actual_entry")
    def data(boat):
        original = boat.get("original_exhibition")
        if not isinstance(original, dict):
            return None
        avg = None if boat.get("average_start_timing_imputed") else _number(boat.get("average_start_timing"), .01, .40)
        st = _number(boat.get("exhibition_st"), 0, .45)
        turn = _number(original.get("turn_time"), 4, 15)
        exhibit = _number(boat.get("exhibition_time"), 5, 10)
        if None in (avg, st, turn, exhibit):
            return None
        return {"avg": avg, "st": st, "turn": turn, "exhibit": exhibit, "lane": boat["lane"]}
    valid = {c: data(b) for c, b in boats.items()}
    audit = {"version": VERSION, "model_role": "formal_primary",
             "status": "NO_COMPLETE_PRE_CUTOFF_SIX_BOAT_EVIDENCE",
             "generated_pre_cutoff": True, "result_data_used": False, "odds_used": False,
             "calibrated": False, "no_additional_stake": True,
             "frozen_at_utc": frozen_at_utc,
             "head_marginals_preserved": True, "adjusted_outcome_count": 0,
             "evidence": [], "max_candidate_multiplier": 1.25}
    if any(v is None for v in valid.values()):
        return [dict(x) for x in ranked], audit

    inside = valid[1]
    qualified = {}
    for course in (2, 3, 4, 5, 6):
        attacker = valid[course]
        st_gap = inside["avg"] - attacker["avg"]
        turn_gap = inside["turn"] - attacker["turn"]
        if st_gap >= .018 and turn_gap >= .025 and attacker["exhibit"] <= inside["exhibit"] + .04:
            qualified[course] = True
            audit["evidence"].append({"course": course, "lane": attacker["lane"],
                                     "avg_st_edge_sec": round(st_gap, 4),
                                     "turn_time_edge_sec": round(turn_gap, 4)})
    if not qualified:
        audit["status"] = "NO_INDEPENDENT_ATTACKER_EVIDENCE"
        return [dict(x) for x in ranked], audit

    lane_courses = {v["lane"]: c for c, v in valid.items()}
    after = {}
    adjusted = 0
    for combo, score in scores.items():
        head, second, third = (lane_courses[int(x)] for x in combo.split("-"))
        attacker, runner = valid[head], valid[second]
        multiplier = 1.
        # Inside wins but a credible outer boat retains enough turn to move to 2nd.
        if head == 1 and second >= 4 and second in qualified:
            multiplier *= 1.20
        # A real-course outer attack may bring the next outer boat along.
        if (head >= 3 and head in qualified and second == head + 1
                and runner["avg"] <= attacker["avg"] + .035
                and runner["turn"] <= attacker["turn"] + .09
                and runner["exhibit"] <= attacker["exhibit"] + .07):
            multiplier *= 1.22
            if third == 1 and inside["turn"] <= attacker["turn"] + .15:
                multiplier *= 1.08  # inner survivor in 3rd, not simultaneous 2nd
        # If the inside was passed but remains competitive, preserve a second-place path.
        if (head >= 2 and head in qualified and second == 1
                and inside["turn"] <= attacker["turn"] + .15):
            multiplier *= 1.10
        # A strong outside second may drag another outside boat into third.
        if (head == 1 and second >= 4 and second in qualified
                and third == second + 1 and third <= 6
                and valid[third]["turn"] <= runner["turn"] + .09):
            multiplier *= 1.06
        multiplier = min(1.25, multiplier)
        after[combo] = score * multiplier
        adjusted += multiplier != 1.
    if not adjusted:
        audit["status"] = "NO_CONDITIONAL_PAIR_SUPPORTED"
        return [dict(x) for x in ranked], audit

    # Preserve each existing 1st-place marginal exactly, so this revision
    # does not blindly suppress course 1 or elevate outside winners.
    for course in range(1, 7):
        lane = str(valid[course]["lane"])
        combos = [k for k in scores if k.split("-")[0] == lane]
        before_total = sum(scores[k] for k in combos)
        after_total = sum(after[k] for k in combos)
        for combo in combos:
            after[combo] *= before_total / after_total
    total = sum(after.values())
    # The second normalization only controls floating point drift.
    after = {k: v / total for k, v in after.items()}
    out = [{"combination": k, "relative_score": after[k]} for k in sorted(after, key=lambda x: (-after[x], x))]
    audit.update({"status": "APPLIED_UNCALIBRATED", "adjusted_outcome_count": adjusted,
                  "changed_top12": [x["combination"] for x in out[:12]] !=
                      [x["combination"] for x in sorted(ranked, key=lambda x: (-x["relative_score"], x["combination"]))[:12]],
                  "head_marginal_max_error": max(abs(
                      sum(after[k] for k in scores if k.split("-")[0] == lane) -
                      sum(scores[k] for k in scores if k.split("-")[0] == lane)
                  ) for lane in "123456")})
    return out, audit
