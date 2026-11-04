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
ALLOWED = {"lane", "strength", "start_mean", "exhibition_time"}
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


def evaluate(racers, *, captured_at_utc: str, cutoff_at_utc: str):
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
    baseline = {}
    for lane, r in rows.items():
        # Relative strength is a *research input*, NOT a trained probability.
        base = __import__("math").log(float(r["strength"]))
        # Upstream strength already contains course advantage; avoid double count.
        if r.get("start_mean") is not None:
            base += max(-.22, min(.22, (.16 - r["start_mean"]) * 1.8))
        if r.get("exhibition_time") is not None:
            base += max(-.14, min(.14, (6.85 - r["exhibition_time"]) * .18))
        baseline[lane] = base

    # Mutually exclusive hypothetical paths: no event is inferred to have occurred.
    attack = max(range(3, 7), key=lambda i: baseline[i])
    defender = max(1, attack - 1)
    follower = min(6, attack + 1) if attack < 6 else 5
    paths = [
        ("no_major_attack", .30, {}, "No decisive outside attack"),
        ("outer_attack_succeeds", .28,
         {attack: .75, follower: .40, 1: -.70},
         "Outside attack may push the inside boat out of a paid position"),
        ("attack_contested", .17,
         {attack: -.44, defender: .27, 1: .20, follower: .12},
         "Inside boat defends an outside challenge"),
        ("attack_overruns", .15,
         {attack: -.68, follower: .50, 1: -.25},
         "Attacker overruns 1M; follower may capitalize"),
        ("inside_displaced", .10,
         {attack: 1.10, follower: .65, 1: -1.80},
         "Inside boat loses position and may finish outside top three"),
    ]
    mixture = {}
    details = []
    exclusion_by_path = {}
    for label, prior, delta, reason in paths:
        scenario = _ordered_three({i: baseline[i] + delta.get(i, 0) for i in baseline})
        exclusion_by_path[label] = round(sum(p for k, p in scenario.items()
            if "1" not in k.split("-")), 8)
        details.append({"scenario": label, "assumed_share": prior,
                        "attack_lane": attack, "defender_lane": defender,
                        "follower_lane": follower, "reason": reason,
                        "top_3": sorted(scenario.items(), key=lambda item: (-item[1], item[0]))[:3]})
        for key, weight in scenario.items():
            mixture[key] = mixture.get(key, 0.0) + prior * weight
    return {"version": VERSION, "status": "SHADOW_UNCALIBRATED",
            "eligible_for_formal_forecast": False, "bets_generated": 0,
            "captured_at_utc": captured.isoformat(), "cutoff_at_utc": cutoff.isoformat(),
            "scenario_assumptions": details,
            "course1_outside_top3_relative_mass": round(sum(p for k, p in mixture.items()
                if "1" not in k.split("-")), 8),
            "course1_outside_top3_by_path": exclusion_by_path,
            "top_combinations": [{"combination": key, "relative_score": round(value, 8)}
                                 for key, value in sorted(mixture.items(),
                                 key=lambda item: (-item[1], item[0]))[:120]],
            "relative_score_sum": round(sum(mixture.values()), 8)}
