"""Bounded, evidence-gated first->second pair diversification for BOAT LAB v2.3.

The inputs are ONLY previously frozen/pre-cutoff canonical relative scores and
the v2.2 justified evidence gate. No outcome, real ST, odds or payout features.
"""
from __future__ import annotations
from collections import Counter
from math import ceil, isfinite

VERSION = "conditional-second-primary-v2.3-untrained"


def diversify(selected: list[dict], ranked: list[dict], policy: dict,
              paths: list[dict]) -> tuple[list[dict], dict, dict]:
    """Replace a redundant pair only if a new *supported* pair clears the
    ORIGINAL ticket's evidence tier and is at least 75% as strong.

    The four minimum model picks remain fixed; no new point count or increased
    risk budget is permitted. The full 120 are inspected, never all bought.
    """
    if not 4 <= len(selected) <= 24 or len(ranked) != 120:
        raise ValueError("invalid_selected_or_ranked_outcomes")
    reasons = policy.get("ticket_reasons")
    if not isinstance(reasons, dict) or set(reasons) != {x["combination"] for x in selected}:
        raise ValueError("missing_v22_ticket_reasons")
    original = [dict(x) for x in selected]
    issued = [dict(x) for x in selected]
    updated = {k: dict(v) for k, v in reasons.items()}
    pairs = Counter("-".join(x["combination"].split("-")[:2]) for x in issued)
    source = {}
    for path in paths:
        if not isinstance(path, dict) or not isinstance(path.get("scenario"), str):
            raise ValueError("invalid_path_provenance")
        for pair_score in path.get("top_3", []):
            combo = pair_score[0]
            key = "-".join(combo.split("-")[:2])
            source.setdefault(key, set()).add(path["scenario"])
    baseline = sorted(ranked, key=lambda x: (-x["relative_score"], x["combination"]))
    if any(not isfinite(x.get("relative_score", float("nan"))) or
           x["relative_score"] < 0 for x in baseline):
        raise ValueError("invalid_scores")
    if len({x["combination"] for x in baseline}) != 120:
        raise ValueError("duplicate_canonical_outcome")
    before = len(pairs)
    target = ceil(len(issued) * .6)
    replaced = []
    for challenger in baseline:
        if len(pairs) >= target:
            break
        combo = challenger["combination"]
        pair = "-".join(combo.split("-")[:2])
        if pair in pairs or pair not in source or combo in updated:
            continue
        if challenger["relative_score"] < .75 * baseline[len(issued) - 1]["relative_score"]:
            break  # canonical descending order: no lower challenger can qualify
        for i in range(len(issued) - 1, 3, -1):
            victim = issued[i]
            victim_pair = "-".join(victim["combination"].split("-")[:2])
            if pairs[victim_pair] <= 1:
                continue
            reason = updated[victim["combination"]]["basis"]
            rel = challenger["relative_score"] / baseline[0]["relative_score"]
            if challenger["relative_score"] < .75 * victim["relative_score"]:
                continue
            if reason == "SUPPORTED_PAIR_IN_HYPOTHETICAL_PATH" and rel < .62:
                continue
            if reason == "VERIFIED_EXHIBITION_AND_SUPPORTED_PAIR" and rel < .55:
                continue
            if reason == "EXHIBITION_AND_HISTORICAL_COURSE_TACTICS_AND_SUPPORTED_PAIR" and rel < .48:
                continue
            if reason not in (
                "SUPPORTED_PAIR_IN_HYPOTHETICAL_PATH",
                "VERIFIED_EXHIBITION_AND_SUPPORTED_PAIR",
                "EXHIBITION_AND_HISTORICAL_COURSE_TACTICS_AND_SUPPORTED_PAIR",
            ):
                continue
            issued[i] = {"combination": combo, "relative_score": challenger["relative_score"]}
            updated.pop(victim["combination"])
            updated[combo] = {
                "basis": reason,
                "path_labels": sorted(source[pair]),
                "relative_score_vs_top": round(rel, 4),
                "conditional_second_replacement": True,
            }
            pairs[victim_pair] -= 1
            if not pairs[victim_pair]:
                del pairs[victim_pair]
            pairs[pair] += 1
            replaced.append({"removed": victim["combination"], "added": combo,
                             "supported_pair": pair, "evidence_gate": reason})
            break
    issued.sort(key=lambda x: (-x["relative_score"], x["combination"]))
    if len(issued) != len(original) or len({x["combination"] for x in issued}) != len(issued):
        raise ValueError("invalid_diversified_ticket_set")
    meta = {
        "version": VERSION, "enabled": True, "status": "APPLIED" if replaced else "NO_ELIGIBLE_SWAP",
        "prior_v22_point_count": len(original), "new_point_count": len(issued),
        "pair_coverage_before": before, "pair_coverage_after": len(pairs),
        "research_pair_target": target, "candidate_score_floor_vs_victim": .75,
        "replacements": replaced, "historical_results_used": False,
        "odds_used": False, "calibrated": False, "formal_tickets_changed": bool(replaced),
        "same_point_count": True, "ticket_reasons_consistent": set(updated) == {x["combination"] for x in issued},
    }
    if not meta["ticket_reasons_consistent"]:
        raise ValueError("ticket_reason_mismatch")
    return issued, updated, meta
