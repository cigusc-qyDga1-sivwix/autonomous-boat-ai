"""Adaptive point count for BOAT LAB's pre-cutoff v1.8 PRIMARY tickets.

Uses only ranked scenario relative scores; NO postrace result, odds, calibrated
probability, or prior model point-count. The thresholds are research heuristics
and may harm payout efficiency. At 100 yen/unit the 50,000 yen budget can
support all 120 distinct trifecta tickets without violating allocation rules.
"""
from __future__ import annotations

from math import isfinite, log
from typing import Sequence

VERSION = "adaptive-primary-points-v0.1-untrained"
BUDGET_YEN = 50_000
UNIT_YEN = 100
VALID = {f"{a}-{b}-{c}" for a in range(1, 7)
         for b in range(1, 7) for c in range(1, 7)
         if len({a, b, c}) == 3}


def allocate_dynamic(ranked: Sequence[dict], *, budget_yen=BUDGET_YEN,
                     unit_yen=UNIT_YEN):
    """Select an evidence-relative prefix, then allocate all virtual budget.

    A lower-entropy score distribution concentrates stakes on fewer plausible
    combinations. High ambiguity admits more. Neither fixed point bands nor
    the *old* model's ticket count is used. No claims of statistical edge.
    """
    if not isinstance(ranked, (tuple, list)) or len(ranked) != 120:
        raise ValueError("expected all 120 ranked ordered trifecta outcomes")
    if type(budget_yen) is not int or type(unit_yen) is not int or unit_yen <= 0 or budget_yen < 120 * unit_yen or budget_yen % unit_yen:
        raise ValueError("need sufficient integer virtual units for up to 120 tickets")
    pairs = []
    seen = set()
    for entry in ranked:
        if not isinstance(entry, dict):
            raise ValueError("invalid entry")
        combo = entry.get("combination")
        score = entry.get("relative_score")
        if combo not in VALID or combo in seen or isinstance(score, bool) or not isinstance(score, (float, int)) or not isfinite(score) or score <= 0:
            raise ValueError("invalid, duplicate or nonpositive combination score")
        seen.add(combo)
        pairs.append((combo, float(score)))
    # Do not trust caller ordering; tie-break lexicographically.
    pairs.sort(key=lambda item: (-item[1], item[0]))
    total = sum(s for _, s in pairs)
    probabilities = [s/total for _, s in pairs]
    entropy = -sum(p*log(p) for p in probabilities) / log(len(pairs))
    peakedness = max(0.0, min(1.0, 1.0 - entropy))
    # Working heuristics, not statistically fitted. Select when additional
    # score mass is relevant AND the next option is not negligible vs #1.
    # High ambiguity -> broader ticket set; concentration -> narrower.
    coverage_target = .45 + .30 * peakedness
    score_floor_ratio = .10 + .28 * peakedness
    selected = []
    cumulative = 0.0
    top = pairs[0][1]
    for combo, score in pairs:
        if (len(selected) >= 4 and
                (cumulative >= coverage_target or score / top < score_floor_ratio)):
            break
        selected.append({"combination": combo, "relative_score": score})
        cumulative += score / total
    if not 4 <= len(selected) <= 120:
        raise ValueError("dynamic point selection invalid")
    return selected, {
        "version": VERSION,
        "point_selection": "entropy_and_relative_score_mass",
        "uncalibrated": True,
        "normalized_entropy": round(entropy, 6),
        "score_coverage_selected": round(cumulative, 6),
        "target_relative_score_coverage": round(coverage_target, 6),
        "last_score_vs_top": round(selected[-1]["relative_score"] / top, 6),
        "relative_score_floor": round(score_floor_ratio, 6),
        "candidate_count": len(pairs),
        "selected_point_count": len(selected),
        "not_calibrated_probability": True,
    }


def stake_dynamic(selected: Sequence[dict], *, budget_yen=BUDGET_YEN,
                  unit_yen=UNIT_YEN) -> list[dict]:
    """Deterministic 100-yen units; at least one unit per candidate."""
    if (not isinstance(selected, (tuple, list)) or not 1 <= len(selected) <= 120
            or type(budget_yen) is not int or type(unit_yen) is not int
            or unit_yen <= 0 or budget_yen % unit_yen
            or budget_yen // unit_yen < len(selected)):
        raise ValueError("invalid dynamic stake dimensions")
    scores = []
    seen = set()
    for item in selected:
        if not isinstance(item, dict):
            raise ValueError("invalid candidate")
        combo, score = item.get("combination"), item.get("relative_score")
        if (combo not in VALID or combo in seen or isinstance(score, bool)
                or not isinstance(score, (int, float)) or not isfinite(score)
                or score <= 0):
            raise ValueError("invalid candidate score")
        seen.add(combo)
        scores.append(float(score))
    leftover = budget_yen // unit_yen - len(selected)
    mass = sum(scores)
    ideal = [leftover * weight / mass for weight in scores]
    whole = [int(value) for value in ideal]
    remainder = leftover - sum(whole)
    for idx in sorted(range(len(selected)),
                      key=lambda i: (-(ideal[i] - whole[i]), i))[:remainder]:
        whole[idx] += 1
    bets = [
        {"combination": item["combination"], "virtual_yen": (whole[i] + 1) * unit_yen}
        for i, item in enumerate(selected)
    ]
    if sum(x["virtual_yen"] for x in bets) != budget_yen:
        raise ValueError("budget allocation failure")
    return bets
