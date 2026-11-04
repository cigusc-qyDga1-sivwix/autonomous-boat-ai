"""Independent BOAT LAB interaction-scenario shadow model.

Not calibrated. No live pipeline imports, writes, wagers, or result features.
Every scenario is conditional on a possible pre-race tactical interaction;
never interpret these scores as observed manoeuvres or true probabilities.
"""
from __future__ import annotations

from itertools import permutations
from math import exp, isfinite
from typing import Mapping

VERSION = "interaction-scenarios-v0.2-inside-failure-untrained"
ENTRY_VERSION = "interaction-scenarios-v0.3-actual-entry-untrained"
ALLOWED = {"lane", "strength", "start_mean", "exhibition_time", "course"}
PROHIBITED = {"result", "finish", "rank", "payout", "trifecta", "odds", "actual_start"}


def _num(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field}: finite number required")
    return float(value)


def _validate(racers):
    if not isinstance(racers, (list, tuple)) or len(racers) != 6:
        raise ValueError("exactly six pre-cutoff racers required")
    rows = {}
    for racer in racers:
        if not isinstance(racer, Mapping) or set(racer) - ALLOWED:
            raise ValueError("unknown or outcome-derived racer field")
        lane = racer.get("lane")
        if type(lane) is not int or lane not in range(1, 7) or lane in rows:
            raise ValueError("lanes must be unique integers 1..6")
        strength = _num(racer.get("strength"), "strength")
        if not 0 < strength <= 100:
            raise ValueError("strength must be in (0,100]")
        start = racer.get("start_mean")
        exhibition = racer.get("exhibition_time")
        if start is not None and not (0 <= _num(start, "start_mean") <= .40):
            raise ValueError("start_mean out of range")
        if exhibition is not None and not (5 <= _num(exhibition, "exhibition_time") <= 9):
            raise ValueError("exhibition_time out of range")
        rows[lane] = dict(racer)
    courses = [r.get("course") for r in rows.values()]
    if any(c is not None for c in courses) and (
            any(type(c) is not int or c not in range(1, 7) for c in courses)
            or len(set(courses)) != 6):
        raise ValueError("six unique explicit actual courses required")
    return rows


def _softmax(values):
    m = max(values)
    weights = [exp(v - m) for v in values]
    total = sum(weights)
    return [v / total for v in weights]


def _ordered_three(scores):
    """Plackett-Luce ordered outcomes, normalized independently per scenario."""
    items = list(range(1, 7))
    weights = {lane: exp(max(-12, min(12, scores[lane]))) for lane in items}
    total = sum(weights.values())
    outcomes = []
    for a, b, c in permutations(items, 3):
        p = weights[a] / total * weights[b] / (total - weights[a])
        p *= weights[c] / (total - weights[a] - weights[b])
        outcomes.append((f"{a}-{b}-{c}", p))
    return dict(outcomes)


