"""BOAT LAB: read-only evidence-based audit of frozen predictions vs verified official results.

This tool NEVER changes prediction models, bets or historical snapshots.
It handles WATCH and SKIP as *hypothetical*, not actual investments.
The dashboard JSON is derived only from BOATRACE official confirmed results and
the corresponding pre-cutoff snapshots. Missing payouts are NOT losses.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
RESEARCH_BUDGET = 50_000


def _ticket_signature(bets: list[dict]) -> tuple:
    """Order and relative scores are not a virtual 3連単 ticket change."""
    return tuple(sorted(((b.get('combination'), b.get('virtual_yen')) for b in bets),
                        key=lambda row: row[0]))


def _metrics(rows: list[dict]) -> dict:
    n = len(rows)
    hit = sum(x["stage"] == "hit" for x in rows)
    head = sum(x["stage"] != "head_miss" for x in rows)
    pair = sum(x["stage"] in ("hit", "third_miss") for x in rows)
    paid = sum(x["virtual_payout_yen"] for x in rows)
    spent = sum(x["virtual_stake_yen"] for x in rows)
    return {
        "verified_races": n,
        "hits": hit,
        "head_captured": head,
        "first_second_captured": pair,
        "head_miss": sum(x["stage"] == "head_miss" for x in rows),
        "second_miss": sum(x["stage"] == "second_miss" for x in rows),
        "third_miss": sum(x["stage"] == "third_miss" for x in rows),
        "hit_rate": round(hit / n, 5) if n else None,
        "return_rate": round(paid / spent, 5) if spent else None,
        "virtual_stake_yen": spent,
        "virtual_payout_yen": paid,
        "virtual_profit_yen": paid - spent,
    }


def _group(rows: list[dict], field: str) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    return {key: _metrics(subset) for key, subset in sorted(groups.items())}



# User-selected operational boundary: Shimonoseki 8R (11/10) is the old
# reference; post-boundary status requires positive pre-cutoff provenance.
HEAD_RISK_BREAKPOINT_UTC = datetime.fromisoformat("2026-11-10T09:30:59+00:00")
HEAD_RISK_V02 = "strong-field-parity-diagnostic-v0.2-readonly-coverage"


def _head_risk_breakpoint_report(forecasts: list[dict], verified: list[dict],
                                 day: str) -> dict:
    """Read-only performance cohorts, NOT a v2.3 ticket-model A/B experiment.

    Classify by each actual frozen snapshot, not venue race number or a later
    deployment. Formal only; missing diagnostic provenance is not 'after'.
    """
    cohorts = ("before_checkpoint", "after_v02_verified", "after_unconfirmed")
    frozen_counts = Counter()
    result_rows = {name: [] for name in cohorts}
    lookup = {}
    anchor = None

    for r in forecasts:
        if r.get("ticket_status") != "formal":
            continue
        label = "after_unconfirmed"
        try:
            stamp = datetime.fromisoformat(r["frozen_at_utc"])
            if stamp.tzinfo is not None and stamp < HEAD_RISK_BREAKPOINT_UTC:
                label = "before_checkpoint"
            elif stamp.tzinfo is not None and stamp >= HEAD_RISK_BREAKPOINT_UTC:
                diagnostic = r.get("strong_field_diagnostic")
                if (r.get("phase") == "exhibition"
                        and isinstance(diagnostic, dict)
                        and diagnostic.get("version") == HEAD_RISK_V02
                        and diagnostic.get("coverage_diagnostics_read_only") is True
                        and diagnostic.get("changes_bets") is False
                        and diagnostic.get("changes_stake") is False):
                    label = "after_v02_verified"
        except (TypeError, ValueError, KeyError):
            pass
        frozen_counts[label] += 1
        lookup[(r.get("venue"), r.get("race"), r.get("sha256"))] = label
        if day == "2026-11-10" and r.get("venue") == "下関" and r.get("race") == 8:
            diagnostic = r.get("strong_field_diagnostic")
            anchor = {
                "frozen_at_utc": r.get("frozen_at_utc"),
                "snapshot_sha256": r.get("sha256"),
                "diagnostic_version": diagnostic.get("version")
                    if isinstance(diagnostic, dict) else None,
                "provenance_group": label,
            }

    for row in verified:
        if row.get("ticket_status") != "formal":
            continue
        label = lookup.get((row["venue"], row["race"], row["snapshot_sha256"]))
        if label in result_rows:
            result_rows[label].append(row)

    return {
        "checkpoint": "2026-11-10 下関8R→9R",
        "merge_at_utc": HEAD_RISK_BREAKPOINT_UTC.isoformat(),
        "diagnostic_version_required_after": HEAD_RISK_V02,
        "anchor_snapshot": anchor if day == "2026-11-10" else None,
        "frozen_formal_counts": {name: frozen_counts[name] for name in cohorts},
        "official_verified_formal": {
            name: _metrics(result_rows[name]) for name in cohorts
        },
        "post_cohort_eligibility": (
            "Only immutable pre-cutoff formal/exhibition forecasts frozen after "
            "merge with diagnostic v0.2 and read-only flags; otherwise unconfirmed."
        ),
        "interpretation": (
            "New diagnostic adds warnings only, not ticket selections or budget. "
            "Day/venue composition differs, so before/after hit and ROI changes "
            "do NOT establish that the warning improved prediction accuracy."
        ),
        "historical_bets_modified": False,
        "research_only": True,
    }


def _verify_race(r: dict, p: dict, day: str) -> tuple[bool, str]:
    if not p or p.get("verified") is not True or p.get("source") != "boatrace_official_pay":
        return False, "unverified"
    if p.get("snapshot_sha256") and r.get("sha256") != p.get("snapshot_sha256"):
        return False, "snapshot_mismatch"
    if not isinstance(p.get("payout_per_100"), int) or p["payout_per_100"] < 100:
        return False, "payout_invalid"
    bets = r.get("bets") or []
    point_free = r.get("model_version") in (
        "four-factor-v1.5-point-free-untrained",
        "four-factor-v1.8-adaptive-points-primary-untrained",
        "four-factor-v1.9-aligned-primary-untrained",
        "four-factor-v2.0-justified-points-primary-untrained",
        "four-factor-v2.1-actual-entry-primary-untrained",
        "four-factor-v2.2-linked-primary-untrained",
        "four-factor-v2.3-conditional-second-primary-untrained",
    )
    if r.get("model_version") in ("four-factor-v2.1-actual-entry-primary-untrained", "four-factor-v2.2-linked-primary-untrained", "four-factor-v2.3-conditional-second-primary-untrained"):
        if not 4 <= len(bets) <= 24:
            return False, "bets_count_invalid"
        if any(type(b.get("virtual_yen")) is not int or b["virtual_yen"] < 1000
               or b["virtual_yen"] % 1000 for b in bets):
            return False, "stake_invalid"
    max_points = 20 if day >= '2026-10-29' and r.get('model_version', '').startswith('four-factor-') else 12
    if not (1 <= len(bets) <= 120 if point_free else 4 <= len(bets) <= max_points):
        return False, "bets_count_invalid"
    if any(not isinstance(b.get("virtual_yen"), int) or isinstance(b.get("virtual_yen"), bool)
           or b["virtual_yen"] < (100 if point_free else 0)
           or (point_free and b["virtual_yen"] % 100) for b in bets):
        return False, "stake_invalid"
    if len({b["combination"] for b in bets}) != len(bets):
        return False, "duplicate_bets"
    if sum(b["virtual_yen"] for b in bets) != RESEARCH_BUDGET:
        return False, "budget_mismatch"
    if p.get("virtual_stake") != RESEARCH_BUDGET:
        return False, "official_stake_mismatch"
    try:
        freeze = datetime.fromisoformat(r["frozen_at_utc"])
        cutoff = datetime.fromisoformat(f"{day}T{r['cutoff_jst']}:00+09:00")
        if freeze.tzinfo is None or not freeze < cutoff:
            return False, "post_cutoff_snapshot"
    except (ValueError, KeyError, TypeError):
        return False, "time_invalid"
    order = p.get("finish")
    if not isinstance(order, str) or len(order) != 5:
        return False, "finish_invalid"
    nums = order.split("-")
    if len(nums) != 3 or len(set(nums)) != 3 or any(x not in "123456" for x in nums):
        return False, "finish_invalid"
    return True, "valid"


def _v22_control_bets(snapshot: dict) -> list[dict] | None:
    """Read an *already frozen* v2.2 counterfactual inside v2.3, never rescore."""
    if snapshot.get("model_version") != "four-factor-v2.3-conditional-second-primary-untrained":
        return None
    meta = snapshot.get("interaction_primary")
    if not isinstance(meta, dict):
        return None
    spec = meta.get("conditional_second_primary")
    if (not isinstance(spec, dict) or spec.get("enabled") is not True
            or spec.get("same_point_count") is not True
            or spec.get("historical_results_used") is not False):
        return None
    bets, control = snapshot.get("bets"), meta.get("same_race_v22_control_bets")
    if not isinstance(bets, list) or not isinstance(control, list):
        return None
    if len(bets) != len(control) or not 4 <= len(control) <= 24:
        return None
    combinations = set()
    for b in control:
        if not isinstance(b, dict):
            return None
        combo, yen = b.get("combination"), b.get("virtual_yen")
        if (not isinstance(combo, str) or len(combo.split("-")) != 3
                or len(set(combo.split("-"))) != 3
                or any(v not in "123456" for v in combo.split("-"))
                or combo in combinations or type(yen) is not int
                or yen < 1000 or yen % 1000):
            return None
        combinations.add(combo)
    return control if sum(b["virtual_yen"] for b in control) == RESEARCH_BUDGET else None


def _valid_shadow_tickets(bets):
    """Exact immutable 50k virtual stake and legal 3連単, no fabricated wins."""
    if not isinstance(bets, list) or not 4 <= len(bets) <= 24:
        return False
    combinations = set()
    spent = 0
    for bet in bets:
        if not isinstance(bet, dict):
            return False
        combo, stake = bet.get("combination"), bet.get("virtual_yen")
        if (not isinstance(combo, str) or len(combo.split("-")) != 3
                or len(set(combo.split("-"))) != 3
                or any(v not in "123456" for v in combo.split("-"))
                or combo in combinations or type(stake) is not int
                or stake < 1000 or stake % 1000 != 0):
            return False
        combinations.add(combo)
        spent += stake
    return spent == RESEARCH_BUDGET


def _shadow_trial_result(snapshot, bets, payout):
    finish = payout["finish"]
    exact = next((b for b in bets if b["combination"] == finish), None)
    heads = {b["combination"][0] for b in bets}
    pairs = {b["combination"][:3] for b in bets}
    stage = ("hit" if exact else "head_miss" if finish[0] not in heads else
             "second_miss" if finish[:3] not in pairs else "third_miss")
    return {
        "venue": snapshot["venue"], "race": snapshot["race"], "stage": stage,
        "virtual_stake_yen": RESEARCH_BUDGET,
        "virtual_payout_yen": (
            exact["virtual_yen"] * payout["payout_per_100"] // 100 if exact else 0
        ),
    }


def _venue_metric_ablation_report(forecasts, official, alerts, day):
    """Results-only daily analysis. No re-scoring or retrospective variants.

    Every compared bet must have been frozen inside the SAME validated
    pre-cutoff snapshot. Missing or nonmatching trials cannot count as losses.
    The compared pair is full VENUE SHADOW vs its ablated VENUE SHADOW;
    neither is the actual v2.3 main bet.
    """
    pair_rows = defaultdict(lambda: {"with": [], "without": [], "venues": defaultdict(
        lambda: {"with": [], "without": []})})
    exclusions = Counter()
    generated, verified_source = 0, 0
    for snapshot in forecasts:
        shadow = snapshot.get("venue_motor_exhibition_shadow")
        if not isinstance(shadow, dict):
            continue
        variants = shadow.get("metric_ablations")
        if not isinstance(variants, list) or not variants:
            continue
        generated += 1
        key = f"{day}|{snapshot['venue']}|{snapshot['race']}"
        if key in alerts:
            exclusions["official_refund_or_conflict"] += 1
            continue
        verified, why = _verify_race(snapshot, official.get(key), day)
        if not verified:
            exclusions["result_" + why] += 1
            continue
        if (snapshot.get("phase") != "exhibition"
                or snapshot.get("ticket_status") != "formal"
                or shadow.get("status") != "ready"
                or shadow.get("not_formal") is not True
                or shadow.get("result_data_used") is not False
                or shadow.get("frozen_at_utc") != snapshot.get("frozen_at_utc")
                or shadow.get("metric_ablation_protocol") != "venue-shadow-v0.2-one-metric-removed"):
            exclusions["invalid_shadow_provenance"] += 1
            continue
        control = shadow.get("trial_bets")
        if not _valid_shadow_tickets(control):
            exclusions["invalid_shadow_bets"] += 1
            continue
        verified_source += 1
        seen_metrics = set()
        for variant in variants:
            if not isinstance(variant, dict):
                exclusions["malformed_variant"] += 1
                continue
            metric = variant.get("metric")
            if (not isinstance(metric, str)
                    or metric not in ("exhibition_time", "lap_time", "half_lap_time",
                                      "turn_time", "straight_time")
                    or metric not in (shadow.get("metric_coverage") or [])
                    or metric in seen_metrics):
                exclusions["invalid_or_duplicate_metric"] += 1
                continue
            seen_metrics.add(metric)
            bets = variant.get("bets")
            if (variant.get("status") != "ready"
                    or variant.get("not_formal") is not True
                    or variant.get("actual_results_used") is not False
                    or variant.get("same_virtual_budget") is not True
                    or variant.get("frozen_at_utc") != snapshot.get("frozen_at_utc")
                    or not _valid_shadow_tickets(bets)):
                exclusions["invalid_or_unavailable_variant"] += 1
                continue
            if (variant.get("same_point_count") is not True
                    or len(bets) != len(control)):
                exclusions["point_count_mismatch"] += 1
                continue
            p = official[key]
            with_row = _shadow_trial_result(snapshot, control, p)
            without_row = _shadow_trial_result(snapshot, bets, p)
            group = pair_rows[metric]
            group["with"].append(with_row)
            group["without"].append(without_row)
            group["venues"][snapshot["venue"]]["with"].append(with_row)
            group["venues"][snapshot["venue"]]["without"].append(without_row)
    metrics = {}
    for metric, group in sorted(pair_rows.items()):
        metrics[metric] = {
            "matched_verified_races": len(group["with"]),
            "with_metric": _metrics(group["with"]),
            "without_metric": _metrics(group["without"]),
            "by_venue": {
                venue: {"matched_verified_races": len(rows["with"]),
                        "with_metric": _metrics(rows["with"]),
                        "without_metric": _metrics(rows["without"])}
                for venue, rows in sorted(group["venues"].items())
            },
        }
    return {
        "protocol": "venue-shadow-v0.2-one-metric-removed",
        "shadow_only_not_formal": True,
        "read_only_official_result_audit": True,
        "same_race_same_time_same_50000yen_budget": True,
        "matched_point_count_only": True,
        "generated_races_in_latest_snapshot": generated,
        "verified_full_shadow_races": verified_source,
        "per_metric": metrics,
        "exclusions": dict(sorted(exclusions.items())),
        "warning": ("Small single-day samples do not prove causality. Compared items "
                    "are VENUE SHADOW full/ablated, NOT v2.3 formal main. "
                    "Only prospective official-verified pairs count; collect at least 100 "
                    "matched races and sufficient venue-level samples before promotion."),
    }


def _three_leg_primary_report(forecasts, official, alerts, day):
    """Formal v2.3 leg-distributed vs old same-input v2.3 pre-cutoff control.

    Never refit model with hindsight. Only verified official payouts and frozen
    source SHA, 50k per arm, equal ticket count, valid source provenance.
    """
    actual_rows, control_rows = [], []
    by_venue = defaultdict(lambda: {"formal": [], "prior_v23": []})
    exclusions = Counter()
    generated, adjusted, changed = 0, 0, 0
    for snapshot in forecasts:
        leg = snapshot.get("three_leg_primary")
        if not isinstance(leg, dict):
            continue
        generated += 1
        if leg.get("applied") is not True:
            continue
        adjusted += 1
        if leg.get("actual_ticket_or_allocation_changed") is True:
            changed += 1
        key = f"{day}|{snapshot['venue']}|{snapshot['race']}"
        if key in alerts:
            exclusions["official_refund_or_conflict"] += 1
            continue
        eligible, why = _verify_race(snapshot, official.get(key), day)
        if not eligible:
            exclusions["result_" + why] += 1
            continue
        if (snapshot.get("model_version") !=
                "four-factor-v2.3-conditional-second-primary-untrained"
                or snapshot.get("phase") != "exhibition"
                or snapshot.get("ticket_status") != "formal"
                or leg.get("version") != "three-leg-formal-redistribution-v0.1-untrained"
                or leg.get("formal_component") is not True
                or leg.get("result_data_used") is not False
                or leg.get("pre_cutoff_only") is not True
                or leg.get("source_exhibition_weight_unchanged") is not True
                or leg.get("same_input_prior_v23_control") is not True
                or leg.get("control_no_postrace_data") is not True
                or leg.get("no_additional_stake") is not True
                or leg.get("control_frozen_at_utc") != snapshot.get("frozen_at_utc")
                or leg.get("frozen_at_utc") != snapshot.get("frozen_at_utc")):
            exclusions["invalid_pre_cutoff_provenance"] += 1
            continue
        control = leg.get("control_bets")
        bets = snapshot.get("bets")
        if not _valid_shadow_tickets(bets) or not _valid_shadow_tickets(control):
            exclusions["invalid_control_or_formal_bets"] += 1
            continue
        if leg.get("same_point_count") is not True or len(bets) != len(control):
            exclusions["point_count_mismatch"] += 1
            continue
        payout = official[key]
        main = _shadow_trial_result(snapshot, bets, payout)
        old = _shadow_trial_result(snapshot, control, payout)
        actual_rows.append(main)
        control_rows.append(old)
        by_venue[snapshot["venue"]]["formal"].append(main)
        by_venue[snapshot["venue"]]["prior_v23"].append(old)
    return {
        "protocol": "formal-v2.3-leg-redistribution-vs-unmodified-v2.3",
        "generated_pre_cutoff_latest_snapshots": generated,
        "formal_adjusted_races": adjusted,
        "changed_tickets_or_allocations": changed,
        "official_verified_equal_point_pairs": len(actual_rows),
        "formal_three_leg": _metrics(actual_rows),
        "same_input_unmodified_v23": _metrics(control_rows),
        "by_venue": {
            venue: {"formal_three_leg": _metrics(rows["formal"]),
                    "same_input_unmodified_v23": _metrics(rows["prior_v23"])}
            for venue, rows in sorted(by_venue.items())
        },
        "exclusions": dict(sorted(exclusions.items())),
        "sample_warning": ("Uncalibrated bounded attribution within existing exhibition "
                           "factor, not proven lift. No backfilled controls or new stake. "
                           "Require >=100 independent forward matched races and venue splits."),
    }


def analyze(dataset: dict) -> dict:
    """Audit a single daily snapshot; never add unresolved races as losers."""
    day = dataset["event_date"]
    if not isinstance(day, str) or len(day) != 10:
        raise ValueError("Expected one dated daily payload")
    raw = dataset.get("forecast_races") or []
    official = dataset.get("official_results") or {}
    alerts = dataset.get("settlement_alerts") or {}
    verified = []
    exclusions = Counter()
    all_bet_heads = Counter()
    race_examples = []
    point_free_rows, prior_rows = [], []
    matched_v23_rows, matched_v22_rows = [], []
    invalid_v22_control = 0
    for r in raw:
        bets = r.get("bets") or []
        if bets:
            all_bet_heads[str(bets[0]["combination"][0])] += 1
        key = f"{day}|{r['venue']}|{r['race']}"
        if key in alerts:
            exclusions["refund_cancelled_or_conflict"] += 1
            continue
        p = official.get(key)
        eligible, reason = _verify_race(r, p, day)
        if not eligible:
            exclusions[reason] += 1
            continue
        win = p["finish"]
        exact = next((b for b in bets if b["combination"] == win), None)
        heads = {b["combination"][0] for b in bets}
        pairs = {b["combination"][:3] for b in bets}
        stage = ("hit" if exact else
                 "head_miss" if win[0] not in heads else
                 "second_miss" if win[:3] not in pairs else
                 "third_miss")
        paid = exact["virtual_yen"] * p["payout_per_100"] // 100 if exact else 0
        row = {
            "venue": r["venue"], "race": r["race"],
            "classification": r.get("classification", "unclassified"),
            "ticket_status": r.get("ticket_status", "unclassified"),
            "strong_field_status": (
                (r.get("strong_field_diagnostic") or {}).get("status", "NOT_ASSESSED")
                if isinstance(r.get("strong_field_diagnostic"), dict) else "NOT_ASSESSED"
            ),
            "model_version": r.get("model_version", "unknown"),
            "phase": r.get("phase", "unknown"), "points": len(bets),
            "stage": stage, "actual_finish": win, "actual_head": win[0],
            "first_bet_head": bets[0]["combination"][0],
            "virtual_stake_yen": RESEARCH_BUDGET, "virtual_payout_yen": paid,
            "payout_per_100": p["payout_per_100"],
            "snapshot_sha256": r.get("sha256"),
            "frozen_at_utc": r.get("frozen_at_utc"),
        }
        verified.append(row)
        comparison = r.get('point_free_control') or {}
        if (r.get('model_version') == 'four-factor-v1.5-point-free-untrained'
                and comparison.get('generated_pre_cutoff') is True
                and comparison.get('frozen_at_utc') == r.get('frozen_at_utc')):
            cb = comparison.get('bets') or []
            if (4 <= len(cb) <= 12 and len({b.get('combination') for b in cb}) == len(cb)
                    and all(isinstance(b.get('virtual_yen'), int) and b['virtual_yen'] >= 1000
                            and b['virtual_yen'] % 1000 == 0 for b in cb)
                    and sum(b['virtual_yen'] for b in cb) == RESEARCH_BUDGET):
                match = next((b for b in cb if b['combination'] == win), None)
                prior_stage = ('hit' if match else 'head_miss' if win[0] not in {b['combination'][0] for b in cb}
                               else 'second_miss' if win[:3] not in {b['combination'][:3] for b in cb} else 'third_miss')
                point_free_rows.append(row)
                prior_rows.append({**row, 'stage': prior_stage,
                                   'virtual_payout_yen': match['virtual_yen'] * p['payout_per_100'] // 100 if match else 0})
        if r.get("model_version") == "four-factor-v2.3-conditional-second-primary-untrained" and r.get("ticket_status") == "formal":
            control = _v22_control_bets(r)
            if control is None:
                invalid_v22_control += 1
            else:
                match = next((b for b in control if b["combination"] == win), None)
                control_heads = {b["combination"][0] for b in control}
                control_pairs = {b["combination"][:3] for b in control}
                stage_v22 = ("hit" if match else
                             "head_miss" if win[0] not in control_heads else
                             "second_miss" if win[:3] not in control_pairs else
                             "third_miss")
                matched_v23_rows.append(row)
                matched_v22_rows.append({**row, "stage": stage_v22,
                                         "virtual_payout_yen": (match["virtual_yen"] * p["payout_per_100"] // 100
                                                                if match else 0)})
        if stage != "hit":
            race_examples.append({k: row[k] for k in
                ("venue", "race", "stage", "actual_finish", "first_bet_head", "model_version")})
    head1 = sum(x["first_bet_head"] == "1" for x in verified)
    actual1 = sum(x["actual_head"] == "1" for x in verified)
    summary = _metrics(verified)
    issue_count = len(alerts)
    all_count = dataset.get("listed_races") or 0
    forecast_count = len(raw)
    exhibition_count = sum(x.get("phase") == "exhibition" for x in raw)
    motor_shadows = [r["venue_motor_exhibition_shadow"] for r in raw
                     if isinstance(r.get("venue_motor_exhibition_shadow"), dict)]
    motor_comparable = [s for s in motor_shadows
                        if isinstance(s.get("control_bets"), list)
                        and isinstance(s.get("trial_bets"), list)]
    motor_ticket_deltas = [
        _ticket_signature(s["control_bets"]) != _ticket_signature(s["trial_bets"])
        for s in motor_comparable
    ]
    report = {
        "audit_version": "1.0",
        "event_date": day, "source_updated_at_utc": dataset.get("updated_at_utc"),
        "forecast_updated_at_utc": dataset.get("forecast_updated_at_utc"),
        "official_evidence_at_utc": (dataset.get("official_pay_info") or {}).get("retrieved_at_utc"),
        "source": "verified BOATRACE official payouts + immutable pre-cutoff predictions",
        "sample_note": "Single-day observations, not a statistically validated lift/accuracy claim.",
        "coverage": {
            "listed_races": all_count,
            "frozen_forecasts": forecast_count,
            "unforecast_races": len(dataset.get("unforecast_races") or []),
            "final_exhibition_forecasts": exhibition_count,
            "baseline_only_forecasts": sum(x.get("phase") == "baseline" for x in raw),
            "new_model_forecasts": sum(x.get("model_version") != "heuristic-0.2-untrained" for x in raw),
            "official_verified_forecasts": len(verified),
            "settlement_alerts": issue_count,
            "weather_fixed_forecasts": sum(bool(x.get("weather_used")) for x in raw),
            "weather_adjusted_forecasts": sum(bool((x.get("weather_adjustment") or {}).get("applied")) for x in raw),
        },
        "metrics": summary,
        "motor_exhibition_shadow": {
            "generated": len(motor_shadows),
            "comparable": len(motor_comparable),
            "applied": sum(s.get("applied") is True for s in motor_shadows),
            "actual_ticket_or_allocation_changes": sum(motor_ticket_deltas),
            "legacy_bet_changes_flag_mismatches": sum(
                bool(s.get("bet_changes")) != changed
                for s, changed in zip(motor_comparable, motor_ticket_deltas)),
            "status_counts": dict(sorted(Counter(
                s.get("status", "unknown") for s in motor_shadows).items())),
            "complete_six_boat_motor": sum(
                s.get("six_boat_motor_complete") is True for s in motor_shadows),
            "metric_coverage": dict(sorted(Counter(
                metric for s in motor_shadows
                for metric in (s.get("metric_coverage") or [])).items())),
            "warning": "Shadow-only; historical frozen change flags may include score-only drift. No formal pick or payout is changed.",
        },
        "bias": {
            "first_bet_head_1_all_forecasts": all_bet_heads["1"],
            "first_bet_head_1_verified": head1,
            "actual_winner_1_verified": actual1,
            "first_bet_head_1_share": round(head1 / len(verified), 4) if verified else None,
            "actual_winner_1_share": round(actual1 / len(verified), 4) if verified else None,
            "winner_lane_counts": dict(sorted(Counter(x["actual_head"] for x in verified).items())),
            "first_bet_head_lane_counts": dict(sorted(all_bet_heads.items())),
        },
        "same_race_v23_v22_control": {
            "comparison": "v2.3 vs its own pre-cutoff frozen v2.2 control; only verified formal races",
            "matched_races": len(matched_v23_rows),
            "invalid_or_missing_frozen_controls": invalid_v22_control,
            "same_point_count": True,
            "same_virtual_budget_per_race": RESEARCH_BUDGET,
            "formal_v23": _metrics(matched_v23_rows),
            "frozen_v22_control": _metrics(matched_v22_rows),
            "v23_head_misses_recovered": sum(
                a["stage"] == "head_miss" and b["stage"] != "head_miss"
                for a, b in zip(matched_v22_rows, matched_v23_rows)),
            "new_v23_head_misses": sum(
                a["stage"] != "head_miss" and b["stage"] == "head_miss"
                for a, b in zip(matched_v22_rows, matched_v23_rows)),
            "changed_ticket_or_allocation_races": sum(
                _ticket_signature((r.get("interaction_primary") or {}).get("same_race_v22_control_bets") or [])
                != _ticket_signature(r["bets"]) for r in raw
                if r.get("model_version") == "four-factor-v2.3-conditional-second-primary-untrained"
                and r.get("ticket_status") == "formal"
                and _v22_control_bets(r) is not None
                and f"{day}|{r['venue']}|{r['race']}" not in alerts
                and _verify_race(r, official.get(f"{day}|{r['venue']}|{r['race']}"), day)[0]),
            "not_formal_performance": True,
            "no_backfilled_counterfactuals": True,
            "warning": "Same-race comparator is observational and uncalibrated; do not infer a profit edge from one day.",
        },
        "point_free_comparison": {
            "selection": "Same-race, same-input, same-time pre-cutoff controls; virtual 50000 each",
            "trial": _metrics(point_free_rows), "previous": _metrics(prior_rows),
            "by_phase": {phase: {"trial": _metrics([r for r in point_free_rows if r['phase'] == phase]),
                                  "previous": _metrics([r for r in prior_rows if r['phase'] == phase])}
                         for phase in ['baseline', 'exhibition']},
        },
        "by_phase": _group(verified, "phase"),
        "by_classification": _group(verified, "classification"),
        "by_ticket_status": _group(verified, "ticket_status"),
        "by_model": _group(verified, "model_version"),
        "by_strong_field_status": _group(verified, "strong_field_status"),
        "by_strong_field_formal": _group(
            [row for row in verified if row["ticket_status"] == "formal"],
            "strong_field_status",
        ),
        "by_points": _group(verified, "points"),
        "by_venue": _group(verified, "venue"),
        "exclusions": dict(exclusions),
        "unhit_examples": race_examples[:30],
    }
    if day >= "2026-11-10":
        report["head_risk_breakpoint"] = _head_risk_breakpoint_report(raw, verified, day)
    report["venue_metric_ablation"] = _venue_metric_ablation_report(
        raw, official, alerts, day
    )
    report["three_leg_primary_comparison"] = _three_leg_primary_report(
        raw, official, alerts, day
    )
    if len(verified) >= 20:
        report["warnings"] = [
            "First-bet head skew: compare lane-1 share to winners and inspect course prior."
            if head1 / len(verified) >= .8 and actual1 / len(verified) <= .6 else None,
            "Second-place pair miss is frequent: review conditional 1st->2nd scenarios."
            if summary["second_miss"] >= summary["third_miss"] else None,
            "Do not interpret only 4–12-point rollout races as proof of improvement."
            if report["coverage"]["new_model_forecasts"] < 100 else None,
            "Most current frozen forecasts lack final exhibition values."
            if exhibition_count * 2 < forecast_count else None,
            "Many published races were not frozen before cutoff."
            if forecast_count * 4 < all_count * 3 else None,
        ]
        report["warnings"] = [s for s in report["warnings"] if s]
    else:
        report["warnings"] = ["Too few verified races for any reliable assessment."]
    return report


def frozen_projection(ledger: dict) -> dict:
    """Project saved snapshots for audit only; never run a prediction model."""
    if __package__:
        from .entry_exhibition_gate import summarize_gate
    else:
        from entry_exhibition_gate import summarize_gate
    day = ledger["event_date"]
    rows, missing = [], []
    records = ledger.get("race_records") or {}
    for record in records.values():
        versions = record.get("versions") or []
        if not versions:
            missing.append({"venue": record.get("venue"), "race": record.get("race")})
            continue
        snapshot = dict(versions[-1])
        snapshot.setdefault("venue", record["venue"])
        snapshot.setdefault("race", record["race"])
        snapshot.setdefault("cutoff_jst", record.get("cutoff_jst"))
        if not snapshot.get("cutoff_jst"):
            try:
                cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
                if cutoff.tzinfo is not None and cutoff.astimezone(JST).date().isoformat() == day:
                    snapshot["cutoff_jst"] = cutoff.astimezone(JST).strftime("%H:%M")
            except (KeyError, TypeError, ValueError):
                pass
        gate = summarize_gate(snapshot, day)
        snapshot["ticket_status"] = "formal" if gate["final_eligible"] else "provisional"
        rows.append(snapshot)
    return {"event_date": day, "forecast_races": rows, "listed_races": len(records),
            "unforecast_races": missing,
            "updated_at_utc": ledger.get("last_updated_at_utc"),
            "forecast_updated_at_utc": ledger.get("last_updated_at_utc")}


def persist(directory: Path, dataset: dict, *, latest: bool = True) -> dict:
    """Publish one audit from the exact reconciled view, including unchanged retries."""
    report = analyze(dataset)
    targets = [directory / "audit" / (dataset["event_date"] + ".json")]
    if latest:
        targets.append(directory / "audit-latest.json")
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_text(encoding="utf-8") == encoded:
            continue
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(target)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("app/data/live/latest.json"))
    parser.add_argument("--out", type=Path, default=Path("app/data/live/audit-latest.json"))
    args = parser.parse_args()
    result = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps({
        "event_date": result["event_date"],
        "verified": result["metrics"]["verified_races"],
        "hit": result["metrics"]["hits"],
        "second_miss": result["metrics"]["second_miss"],
        "third_miss": result["metrics"]["third_miss"],
        "head1_primary": result["bias"]["first_bet_head_1_verified"],
        "return_rate": result["metrics"]["return_rate"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
