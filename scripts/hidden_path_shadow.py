"""Independent pre-cutoff hidden-path research: alternative 1M outcomes.

Model hypotheses, NOT observed maneuvers, calibrated probabilities, or formal bets.
The module does not access results, odds or payouts and never changes formal tickets.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from itertools import permutations
from math import isfinite
from collections import Counter

try:
    from .justified_main_points import justified_stakes
except ImportError:
    from justified_main_points import justified_stakes

VERSION = "hidden-1m-counterfactual-shadow-v0.1"
COMBOS = {"-".join(p) for p in permutations("123456", 3)}
PROHIBITED = {"result", "finish", "actual_finish", "actual_start", "kimarite", "payout", "odds"}

def _n(v, lo, hi):
    return float(v) if type(v) in (int, float) and isfinite(v) and lo <= v <= hi else None

def _turn(r):
    return _n((r.get("original_exhibition") or {}).get("turn_time"), 4, 15)

def _prepare(bets, ranked, racers, frozen, cutoff):
    a, b = datetime.fromisoformat(frozen), datetime.fromisoformat(cutoff)
    if a.tzinfo is None or b.tzinfo is None or a > b - timedelta(minutes=2):
        raise ValueError("not_safe_pre_cutoff")
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("invalid_six_boat_source")
    by_course, lanes = {}, set()
    for r in racers:
        if not isinstance(r, dict) or PROHIBITED.intersection(r):
            raise ValueError("postrace_or_bad_racer")
        lane, course = r.get("lane"), r.get("course")
        if type(lane) is not int or type(course) is not int or not 1 <= lane <= 6 or not 1 <= course <= 6:
            raise ValueError("bad_actual_course")
        if lane in lanes or course in by_course:
            raise ValueError("duplicate_actual_course")
        if _n(r.get("exhibition_time"), 5, 10) is None or _n(r.get("exhibition_st"), -0.5, 0.5) is None:
            raise ValueError("incomplete_exhibition")
        lanes.add(lane)
        by_course[course] = r
    if set(by_course) != set(range(1, 7)) or lanes != set(range(1, 7)):
        raise ValueError("incomplete_actual_entry")
    if not isinstance(ranked, list) or len(ranked) != 120:
        raise ValueError("invalid_120_outcomes")
    scores = {}
    for x in ranked:
        if not isinstance(x, dict) or PROHIBITED.intersection(x):
            raise ValueError("postrace_or_bad_outcome")
        k = x.get("combination")
        v = _n(x.get("relative_score"), 0.00000000001, 1)
        if k not in COMBOS or v is None or k in scores:
            raise ValueError("invalid_outcome_row")
        scores[k] = v
    if set(scores) != COMBOS or abs(sum(scores.values()) - 1) > 0.0001:
        raise ValueError("incomplete_or_unnormalized_outcomes")
    if not isinstance(bets, list) or not 5 <= len(bets) <= 24:
        raise ValueError("invalid_formal_bets")
    selected = {}
    for x in bets:
        if not isinstance(x, dict) or PROHIBITED.intersection(x):
            raise ValueError("bad_bet")
        k, yen = x.get("combination"), x.get("virtual_yen")
        if k not in scores or k in selected or type(yen) is not int or yen < 1000 or yen % 1000:
            raise ValueError("bad_formal_ticket")
        selected[k] = yen
    if sum(selected.values()) != 50000:
        raise ValueError("invalid_budget")
    return by_course, scores, selected

def analyze(formal_bets, ranked, racers, *, phase, exhibition_verified,
            frozen_at_utc, cutoff_at_utc):
    """Freeze at source-time; never infer actual tactics from finish/order."""
    if phase != "exhibition" or exhibition_verified is not True:
        return None
    by, scores, selected = _prepare(
        formal_bets, ranked, racers, frozen_at_utc, cutoff_at_utc)
    inside = by[1]
    candidates = {}
    def propose(combo, kind, evidence):
        if combo not in scores:
            return
        before = candidates.get(combo)
        if before is None:
            candidates[combo] = {"combination": combo, "scenario": kind,
                                 "evidence": evidence, "model_relative_score": round(scores[combo], 8),
                                 "already_in_formal": combo in selected}
    for course in range(3, 7):
        attacker = by[course]
        st_att = _n(attacker.get("average_start_timing"), .01, .40)
        st_in = _n(inside.get("average_start_timing"), .01, .40)
        turn_att, turn_in = _turn(attacker), _turn(inside)
        exhibit_att = _n(attacker.get("exhibition_time"), 5, 10)
        exhibit_in = _n(inside.get("exhibition_time"), 5, 10)
        show_att = _n(attacker.get("exhibition_st"), 0, .45)
        show_in = _n(inside.get("exhibition_st"), 0, .45)
        if (attacker.get("average_start_timing_imputed")
                or inside.get("average_start_timing_imputed")
                or None in (st_att, st_in, turn_att, turn_in, show_att, show_in)):
            continue
        st_edge, turn_edge, speed_edge = st_in-st_att, turn_in-turn_att, exhibit_in-exhibit_att
        # Two different evidential classes: historical average ST + original turn.
        # Ordinary exhibition-time advantage can corroborate; never trigger alone.
        if st_edge < .02 or turn_edge < .03 or speed_edge < -.025:
            continue
        evidence = {"attacking_course": course, "attacking_lane": attacker["lane"],
                    "inside_lane": inside["lane"],
                    "average_st_edge_sec": round(st_edge, 4),
                    "turn_time_edge_sec": round(turn_edge, 4),
                    "exhibition_time_edge_sec": round(speed_edge, 4)}
        a, i = str(attacker["lane"]), str(inside["lane"])
        # An outer attack need not always be the winner: inner course 2/3
        # may profit when the attacker overruns 1M. Both are hypotheses.
        if course <= 5:
            follower = by[course+1]
            ef, tf = _n(follower.get("exhibition_time"), 5, 10), _turn(follower)
            if ef is not None and tf is not None and ef <= exhibit_att + .07 and tf <= turn_att + .08:
                f = str(follower["lane"])
                propose(f"{a}-{f}-{i}", "OUTER_ATTACK_FOLLOWER", evidence)
                propose(f"{a}-{i}-{f}", "OUTER_ATTACK_INSIDE_SURVIVES", evidence)
        for inner_course in (2, 3):
            if inner_course >= course:
                continue
            counter = by[inner_course]
            ct, cs = _turn(counter), _n(counter.get("average_start_timing"), .01, .40)
            if (ct is not None and cs is not None
                    and ct <= turn_in + .06 and cs <= st_in + .015
                    and not counter.get("average_start_timing_imputed")):
                c = str(counter["lane"])
                propose(f"{c}-{i}-{a}", "ATTACK_OVERRUN_INNER_COUNTER", evidence)

    ordered = sorted(candidates.values(), key=lambda c: (-scores[c["combination"]], c["combination"]))
    missing = [x for x in ordered if not x["already_in_formal"]]
    report = {
        "version": VERSION, "model_role": "research_shadow", "not_formal": True,
        "calibrated": False, "result_data_used": False, "odds_used": False,
        "no_additional_stake": True, "formal_bets_unchanged": True,
        "frozen_at_utc": frozen_at_utc, "cutoff_at_utc": cutoff_at_utc,
        "status": "NO_SUPPORTED_PATH" if not ordered else
                  "COVERED" if not missing else "MISSING_SCENARIO_CANDIDATE",
        "candidate_count": len(ordered), "uncovered_count": len(missing),
        "candidates": ordered[:6],
        "hypothesis_warning": "Scenarios are inferred, not observed. Model scores are not probabilities.",
        "forward_comparison_only": True,
    }
    if not missing:
        return report
    # Preserve first four formal picks and every unique 1st->2nd pair.
    # Propose at most ONE paired, no-extra-money research alternative.
    pair_counts = Counter("-".join(k.split("-")[:2]) for k in selected)
    best_score = max(scores.values())
    for candidate in missing:
        combo = candidate["combination"]
        if scores[combo] < best_score*.20:
            continue
        for position in range(len(formal_bets)-1, 3, -1):
            victim = formal_bets[position]["combination"]
            pair = "-".join(victim.split("-")[:2])
            if pair_counts[pair] <= 1 or scores[combo] < scores[victim]*.65:
                continue
            choices = [k for k in selected if k != victim] + [combo]
            choices.sort(key=lambda k: (-scores[k], k))
            alternative = justified_stakes([
                {"combination": k, "relative_score": scores[k]} for k in choices])
            if len(alternative) != len(formal_bets) or sum(b["virtual_yen"] for b in alternative) != 50000:
                raise ValueError("invalid_shadow_allocation")
            report.update({
                "status": "PRE_CUTOFF_SHADOW_SWAP_ONLY",
                "replacement_candidate": combo, "replacement_victim": victim,
                "formal_control_bets": formal_bets,
                "shadow_alternative_bets": alternative,
                "same_point_count": True, "same_virtual_budget_yen": 50000,
            })
            return report
    return report