def evaluate(racers, *, captured_at_utc: str, cutoff_at_utc: str, entry_aware: bool = False):
    """Return scenario mixtures only if input is explicitly frozen before cutoff.

    ISO8601 with timezone is required. This function deliberately does not
    accept actual starts, observed tactics, results, payouts, or odds.
    """
    from datetime import datetime
    captured = datetime.fromisoformat(captured_at_utc.replace("Z", "+00:00"))
    cutoff = datetime.fromisoformat(cutoff_at_utc.replace("Z", "+00:00"))
    if captured.tzinfo is None or cutoff.tzinfo is None or captured >= cutoff:
        raise ValueError("a pre-cutoff timezone-aware capture is required")
    rows = _validate(racers)
    if entry_aware and any(r.get("course") is None for r in rows.values()):
        raise ValueError("actual courses cannot be inferred from boat numbers")
    by_course = {r["course"] if entry_aware else lane: lane for lane, r in rows.items()}
    inside_lane = by_course[1]
    baseline = {}
    for lane, r in rows.items():
        # Relative strength is a *research input*, NOT a trained probability.
        base = __import__("math").log(float(r["strength"]))
        # Upstream strength already contains course advantage; avoid double count.
        # Average ST and exhibition time are already reflected in the
        # upstream relative weight as well. Validate inputs, but do not
        # add the same features again in the scenario layer.
        baseline[lane] = base

    # Mutually exclusive hypothetical paths: no event is inferred to have occurred.
    attack_course = max(range(3, 7), key=lambda c: baseline[by_course[c]])
    attack = by_course[attack_course]
    defender = by_course[attack_course - 1]
    # Course 6 has no outer neighbour. Never relabel course 5 as an outer follower.
    follower_course = attack_course + 1 if attack_course < 6 else (None if entry_aware else 5)
    follower = by_course[follower_course] if follower_course is not None else None

    def changes(attack_delta=0., defender_delta=0., inside_delta=0., follower_delta=0.):
        # Defender and course-1 occupant may be the same physical boat in
        # future variants; combine effects instead of silently overwriting.
        result = {}
        for lane, delta in ((attack, attack_delta), (defender, defender_delta),
                            (inside_lane, inside_delta), (follower, follower_delta)):
            if lane is not None and delta:
                result[lane] = result.get(lane, 0.) + delta
        return result

    paths = [
        ("no_major_attack", .30, {}, "No decisive outside attack"),
        ("outer_attack_succeeds", .28,
         changes(.75, inside_delta=-.70, follower_delta=.40),
         "Outside attack may push the inside boat out of a paid position"),
        ("attack_contested", .17,
         changes(-.44, defender_delta=.27, inside_delta=.20, follower_delta=.12),
         "Inside boat defends an outside challenge"),
        ("attack_overruns", .15,
         changes(-.68, inside_delta=-.25, follower_delta=.50),
         "Attacker overruns 1M; follower may capitalize"),
        ("inside_displaced", .10,
         changes(1.10, inside_delta=-1.80, follower_delta=.65),
         "Inside boat loses position and may finish outside top three"),
    ]
    if not entry_aware:
        # Preserve archived v0.2 exactly, including its historical course-6
        # assumption. Only the new model fixes the physical relationships.
        paths = [
            ("no_major_attack", .30, {}, "No decisive outside attack"),
            ("outer_attack_succeeds", .28, {attack: .75, follower: .40, 1: -.70},
             "Outside attack may push the inside boat out of a paid position"),
            ("attack_contested", .17, {attack: -.44, defender: .27, 1: .20, follower: .12},
             "Inside boat defends an outside challenge"),
            ("attack_overruns", .15, {attack: -.68, follower: .50, 1: -.25},
             "Attacker overruns 1M; follower may capitalize"),
            ("inside_displaced", .10, {attack: 1.10, follower: .65, 1: -1.80},
             "Inside boat loses position and may finish outside top three"),
        ]
    mixture = {}
    details = []
    exclusion_by_path = {}
    for label, prior, delta, reason in paths:
        scenario = _ordered_three({i: baseline[i] + delta.get(i, 0) for i in baseline})
        exclusion_by_path[label] = round(sum(p for k, p in scenario.items()
            if str(inside_lane) not in k.split("-")), 8)
        details.append({"scenario": label, "assumed_share": prior,
                        "attack_lane": attack, "defender_lane": defender,
                        **({"attack_course": attack_course, "defender_course": attack_course - 1,
                            "follower_course": follower_course, "inside_lane": inside_lane} if entry_aware else {}),
                        "follower_lane": follower, "reason": reason,
                        "top_3": sorted(scenario.items(), key=lambda item: (-item[1], item[0]))[:3]})
        for key, weight in scenario.items():
            mixture[key] = mixture.get(key, 0.0) + prior * weight
    # Conditional positions are derived from the SAME 120-outcome mixture
    # used for tickets. They are diagnostics, not calibrated probabilities;
    # no fixed "outer follower" can be called a guaranteed second place.
    by_head = {i: {"head_weight": 0.0, "second": {j: 0.0 for j in range(1, 7)},
                   "third": {j: 0.0 for j in range(1, 7)}}
               for i in range(1, 7)}
    for combo, mass in mixture.items():
        head, second, third = (int(x) for x in combo.split("-"))
        by_head[head]["head_weight"] += mass
        by_head[head]["second"][second] += mass
        by_head[head]["third"][third] += mass
    conditional_places = []
    for head in range(1, 7):
        h = by_head[head]
        head_mass = h["head_weight"]
        if head_mass <= 0:
            raise ValueError("Invalid zero head weight")
        conditional_places.append({
            "head_lane": head,
            "relative_head_share": round(head_mass, 8),
            "second_given_head": {str(j): round(h["second"][j] / head_mass, 8)
                                  for j in range(1, 7)},
            "third_given_head": {str(j): round(h["third"][j] / head_mass, 8)
                                 for j in range(1, 7)},
            "top3_partner_given_head": {
                str(j): round((h["second"][j] + h["third"][j]) / head_mass, 8)
                for j in range(1, 7)},
        })
    return {"version": ENTRY_VERSION if entry_aware else VERSION,
            **({"entry_aware": True, "inside_lane": inside_lane} if entry_aware else {}), "status": "SHADOW_UNCALIBRATED",
            "eligible_for_formal_forecast": False, "bets_generated": 0,
            "captured_at_utc": captured.isoformat(), "cutoff_at_utc": cutoff.isoformat(),
            "scenario_assumptions": details,
            "conditional_places_by_head": conditional_places,
            "course1_outside_top3_relative_mass": round(sum(p for k, p in mixture.items()
                if str(inside_lane) not in k.split("-")), 8),
            "course1_outside_top3_by_path": exclusion_by_path,
            "top_combinations": [{"combination": key, "relative_score": round(value, 8)}
                                 for key, value in sorted(mixture.items(),
                                 key=lambda item: (-item[1], item[0]))[:120]],
            "relative_score_sum": round(sum(mixture.values()), 8)}
