"""Pre-cutoff research-only reselection for uncovered winner / 1st->2nd paths.

This is a counterfactual shadow, never the formal v2.3 prediction.  The inputs
are already available BEFORE cutoff: the 120 normalized model paths, original
formal bets, pre-race hypothetical scenarios, the saved coverage diagnostic,
and six-boat exhibition eligibility.  No result, payout, odds, or retrospective
coefficients may influence selection.  A hypothetical path is NOT proof of a
profitable wager; changes require forward validation before promotion.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from itertools import permutations
from math import isfinite

try:
    from .justified_main_points import justified_stakes
except ImportError:
    from justified_main_points import justified_stakes

VERSION = "coverage-reselection-shadow-v0.1-untrained"
ALLOWED = {"-".join(p) for p in permutations("123456", 3)}
SCORE_VS_VICTIM_MIN = 0.75
SCORE_VS_BEST_MIN = 0.45
TOTAL_VIRTUAL_YEN = 50000


def review(formal_bets: list[dict], ranked: list[dict], diagnostic: dict,
           scenarios: list[dict], policy: dict, *,
           phase: str, exhibition_verified: bool) -> dict:
    """Research replay at freeze time; always fail closed without changing bets."""
    report = {
        "version": VERSION, "model_role": "research_shadow",
        "status": "NOT_ELIGIBLE", "not_formal": True,
        "formal_bets_unchanged": True, "no_additional_stake": True,
        "results_used": False, "odds_used": False, "calibrated": False,
        "prospective_comparison_only": True,
        "same_point_count": True, "virtual_budget_yen": TOTAL_VIRTUAL_YEN,
        "selection_gate": "pre_cutoff_exhibition_and_scenario_top3_only",
        "score_floor_vs_victim": SCORE_VS_VICTIM_MIN,
        "score_floor_vs_best": SCORE_VS_BEST_MIN,
        "notes": ("Scenario top-3 is a model hypothesis, not independent observed "
                  "evidence. Never promote without matched forward testing."),
    }
    if phase != "exhibition" or exhibition_verified is not True:
        report["reason"] = "six_boat_pre_cutoff_exhibition_unverified"
        return report
    if (not isinstance(diagnostic, dict)
            or diagnostic.get("version") != "strong-field-parity-diagnostic-v0.2-readonly-coverage"
            or diagnostic.get("coverage_diagnostics_read_only") is not True
            or diagnostic.get("results_used") is not False
            or not isinstance(policy, dict)
            or policy.get("version") != "justified-main-points-v2.0-conservative-untrained"):
        report["reason"] = "diagnostic_or_policy_provenance_missing"
        return report
    if not isinstance(formal_bets, list) or not 5 <= len(formal_bets) <= 24:
        report["reason"] = "no_redundant_tail_or_invalid_point_count"
        return report
    if not isinstance(ranked, list) or len(ranked) != 120:
        report["reason"] = "incomplete_120_ranking"
        return report

    scores = {}
    for entry in ranked:
        if not isinstance(entry, dict):
            report["reason"] = "invalid_ranking_row"
            return report
        combo, val = entry.get("combination"), entry.get("relative_score")
        if (combo not in ALLOWED or combo in scores
                or type(val) not in (float, int) or not isfinite(val) or val <= 0):
            report["reason"] = "invalid_ranking_row"
            return report
        scores[combo] = float(val)
    if set(scores) != ALLOWED or not 0.99 <= sum(scores.values()) <= 1.01:
        report["reason"] = "ranking_not_normalized_or_incomplete"
        return report

    original = {}
    for bet in formal_bets:
        if not isinstance(bet, dict):
            report["reason"] = "invalid_formal_ticket"
            return report
        combo, amount = bet.get("combination"), bet.get("virtual_yen")
        if (combo not in scores or combo in original
                or type(amount) is not int or amount <= 0 or amount % 1000):
            report["reason"] = "invalid_formal_ticket"
            return report
        original[combo] = amount
    if sum(original.values()) != TOTAL_VIRTUAL_YEN:
        report["reason"] = "formal_budget_mismatch"
        return report
    if not isinstance(scenarios, list) or len(scenarios) != 6:
        report["reason"] = "incomplete_scenario_provenance"
        return report
    supported = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not isinstance(scenario.get("scenario"), str):
            report["reason"] = "invalid_scenario"
            return report
        top = scenario.get("top_3")
        if not isinstance(top, list) or len(top) != 3:
            report["reason"] = "invalid_scenario"
            return report
        for item in top:
            if (not isinstance(item, (list, tuple)) or len(item) != 2
                    or item[0] not in scores
                    or type(item[1]) not in (float, int)
                    or not isfinite(item[1]) or item[1] < 0):
                report["reason"] = "invalid_scenario"
                return report
            supported.setdefault(item[0], set()).add(scenario["scenario"])

    if diagnostic.get("second_pair_coverage_status") != "ASSESSED":
        missing_pairs = []
    else:
        missing_pairs = diagnostic.get("missing_top_second_pairs") or []
    missing_heads = diagnostic.get("uncovered_top_two_heads") or []
    if not isinstance(missing_pairs, list) or not isinstance(missing_heads, list):
        report["reason"] = "invalid_coverage_alert"
        return report
    candidates = {}
    for item in missing_heads:
        if not isinstance(item, dict) or type(item.get("lane")) is not int:
            continue
        h = str(item["lane"])
        if h not in "123456":
            continue
        for combo in supported:
            if combo.startswith(h + "-") and combo not in original:
                candidates.setdefault(combo, {"kind": "uncovered_head", "head": int(h)})
    for item in missing_pairs:
        if (not isinstance(item, dict) or type(item.get("head_lane")) is not int
                or type(item.get("second_lane")) is not int):
            continue
        a, b = item["head_lane"], item["second_lane"]
        if a == b or not (1 <= a <= 6 and 1 <= b <= 6):
            continue
        for combo in supported:
            if combo.startswith(f"{a}-{b}-") and combo not in original:
                candidates.setdefault(combo, {"kind": "uncovered_second_pair",
                                               "head": a, "second": b})
    if not candidates:
        report["status"] = "NO_SUPPORTED_COVERAGE_CANDIDATE"
        report["reason"] = "no_alert_or_no_top3_path_support"
        return report

    # Preserve the highest four formal selections; replace at most one
    # lower-ranked redundant pair so points and total budget remain fixed.
    pair_counts = Counter("-".join(k.split("-")[:2]) for k in original)
    best_score = max(scores.values())
    eligible = sorted(candidates, key=lambda c: (
        0 if candidates[c]["kind"] == "uncovered_head" else 1,
        -scores[c], c))
    reviewed = []
    for combo in eligible:
        reason = candidates[combo]
        if scores[combo] / best_score < SCORE_VS_BEST_MIN:
            reviewed.append({"candidate": combo, "decision": "REJECT",
                             "reason": "relative_score_below_model_floor"})
            continue
        for i in range(len(formal_bets) - 1, 3, -1):
            victim = formal_bets[i]["combination"]
            victim_pair = "-".join(victim.split("-")[:2])
            if pair_counts[victim_pair] <= 1:
                continue
            if scores[combo] < SCORE_VS_VICTIM_MIN * scores[victim]:
                continue
            selected = [x for x in original if x != victim] + [combo]
            selected.sort(key=lambda c: (-scores[c], c))
            alt = justified_stakes([{"combination": c, "relative_score": scores[c]}
                                    for c in selected])
            assert len(alt) == len(formal_bets)
            assert sum(b["virtual_yen"] for b in alt) == TOTAL_VIRTUAL_YEN
            report.update({
                "status": "PROPOSED_FOR_FORWARD_TEST_ONLY",
                "candidate_review": reviewed + [{
                    "candidate": combo, "decision": "PROPOSE_RESEARCH_SWAP",
                    "reason": reason["kind"],
                    "scenario_paths": sorted(supported[combo]),
                    "score_ratio_vs_removed": round(scores[combo] / scores[victim], 6),
                    "score_ratio_vs_model_top": round(scores[combo] / best_score, 6),
                    "important_limitation": "hypothetical_path_not_independent_evidence",
                }],
                "replacement": {"removed": victim, "added": combo,
                                "coverage_kind": reason["kind"]},
                "forecast_alternative_bets": alt,
                "alternative_point_count": len(alt),
                "point_count_matched": True,
                "actual_ticket_or_allocation_change": True,
                "source_input_sha256": hashlib.sha256(json.dumps(
                    {"ranked": ranked, "formal_bets": formal_bets, "scenarios": scenarios},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")).hexdigest(),
            })
            return report
        reviewed.append({"candidate": combo, "decision": "REJECT",
                         "reason": "no_redundant_tail_or_score_below_victim_floor"})
    report["status"] = "NO_QUALIFIED_SWAP"
    report["candidate_review"] = reviewed
    return report
