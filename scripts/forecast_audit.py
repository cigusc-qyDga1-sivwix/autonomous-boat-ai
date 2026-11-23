"""BOAT LAB: read-only evidence-based audit of frozen predictions vs verified official results.

This tool NEVER changes prediction models, bets or historical snapshots.
It handles WATCH and SKIP as *hypothetical*, not actual investments.
The dashboard JSON is derived only from BOATRACE official confirmed results and
the corresponding pre-cutoff snapshots. Missing payouts are NOT losses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from .head_focus_learning import inspect as inspect_head_focus
    from .venue_weather_learning import inspect as inspect_venue_weather
except ImportError:
    from head_focus_learning import inspect as inspect_head_focus
    from venue_weather_learning import inspect as inspect_venue_weather

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
HEAD_RISK_ELIGIBLE_VENUES = (
    "桐生", "戸田", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑",
    "津", "三国", "びわこ", "住之江", "尼崎", "鳴門", "丸亀",
    "児島", "宮島", "徳山", "下関", "若松", "芦屋", "福岡",
    "唐津", "大村",
)
# 江戸川 is excluded from current BOAT LAB rollout; no silent classification.


def _head_risk_breakpoint_report(forecasts: list[dict], verified: list[dict],
                                 day: str) -> dict:
    """Read-only performance cohorts, NOT a v2.3 ticket-model A/B experiment.

    Classify by each actual frozen snapshot, not venue race number or a later
    deployment. Formal only; missing diagnostic provenance is not 'after'.
    """
    cohorts = ("before_checkpoint", "after_v02_verified", "after_unconfirmed")
    frozen_counts = Counter()
    result_rows = {name: [] for name in cohorts}
    # Per-venue evidence; venues with no races are explicitly unverified.
    venue_frozen = defaultdict(Counter)
    venue_results = defaultdict(lambda: {name: [] for name in cohorts})
    first_v02 = {}
    venue_warnings = defaultdict(Counter)
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
        venue = r.get("venue")
        if isinstance(venue, str) and venue:
            venue_frozen[venue][label] += 1
            if label == "after_v02_verified":
                diag = r["strong_field_diagnostic"]
                if diag.get("head_coverage_warning") or diag.get("head_coverage_outside_parity_warning"):
                    venue_warnings[venue]["uncovered_head_alerts"] += 1
                if diag.get("second_pair_coverage_warning"):
                    venue_warnings[venue]["missing_second_pair_alerts"] += 1
                record = {
                    "race": r.get("race"),
                    "frozen_at_utc": r.get("frozen_at_utc"),
                    "snapshot_sha256": r.get("sha256"),
                }
                if venue not in first_v02 or stamp < first_v02[venue][0]:
                    first_v02[venue] = (stamp, record)
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
            venue_results[row["venue"]][label].append(row)

    def venue_status(venue: str) -> str:
        counts = venue_frozen[venue]
        if sum(counts.values()) == 0:
            return "NO_FORMAL_FORECAST_RECORDED"
        if counts["after_unconfirmed"]:
            return "PARTIALLY_UNCONFIRMED" if counts["after_v02_verified"] else "AFTER_NOT_VERIFIED"
        if counts["after_v02_verified"]:
            return "AFTER_V02_VERIFIED"
        return "BEFORE_CHECKPOINT_ONLY"

    by_venue = {
        venue: {
            "status": venue_status(venue),
            "formal_frozen_counts": {
                name: venue_frozen[venue][name] for name in cohorts
            },
            "official_verified_formal": {
                name: _metrics(venue_results[venue][name]) for name in cohorts
            },
            "first_v02_pre_cutoff_snapshot": (
                first_v02[venue][1] if venue in first_v02 else None
            ),
            "new_diagnostic_warning_counts": {
                "uncovered_head_alerts": venue_warnings[venue]["uncovered_head_alerts"],
                "missing_second_pair_alerts": venue_warnings[venue]["missing_second_pair_alerts"],
            },
        }
        for venue in sorted(set(HEAD_RISK_ELIGIBLE_VENUES) | set(venue_frozen))
    }

    return {
        "checkpoint": "2026-11-10 下関8R→9R",
        "merge_at_utc": HEAD_RISK_BREAKPOINT_UTC.isoformat(),
        "diagnostic_version_required_after": HEAD_RISK_V02,
        "anchor_snapshot": anchor if day == "2026-11-10" else None,
        "frozen_formal_counts": {name: frozen_counts[name] for name in cohorts},
        "official_verified_formal": {
            name: _metrics(result_rows[name]) for name in cohorts
        },
        "by_venue": by_venue,
        "eligible_venues": list(HEAD_RISK_ELIGIBLE_VENUES),
        "excluded_venue": "江戸川",
        "venue_reporting_note": (
            "Per-venue status requires each individual immutable pre-cutoff "
            "snapshot with v0.2 evidence. No forecast does not mean a failed venue. "
            "Official results are not counted until SHA matched and verified."
        ),
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
        "four-factor-v2.4-entry-exhibition-balance-untrained",
        "four-factor-v2.5-evidence-head-switch-untrained",
    )
    if r.get("model_version") in ("four-factor-v2.1-actual-entry-primary-untrained", "four-factor-v2.2-linked-primary-untrained", "four-factor-v2.3-conditional-second-primary-untrained", "four-factor-v2.4-entry-exhibition-balance-untrained", "four-factor-v2.5-evidence-head-switch-untrained"):
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


def _learned_exhibition_effect_report(forecasts, official, alerts, day):
    """Prospective identical-model exhibition vs no-exhibition freeze.

    NEVER regenerate past hypothetical rankings. The no-exhibition ablation
    must have been generated and hashed before the race in its live snapshot.
    """
    grouped = defaultdict(lambda: {"formal": [], "no_exhibition": []})
    exclusions = Counter()
    total = 0
    changed = 0

    def sha(value):
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()

    for row in forecasts:
        a = row.get("learned_exhibition_ablation")
        if not isinstance(a, dict):
            continue
        total += 1
        key = f"{day}|{row.get('venue')}|{row.get('race')}"
        if key in alerts:
            exclusions["official_conflict_or_refund"] += 1
            continue
        ok, reason = _verify_race(row, official.get(key), day)
        if not ok:
            exclusions[reason] += 1
            continue
        formal = row.get("bets")
        control = a.get("formal_bets")
        shadow = a.get("no_exhibition_bets")
        try:
            good = (
                row.get("ticket_status") == "formal"
                and row.get("model_version") == "four-factor-learned-v1-conditional-choice-trained"
                and a.get("version") == "learned-exhibition-effect-shadow-v0.1"
                and a.get("model_role") == "research_shadow"
                and a.get("model_sha256") == (row.get("learned_formal") or {}).get("model_sha256")
                and a.get("frozen_at_utc") == row.get("frozen_at_utc")
                and a.get("same_model_same_time") is True
                and a.get("same_point_count") is True
                and a.get("formal_tickets_changed") is False
                and a.get("official_result_used") is False
                and a.get("odds_used") is False
                and a.get("not_a_historical_frozen_baseline") is True
                and a.get("virtual_budget_yen_each") == RESEARCH_BUDGET
                and (row.get("exhibition_input_check") or {}).get("verified_before_freeze") is True
                and (row.get("exhibition_input_check") or {}).get("six_boats_matched") == 6
                and isinstance(formal, list) and isinstance(control, list)
                and isinstance(shadow, list)
                and len(formal) == len(control) == len(shadow)
                and _valid_shadow_tickets(control) and _valid_shadow_tickets(shadow)
                and _ticket_signature(formal) == _ticket_signature(control)
                and a.get("formal_bets_sha256") == sha(control)
                and a.get("no_exhibition_bets_sha256") == sha(shadow)
                and a.get("source_snapshot_sha256") == sha({
                    "racers": row.get("racers"),
                    "exhibition_origin": row.get("exhibition_origin"),
                    "exhibition_input_check": row.get("exhibition_input_check"),
                })
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            good = False
        if not good:
            exclusions["unproven_or_modified_ablation"] += 1
            continue
        p = official[key]
        f = _shadow_trial_result(row, formal, p)
        e = _shadow_trial_result(row, shadow, p)
        grouped[row["venue"]]["formal"].append(f)
        grouped[row["venue"]]["no_exhibition"].append(e)
        changed += _ticket_signature(formal) != _ticket_signature(shadow)

    def measures(a, b):
        return {
            "matched_races": len(a),
            "with_exhibition_formal": _metrics(a),
            "without_exhibition_research": _metrics(b),
            "hits_delta_exhibition_minus_without": sum(x["stage"] == "hit" for x in a)
                                                  - sum(x["stage"] == "hit" for x in b),
            "payout_delta_exhibition_minus_without": sum(x["virtual_payout_yen"] for x in a)
                                                    - sum(x["virtual_payout_yen"] for x in b),
        }
    formals = [x for g in grouped.values() for x in g["formal"]]
    without = [x for g in grouped.values() for x in g["no_exhibition"]]
    return {
        "protocol": "forward-only-same-model-same-time-exhibition-ablation-v0.1",
        "frozen_ablation_forecasts": total,
        "official_matched_ticket_change_races": changed,
        **measures(formals, without),
        "by_venue": {venue: measures(g["formal"], g["no_exhibition"])
                     for venue, g in sorted(grouped.items())},
        "exclusions": dict(sorted(exclusions.items())),
        "not_a_historical_baseline": True,
        "historical_formal_forecasts_modified": False,
        "no_hindsight_reconstruction": True,
        "warning": ("This is a same-time ablation of exhibition inputs, not a "
                    "previously frozen baseline and not evidence of calibrated edge."),
    }


def _learned_conditional_shadow_report(forecasts, official, alerts, day):
    """Read-only same-time learned-main vs v2.6 pair shadow. No retrofitting."""
    formal, alternative = [], []
    by_venue = defaultdict(lambda: {"formal": [], "shadow": []})
    exclusions = Counter()
    frozen_count = 0
    changed_count = 0

    def hashed(value):
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()

    for r in forecasts:
        proof = r.get("learned_conditional_shadow")
        if not isinstance(proof, dict):
            continue
        frozen_count += 1
        key = f"{day}|{r.get('venue')}|{r.get('race')}"
        if key in alerts:
            exclusions["official_conflict_refund_or_cancel"] += 1
            continue
        ok, reason = _verify_race(r, official.get(key), day)
        if not ok:
            exclusions[reason] += 1
            continue
        main, control, trial = r.get("bets"), proof.get("control_bets"), proof.get("shadow_bets")
        try:
            integrity = (
                r.get("ticket_status") == "formal"
                and r.get("model_version") == "four-factor-learned-v1-conditional-choice-trained"
                and proof.get("model_role") == "research_shadow"
                and proof.get("version") == "learned-conditional-pair-shadow-v0.1"
                and proof.get("model_sha256") == (r.get("learned_formal") or {}).get("model_sha256")
                and proof.get("frozen_at_utc") == r.get("frozen_at_utc")
                and proof.get("same_input_same_time") is True
                and proof.get("same_point_count") is True
                and proof.get("head_marginals_preserved") is True
                and proof.get("formal_tickets_changed") is False
                and proof.get("official_results_used") is False
                and proof.get("odds_used") is False
                and proof.get("virtual_stake_yen_each") == RESEARCH_BUDGET
                and (r.get("exhibition_input_check") or {}).get("verified_before_freeze") is True
                and (r.get("exhibition_input_check") or {}).get("six_boats_matched") == 6
                and isinstance(main, list) and isinstance(control, list)
                and isinstance(trial, list) and len(main) == len(control) == len(trial)
                and _valid_shadow_tickets(control) and _valid_shadow_tickets(trial)
                and _ticket_signature(main) == _ticket_signature(control)
                and proof.get("shadow_bets_sha256") == hashed(trial)
                and proof.get("source_snapshot_sha256") == hashed({
                    "racers": r.get("racers"),
                    "exhibition_origin": r.get("exhibition_origin"),
                    "exhibition_input_check": r.get("exhibition_input_check"),
                })
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            integrity = False
        if not integrity:
            exclusions["unproven_or_modified_shadow"] += 1
            continue
        pay = official[key]
        m = _shadow_trial_result(r, main, pay)
        a = _shadow_trial_result(r, trial, pay)
        formal.append(m)
        alternative.append(a)
        by_venue[r["venue"]]["formal"].append(m)
        by_venue[r["venue"]]["shadow"].append(a)
        changed_count += _ticket_signature(main) != _ticket_signature(trial)

    def comparison(main, shadow):
        return {
            "matched_races": len(main),
            "formal": _metrics(main),
            "research_shadow": _metrics(shadow),
            "head_misses_recovered": sum(
                x["stage"] == "head_miss" and y["stage"] != "head_miss"
                for x, y in zip(main, shadow)
            ),
            "new_head_misses": sum(
                x["stage"] != "head_miss" and y["stage"] == "head_miss"
                for x, y in zip(main, shadow)
            ),
            "second_misses_recovered": sum(
                x["stage"] == "second_miss" and y["stage"] != "second_miss"
                for x, y in zip(main, shadow)
            ),
            "new_second_misses": sum(
                x["stage"] != "second_miss" and y["stage"] == "second_miss"
                for x, y in zip(main, shadow)
            ),
        }

    return {
        "protocol": "precutoff-learned-main-vs-head-preserved-v26-shadow-v0.1",
        "frozen_shadows": frozen_count,
        "changed_ticket_pairs": changed_count,
        **comparison(formal, alternative),
        "by_venue": {venue: comparison(group["formal"], group["shadow"])
                     for venue, group in sorted(by_venue.items())},
        "exclusions": dict(sorted(exclusions.items())),
        "formal_performance_changed": False,
        "no_hindsight": True,
        "warning": "Research only; compare 100+ future matched races before considering promotion.",
    }


def _outside_head_forward_shadow_report(forecasts, official, alerts, day):
    """11/24+ read-only, official-verified, prospectively frozen 5/6-head A/B.

    DO NOT retrospectively generate alternatives. This is never formal ROI.
    Keep unchanged/no-signal records separate from paired ticket comparisons.
    """
    statuses = Counter()
    exclusions = Counter()
    paired_main, paired_shadow = [], []
    changed_examples = []
    by_venue = defaultdict(lambda: {"formal": [], "outside_shadow": []})
    prospective_frozen = 0
    supported_signals = 0
    for race in forecasts:
        trial = race.get("outside_head_forward_shadow_v1")
        if not isinstance(trial, dict):
            continue
        status = trial.get("status", "UNKNOWN")
        statuses[status] += 1
        supported_signals += len(trial.get("supported_outer_1st_signals") or [])
        if status != "PRE_CUTOFF_SHADOW_SWAP_FROZEN":
            continue
        prospective_frozen += 1
        key = f"{day}|{race.get('venue')}|{race.get('race')}"
        if key in alerts:
            exclusions["official_conflict_or_refund"] += 1
            continue
        ok, reason = _verify_race(race, official.get(key), day)
        if not ok:
            exclusions[reason] += 1
            continue
        control, alternative = trial.get("control_bets"), trial.get("shadow_alternative_bets")
        if (day < "2026-11-24"
                or race.get("ticket_status") != "formal"
                or race.get("phase") != "exhibition"
                or trial.get("version") != "outside-head-5-6-precutoff-shadow-v0.1"
                or trial.get("model_role") != "research_shadow"
                or trial.get("not_formal") is not True
                or trial.get("result_data_used") is not False
                or trial.get("odds_used") is not False
                or trial.get("formal_tickets_changed") is not False
                or trial.get("frozen_at_utc") != race.get("frozen_at_utc")
                or trial.get("cutoff_iso_jst") != race.get("cutoff_iso_jst")
                or not _valid_shadow_tickets(control)
                or not _valid_shadow_tickets(alternative)
                or len(control) != len(alternative)
                or len(control) != len(race["bets"])):
            exclusions["not_independently_frozen_equal_point_pair"] += 1
            continue
        try:
            def sha(payload):
                return hashlib.sha256(json.dumps(
                    payload, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
            if (sha(control) != trial.get("control_bets_sha256")
                    or sha(alternative) != trial.get("shadow_bets_sha256")
                    or _ticket_signature(control) != _ticket_signature(race["bets"])
                    or _ticket_signature(control) == _ticket_signature(alternative)):
                exclusions["control_or_trial_sha_mismatch"] += 1
                continue
            freeze = datetime.fromisoformat(race["frozen_at_utc"])
            cutoff = datetime.fromisoformat(race["cutoff_iso_jst"])
            if (freeze.tzinfo is None or cutoff.tzinfo is None
                    or freeze >= cutoff - timedelta(minutes=2)):
                exclusions["not_frozen_two_minutes_before_cutoff"] += 1
                continue
        except (KeyError, ValueError, TypeError, OverflowError):
            exclusions["invalid_provenance"] += 1
            continue
        payout = official[key]
        formal = _shadow_trial_result(race, control, payout)
        shadow = _shadow_trial_result(race, alternative, payout)
        paired_main.append(formal)
        paired_shadow.append(shadow)
        by_venue[race["venue"]]["formal"].append(formal)
        by_venue[race["venue"]]["outside_shadow"].append(shadow)
        if formal["stage"] != shadow["stage"] or formal["virtual_payout_yen"] != shadow["virtual_payout_yen"]:
            changed_examples.append({
                "venue": race["venue"], "race": race["race"],
                "official_finish": payout["finish"],
                "formal_stage": formal["stage"], "shadow_stage": shadow["stage"],
                "formal_payout_yen": formal["virtual_payout_yen"],
                "shadow_payout_yen": shadow["virtual_payout_yen"],
                "replacement": trial.get("replacement"),
            })
    return {
        "protocol": "forward-frozen-5-6-outside-head-conditional-pair-shadow-v0.1",
        "research_shadow_only": True, "actual_purchase": False,
        "prospective_new_snapshots": sum(statuses.values()),
        "supported_outer_head_signals": supported_signals,
        "precutoff_equal_point_alternatives": prospective_frozen,
        "official_verified_sha_matched_pairs": len(paired_main),
        "status_counts": dict(sorted(statuses.items())),
        "exclusions": dict(sorted(exclusions.items())),
        "formal": _metrics(paired_main),
        "outside_head_shadow": _metrics(paired_shadow),
        "virtual_payout_delta_shadow_minus_formal_yen":
            sum(x["virtual_payout_yen"] for x in paired_shadow) -
            sum(x["virtual_payout_yen"] for x in paired_main),
        "head_misses_recovered": sum(a["stage"] == "head_miss" and b["stage"] != "head_miss"
                                     for a, b in zip(paired_main, paired_shadow)),
        "new_head_misses": sum(a["stage"] != "head_miss" and b["stage"] == "head_miss"
                               for a, b in zip(paired_main, paired_shadow)),
        "second_misses_recovered": sum(a["stage"] == "second_miss" and
                                        b["stage"] not in ("second_miss", "head_miss")
                                        for a, b in zip(paired_main, paired_shadow)),
        "changed_outcome_examples": changed_examples[:12],
        "by_venue": {
            venue: {"formal": _metrics(rows["formal"]),
                    "outside_head_shadow": _metrics(rows["outside_shadow"])}
            for venue, rows in sorted(by_venue.items())
        },
        "not_a_formal_performance_claim": True,
        "warning": "Single-day postrace inspection is not proof of uplift. Only source-time, SHA-verified prospective pairs count.",
    }


def _learned_formal_comparison(forecasts, official, alerts, day):
    """Compare ONLY pre-cutoff official learned main vs same-input old control.

    Use already frozen tickets, never retrofit the learning algorithm to past
    results. Model SHA is necessary to see whether later trained versions win.
    """
    by_sha = defaultdict(lambda: {"learned": [], "control": []})
    by_venue = defaultdict(lambda: {"learned": [], "control": []})
    exclusions = Counter()
    total = 0
    model_meta = {}
    for r in forecasts:
        if r.get("model_version") != "four-factor-learned-v1-conditional-choice-trained":
            continue
        total += 1
        proof = r.get("learned_formal") or {}
        key = f"{day}|{r.get('venue')}|{r.get('race')}"
        if key in alerts:
            exclusions["official_conflict_refund_or_cancel"] += 1
            continue
        eligible, reason = _verify_race(r, official.get(key), day)
        if not eligible:
            exclusions[reason] += 1
            continue
        sha = proof.get("model_sha256")
        control = proof.get("control_bets")
        if (r.get("ticket_status") != "formal"
                or proof.get("model_role") != "formal_primary"
                or proof.get("same_input_same_time") is not True
                or proof.get("same_point_count") is not True
                or proof.get("input_frozen_at_utc") != r.get("frozen_at_utc")
                or proof.get("result_data_used") is not False
                or proof.get("odds_used") is not False
                or not isinstance(sha, str) or len(sha) != 64
                or not isinstance(control, list) or len(control) != len(r["bets"])
                or not _valid_shadow_tickets(control)):
            exclusions["not_proven_paired_formal"] += 1
            continue
        model_meta[sha] = {"trained_through": proof.get("trained_through"),
                           "training_n": proof.get("training_n")}
        pay = official[key]
        main = _shadow_trial_result(r, r["bets"], pay)
        prior = _shadow_trial_result(r, control, pay)
        for dest in (by_sha[sha], by_venue[r["venue"]]):
            dest["learned"].append(main)
            dest["control"].append(prior)
    pairs = [s for group in by_sha.values() for s in group["learned"]]
    old = [s for group in by_sha.values() for s in group["control"]]
    def summary(group):
        main, ctrl = group["learned"], group["control"]
        return {
            "matched_verified_races": len(main),
            "learned_formal": _metrics(main),
            "previous_formal_control": _metrics(ctrl),
            "payout_delta_yen": sum(x["virtual_payout_yen"] for x in main)
                              - sum(x["virtual_payout_yen"] for x in ctrl),
        }
    return {
        "protocol": "forward-frozen-user-authorized-learned-main-vs-old-control-v1",
        "new_learned_forecasts": total,
        "matched_verified_races": len(pairs),
        "learned_formal": _metrics(pairs),
        "previous_formal_control": _metrics(old),
        "by_model_sha": {sha: {**model_meta.get(sha, {}), **summary(grp)}
                         for sha, grp in sorted(by_sha.items())},
        "by_venue": {venue: summary(grp) for venue, grp in sorted(by_venue.items())},
        "exclusions": dict(sorted(exclusions.items())),
        "main_predicted_before_cutoff": True,
        "no_result_used_in_forecast": True,
        "actual_purchase": False,
        "warning": ("Only exhibition-confirmed formal forecasts with official verified "
                    "results and source-matched, pre-cutoff control bets. "
                    "No proof of profitable edge or calibration."),
    }


def _experimental_race_flow_report(forecasts, official, alerts, day):
    """Pre-cutoff saved experiment vs same-time unmodified learned control.

    Results are only joined AFTER official verification; never regenerate old
    predictions or infer payouts for unresolved/cancelled races.
    """
    actual, control = [], []
    cohorts = defaultdict(lambda: {"experiment": [], "control": []})
    excluded = Counter()
    trials = changed = head_switched = 0
    def sha(x):
        return hashlib.sha256(json.dumps(
            x, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()

    for r in forecasts:
        proof = r.get("experimental_race_flow")
        if not isinstance(proof, dict):
            continue
        trials += 1
        if proof.get("formal_component") is not True:
            excluded["no_independent_signal_or_unverified"] += 1
            continue
        key = f"{day}|{r.get('venue')}|{r.get('race')}"
        if key in alerts:
            excluded["official_conflict_or_refund"] += 1
            continue
        eligible, reason = _verify_race(r, official.get(key), day)
        if not eligible:
            excluded[reason] += 1
            continue
        portfolio = r.get("expert_scenario_portfolio_formal")
        # Evaluate the underlying race-flow trial against ITS frozen no-experiment
        # control, not the later expert-portfolio overlay in the final forecast.
        main = (portfolio.get("control_bets") if isinstance(portfolio, dict)
                else r.get("bets"))
        prior = proof.get("same_time_control_bets")
        try:
            good = (
                day >= "2026-11-20"
                and r.get("ticket_status") == "formal"
                and r.get("phase") == "exhibition"
                and r.get("model_version") == "four-factor-learned-v1-conditional-choice-trained"
                and proof.get("version") == "race-flow-head-experiment-v1-20261120-uncalibrated"
                and proof.get("status") == "APPLIED_EXPERIMENTAL_UNCALIBRATED"
                and proof.get("results_used") is False
                and proof.get("odds_used") is False
                and proof.get("calibrated") is False
                and proof.get("no_historical_overwrite") is True
                and proof.get("frozen_at_utc") == r.get("frozen_at_utc")
                and proof.get("same_point_count") is True
                and proof.get("same_virtual_stake_yen") == RESEARCH_BUDGET
                and (r.get("exhibition_input_check") or {}).get("verified_before_freeze") is True
                and (r.get("exhibition_input_check") or {}).get("six_boats_matched") == 6
                and isinstance(main, list) and isinstance(prior, list)
                and len(main) == len(prior)
                and _valid_shadow_tickets(main) and _valid_shadow_tickets(prior)
                and (not isinstance(portfolio, dict)
                     or (portfolio.get("control_bets_sha256") == sha(main)
                         and portfolio.get("alternative_bets_sha256") == sha(r.get("bets"))))
                and isinstance(proof.get("policy_sha256"), str)
                and len(proof["policy_sha256"]) == 64
                and proof.get("control_bets_sha256") == sha(prior)
                and proof.get("experimental_bets_sha256") == sha(main)
                and proof.get("formal_bets_changed") is (
                    _ticket_signature(main) != _ticket_signature(prior))
                and proof.get("first_ticket_head_changed") is (
                    main[0]["combination"][0] != prior[0]["combination"][0])
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            good = False
        if not good:
            excluded["unverifiable_experiment_control"] += 1
            continue
        a = _shadow_trial_result(r, main, official[key])
        b = _shadow_trial_result(r, prior, official[key])
        actual.append(a)
        control.append(b)
        cohorts[r["venue"]]["experiment"].append(a)
        cohorts[r["venue"]]["control"].append(b)
        changed += _ticket_signature(main) != _ticket_signature(prior)
        head_switched += main[0]["combination"][0] != prior[0]["combination"][0]

    def comparison(exp, ctrl):
        return {
            "matched_races": len(exp),
            "experimental_formal": _metrics(exp),
            "same_time_learned_control": _metrics(ctrl),
            "head_misses_recovered": sum(b["stage"] == "head_miss" and a["stage"] != "head_miss"
                                         for a, b in zip(exp, ctrl)),
            "new_head_misses": sum(b["stage"] != "head_miss" and a["stage"] == "head_miss"
                                   for a, b in zip(exp, ctrl)),
            "virtual_payout_delta_yen": sum(x["virtual_payout_yen"] for x in exp) -
                                        sum(x["virtual_payout_yen"] for x in ctrl),
        }
    return {
        "protocol": "experiment-v1-vs-frozen-same-time-no-experiment-control",
        "forward_frozen_experiment_records": trials,
        "verified_formal_ticket_change_races": changed,
        "verified_formal_first_head_change_races": head_switched,
        **comparison(actual, control),
        "by_venue": {venue: comparison(x["experiment"], x["control"])
                     for venue, x in sorted(cohorts.items())},
        "exclusions": dict(sorted(excluded.items())),
        "untrained_and_uncalibrated": True,
        "not_an_actual_purchase": True,
        "no_historical_reconstruction": True,
    }


def _expert_scenario_formal_report(forecasts, official, alerts, day):
    """Official-verified comparison: experimental FORMAL tickets vs frozen control.

    Both ticket sets are actually committed in the same pre-cutoff SHA snapshot,
    same race and same hypothetical ¥50,000 allocation. Historical events are
    never re-forecast or used for score construction.
    """
    before, after = [], []
    by_venue = defaultdict(lambda: {"control": [], "formal": []})
    exclusions = Counter()
    frozen_count = changed = head_added = 0
    def sha(v):
        return hashlib.sha256(json.dumps(
            v, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()

    for row in forecasts:
        proof = row.get("expert_scenario_portfolio_formal")
        if not isinstance(proof, dict):
            continue
        frozen_count += 1
        key = f"{day}|{row.get('venue')}|{row.get('race')}"
        if key in alerts:
            exclusions["refund_conflict_or_cancellation"] += 1
            continue
        ok, reason = _verify_race(row, official.get(key), day)
        if not ok:
            exclusions[reason] += 1
            continue
        main, ctrl = row.get("bets"), proof.get("control_bets")
        try:
            verified = (
                day >= "2026-11-20"
                and row.get("ticket_status") == "formal"
                and row.get("phase") == "exhibition"
                and row.get("model_version") == "four-factor-learned-v1-conditional-choice-trained"
                and proof.get("version") == "expert-scenario-portfolio-formal-experiment-v0.1"
                and proof.get("formal_component") is True
                and proof.get("not_formal") is False
                and proof.get("model_role") == "experimental_formal"
                and proof.get("promotion_basis") == "user_authorized_prospective_experiment"
                and proof.get("source_snapshot_frozen_at_utc") == row.get("frozen_at_utc")
                and proof.get("frozen_at_utc") == row.get("frozen_at_utc")
                and proof.get("same_input_same_time") is True
                and proof.get("same_point_count") is True
                and proof.get("same_virtual_stake_yen") == RESEARCH_BUDGET
                and proof.get("no_odds_used") is True
                and proof.get("no_results_used") is True
                and proof.get("calibrated") is False
                and proof.get("not_real_purchase") is True
                and proof.get("no_historical_forecast_overwrite") is True
                and (row.get("exhibition_input_check") or {}).get("verified_before_freeze") is True
                and (row.get("exhibition_input_check") or {}).get("six_boats_matched") == 6
                and isinstance(main, list) and isinstance(ctrl, list)
                and len(main) == len(ctrl)
                and _valid_shadow_tickets(main) and _valid_shadow_tickets(ctrl)
                and proof.get("control_bets_sha256") == sha(ctrl)
                and proof.get("alternative_bets_sha256") == sha(main)
                and proof.get("bets_modified") is (_ticket_signature(main) != _ticket_signature(ctrl))
            )
        except (TypeError, KeyError, ValueError, OverflowError):
            verified = False
        if not verified:
            exclusions["invalid_or_missing_frozen_pair_evidence"] += 1
            continue
        p = official[key]
        control_result = _shadow_trial_result(row, ctrl, p)
        formal_result = _shadow_trial_result(row, main, p)
        before.append(control_result)
        after.append(formal_result)
        by_venue[row["venue"]]["control"].append(control_result)
        by_venue[row["venue"]]["formal"].append(formal_result)
        changed += _ticket_signature(main) != _ticket_signature(ctrl)
        head_added += {b["combination"][0] for b in main} != {b["combination"][0] for b in ctrl}

    def stats(ctrl, formal):
        return {
            "matched_races": len(formal),
            "same_time_learned_control": _metrics(ctrl),
            "expert_style_experimental_formal": _metrics(formal),
            "head_misses_recovered": sum(
                x["stage"] == "head_miss" and y["stage"] != "head_miss"
                for x, y in zip(ctrl, formal)),
            "new_head_misses": sum(
                x["stage"] != "head_miss" and y["stage"] == "head_miss"
                for x, y in zip(ctrl, formal)),
            "virtual_payout_delta_experiment_minus_control_yen":
                sum(x["virtual_payout_yen"] for x in formal)
                - sum(x["virtual_payout_yen"] for x in ctrl),
        }
    return {
        "protocol": "prospective-verified-expert-portfolio-formal-v01",
        "frozen_formal_experiment_records": frozen_count,
        "matched_ticket_change_races": changed,
        "matched_head_set_change_races": head_added,
        **stats(before, after),
        "by_venue": {venue: stats(rows["control"], rows["formal"])
                     for venue, rows in sorted(by_venue.items())},
        "exclusions": dict(sorted(exclusions.items())),
        "not_an_actual_purchase": True,
        "not_calibrated": True,
        "historical_forecasts_not_recomputed": True,
        "improvement_unproven": True,
    }


def _expert_scenario_portfolio_report(forecasts, official, alerts, day):
    """Freeze-first portfolio study: compare source-proven alternative vs main.

    This never imports third-party picks, copies historical predictions, or
    modifies official forecast performance. Same-time snapshots + result joins.
    """
    frozen = changed = 0
    formal, shadow = [], []
    per_venue = defaultdict(lambda: {"formal": [], "shadow": []})
    exclusions = Counter()
    def sha(value):
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
    for row in forecasts:
        trial = row.get("expert_scenario_portfolio_shadow")
        if not isinstance(trial, dict):
            continue
        frozen += 1
        if trial.get("status") != "PRE_CUTOFF_COUNTER_PATH_FROZEN":
            exclusions["unsupported_or_incomplete_counterpath"] += 1
            continue
        key = f"{day}|{row.get('venue')}|{row.get('race')}"
        if key in alerts:
            exclusions["official_conflict_or_refund"] += 1
            continue
        good_result, reason = _verify_race(row, official.get(key), day)
        if not good_result:
            exclusions[reason] += 1
            continue
        actual, original, candidate = row.get("bets"), trial.get("control_bets"), trial.get("alternative_bets")
        try:
            proof_ok = (
                day >= "2026-11-20"
                and row.get("model_version") == "four-factor-learned-v1-conditional-choice-trained"
                and row.get("ticket_status") == "formal"
                and row.get("phase") == "exhibition"
                and trial.get("version") == "expert-scenario-portfolio-shadow-v0.1"
                and trial.get("model_role") == "research_shadow"
                and trial.get("not_formal") is True
                and trial.get("bets_modified") is False
                and trial.get("no_odds_used") is True
                and trial.get("no_results_used") is True
                and trial.get("calibrated") is False
                and trial.get("comparison_only_no_history_rewrite") is True
                and trial.get("frozen_at_utc") == row.get("frozen_at_utc")
                and trial.get("same_point_count") is True
                and trial.get("virtual_budget_yen_each") == RESEARCH_BUDGET
                and (row.get("exhibition_input_check") or {}).get("verified_before_freeze") is True
                and (row.get("exhibition_input_check") or {}).get("six_boats_matched") == 6
                and isinstance(actual, list) and isinstance(original, list)
                and isinstance(candidate, list)
                and len(actual) == len(original) == len(candidate)
                and _valid_shadow_tickets(actual) and _valid_shadow_tickets(original)
                and _valid_shadow_tickets(candidate)
                and _ticket_signature(actual) == _ticket_signature(original)
                and trial.get("control_bets_sha256") == sha(original)
                and trial.get("alternative_bets_sha256") == sha(candidate)
                and trial.get("ticket_or_allocation_changed") is (
                    _ticket_signature(actual) != _ticket_signature(candidate))
            )
        except (TypeError, KeyError, ValueError, OverflowError):
            proof_ok = False
        if not proof_ok:
            exclusions["unverified_or_changed_control"] += 1
            continue
        p = official[key]
        m = _shadow_trial_result(row, original, p)
        a = _shadow_trial_result(row, candidate, p)
        formal.append(m)
        shadow.append(a)
        per_venue[row["venue"]]["formal"].append(m)
        per_venue[row["venue"]]["shadow"].append(a)
        changed += _ticket_signature(original) != _ticket_signature(candidate)
    def compare(a, b):
        return {
            "matched_races": len(a),
            "existing_formal": _metrics(a),
            "expert_style_research": _metrics(b),
            "head_misses_recovered": sum(x["stage"] == "head_miss" and y["stage"] != "head_miss"
                                         for x, y in zip(a, b)),
            "new_head_misses": sum(x["stage"] != "head_miss" and y["stage"] == "head_miss"
                                   for x, y in zip(a, b)),
            "virtual_payout_delta_research_minus_formal_yen":
                sum(x["virtual_payout_yen"] for x in b) -
                sum(x["virtual_payout_yen"] for x in a),
        }
    return {
        "protocol": "expert-inspired-scenario-portfolio-precutoff-shadow-v01",
        "frozen_research_records": frozen,
        "changed_ticket_or_stake_pairs": changed,
        **compare(formal, shadow),
        "by_venue": {v: compare(rows["formal"], rows["shadow"])
                     for v, rows in sorted(per_venue.items())},
        "exclusions": dict(sorted(exclusions.items())),
        "not_formal": True,
        "no_proven_accuracy_or_roi_gain": True,
        "no_hindsight_reconstruction": True,
    }


def _third_place_pilot_report(forecasts, official, alerts, day):
    """Read-only matched comparison for an actually frozen third-place pilot.

    No hindsight construction. Only official-settled, six-boat exhibition-
    verified formal forecasts can count. Both selections have the same points,
    same race, same time, and independent virtual 50,000 yen per model.
    """
    formal, trial = [], []
    groups = defaultdict(lambda: {"formal": [], "trial": []})
    exclusions = Counter()
    changed = 0
    common_pair = 0
    common_pair_formal_hit = 0
    common_pair_trial_hit = 0
    candidates = 0

    def signed_hash(x):
        return hashlib.sha256(json.dumps(
            x, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()

    for r in forecasts:
        shadow = r.get("third_place_pilot")
        if not isinstance(shadow, dict):
            continue
        candidates += 1
        key = f"{day}|{r.get('venue')}|{r.get('race')}"
        if key in alerts:
            exclusions["official_refund_conflict_or_cancellation"] += 1
            continue
        eligible, reason = _verify_race(r, official.get(key), day)
        if not eligible:
            exclusions[reason] += 1
            continue
        proof = r.get("learned_formal") or {}
        sb = shadow.get("bets")
        try:
            good = (
                r.get("model_version") == "four-factor-learned-v1-conditional-choice-trained"
                and r.get("ticket_status") == "formal"
                and r.get("phase") == "exhibition"
                and (r.get("exhibition_input_check") or {}).get("verified_before_freeze") is True
                and proof.get("model_role") == "formal_primary"
                and shadow.get("version") == "third-place-context-v0.1-research-only"
                and shadow.get("model_role") == "research_shadow"
                and shadow.get("not_formal") is True
                and shadow.get("no_additional_stake") is True
                and shadow.get("formal_bets_unchanged") is True
                and shadow.get("same_race_same_time") is True
                and shadow.get("same_point_count") is True
                and shadow.get("calibrated") is False
                and shadow.get("result_data_used") is False
                and shadow.get("odds_used") is False
                and shadow.get("actual_1m_maneuver_observed") is False
                and shadow.get("virtual_budget_per_model_yen") == RESEARCH_BUDGET
                and shadow.get("frozen_at_utc") == r.get("frozen_at_utc")
                and shadow.get("parent_model_sha256") == proof.get("model_sha256")
                and isinstance(shadow.get("pilot_model_sha256"), str)
                and len(shadow["pilot_model_sha256"]) == 64
                and shadow.get("trained_through") < day
                and shadow.get("source_main_bets_sha256") == signed_hash({"bets": r["bets"]})
                and _valid_shadow_tickets(sb)
                and len(sb) == len(r["bets"])
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            good = False
        if not good:
            exclusions["invalid_unmatched_or_unverified_shadow"] += 1
            continue
        pay = official[key]
        main = _shadow_trial_result(r, r["bets"], pay)
        pilot = _shadow_trial_result(r, sb, pay)
        formal.append(main)
        trial.append(pilot)
        groups[r["venue"]]["formal"].append(main)
        groups[r["venue"]]["trial"].append(pilot)
        changed += _ticket_signature(r["bets"]) != _ticket_signature(sb)
        pair = "-".join(pay["finish"].split("-")[:2])
        both_have_pair = (
            any(b["combination"].startswith(pair+"-") for b in r["bets"])
            and any(b["combination"].startswith(pair+"-") for b in sb)
        )
        if both_have_pair:
            common_pair += 1
            common_pair_formal_hit += main["stage"] == "hit"
            common_pair_trial_hit += pilot["stage"] == "hit"

    def summarize(items):
        f, t = items["formal"], items["trial"]
        return {
            "paired_verified_races": len(f),
            "learned_formal": _metrics(f),
            "third_place_trial": _metrics(t),
            "virtual_payout_delta_yen": (
                sum(x["virtual_payout_yen"] for x in t)
                - sum(x["virtual_payout_yen"] for x in f)
            ),
        }

    return {
        "protocol": "frozen-third-v01-vs-learned-formal-same-race-same-time",
        "source": "pre-cutoff SHA-frozen trial + verified official 3連単 result",
        "trial_not_formal": True,
        "actual_purchase": False,
        "candidate_trial_races": candidates,
        "paired_verified_races": len(formal),
        "changed_bets_or_allocation_races": changed,
        "learned_formal": _metrics(formal),
        "third_place_trial": _metrics(trial),
        "shared_correct_head_second_opportunities": common_pair,
        "shared_pair_main_third_hits": common_pair_formal_hit,
        "shared_pair_trial_third_hits": common_pair_trial_hit,
        "by_venue": {
            venue: summarize(g) for venue, g in sorted(groups.items())
        },
        "exclusions": dict(sorted(exclusions.items())),
        "warning": (
            "Trial is never the formal ticket; pair-specific conditional "
            "third accuracy is only calculated for shared eligible 1st/2nd "
            "pairs. Geometric inputs are pre-race proxies, not observed "
            "maneuvers. No result-based backfill or ticket modification."
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


def _coverage_reselection_forward_report(forecasts, official, alerts, day):
    """Equal-point formal vs immutable PRE-CUTOFF coverage shadow; never refit."""
    formal, trial = [], []
    venues = defaultdict(lambda: {"formal": [], "trial": []})
    groups = defaultdict(lambda: {"formal": [], "trial": []})
    states = Counter()
    exclusions = Counter()
    proposed = 0
    for snapshot in forecasts:
        s = snapshot.get("coverage_reselection_shadow")
        if not isinstance(s, dict):
            continue
        states[str(s.get("status", "UNKNOWN"))] += 1
        if s.get("status") != "PROPOSED_FOR_FORWARD_TEST_ONLY":
            continue
        proposed += 1
        key = f"{day}|{snapshot['venue']}|{snapshot['race']}"
        if key in alerts:
            exclusions["official_refund_or_conflict"] += 1
            continue
        valid, why = _verify_race(snapshot, official.get(key), day)
        if not valid:
            exclusions["official_" + why] += 1
            continue
        if (snapshot.get("ticket_status") != "formal"
                or snapshot.get("phase") != "exhibition"
                or snapshot.get("model_version") !=
                "four-factor-v2.3-conditional-second-primary-untrained"
                or s.get("version") != "coverage-reselection-shadow-v0.1-untrained"
                or s.get("model_role") != "research_shadow"
                or s.get("not_formal") is not True
                or s.get("no_additional_stake") is not True
                or s.get("results_used") is not False
                or s.get("odds_used") is not False
                or s.get("formal_bets_unchanged") is not True
                or s.get("same_point_count") is not True
                or s.get("point_count_matched") is not True
                or s.get("actual_ticket_or_allocation_change") is not True
                or s.get("frozen_at_utc") != snapshot.get("frozen_at_utc")):
            exclusions["invalid_pre_cutoff_provenance"] += 1
            continue
        base = snapshot.get("bets")
        alternative = s.get("forecast_alternative_bets")
        if (not _valid_shadow_tickets(base) or not _valid_shadow_tickets(alternative)
                or len(base) != len(alternative)):
            exclusions["invalid_budget_or_points"] += 1
            continue
        meta = snapshot.get("interaction_primary")
        if not isinstance(meta, dict):
            exclusions["missing_ranked_source"] += 1
            continue
        source = {"ranked": meta.get("ranked_outcomes"),
                  "formal_bets": base, "scenarios": meta.get("scenario_assumptions")}
        if not isinstance(source["ranked"], list) or len(source["ranked"]) != 120:
            exclusions["missing_ranked_source"] += 1
            continue
        def sha(data):
            return hashlib.sha256(json.dumps(
                data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
        if (s.get("formal_bets_sha256") != sha({"bets": base})
                or s.get("source_input_sha256") != sha(source)):
            exclusions["input_sha_mismatch"] += 1
            continue
        paid = official[key]
        a = _shadow_trial_result(snapshot, base, paid)
        b = _shadow_trial_result(snapshot, alternative, paid)
        formal.append(a)
        trial.append(b)
        venues[snapshot["venue"]]["formal"].append(a)
        venues[snapshot["venue"]]["trial"].append(b)
        category = str(s.get("replacement", {}).get("coverage_kind", "unclassified"))
        groups[category]["formal"].append(a)
        groups[category]["trial"].append(b)
    def table(source):
        return {
            name: {"formal": _metrics(rows["formal"]),
                   "research_shadow": _metrics(rows["trial"])}
            for name, rows in sorted(source.items())
        }
    return {
        "protocol": "same-frozen-input-coverage-shadow-v0.1-vs-formal-v2.3",
        "not_formal_performance": True,
        "no_backfilled_counterfactuals": True,
        "same_point_count_and_50000yen": True,
        "generated_status_counts": dict(sorted(states.items())),
        "frozen_proposals": proposed,
        "official_verified_sha_matched_pairs": len(formal),
        "formal_v23": _metrics(formal),
        "research_shadow": _metrics(trial),
        "head_misses_recovered": sum(a["stage"] == "head_miss"
                                    and b["stage"] != "head_miss"
                                    for a, b in zip(formal, trial)),
        "new_head_misses": sum(a["stage"] != "head_miss"
                               and b["stage"] == "head_miss"
                               for a, b in zip(formal, trial)),
        "second_misses_recovered": sum(a["stage"] == "second_miss"
                                       and b["stage"] in ("hit", "third_miss")
                                       for a, b in zip(formal, trial)),
        "by_venue": table(venues),
        "by_coverage_kind": table(groups),
        "exclusions": dict(sorted(exclusions.items())),
        "warning": ("Model-only hypothetical path support is not an observed "
                    "win condition. Do not infer hit/ROI improvement before "
                    ">=100 independent pre-cutoff matched races and venue splits."),
    }


def _hidden_path_forward_report(forecasts, official, alerts, day):
    """Compare only already-frozen equal-point research swaps with official payouts."""
    baseline, alternative = [], []
    by_venue = defaultdict(lambda: {"formal": [], "research": []})
    by_scenario = defaultdict(lambda: {"formal": [], "research": []})
    statuses, exclusions = Counter(), Counter()
    for r in forecasts:
        shadow = r.get("hidden_path_shadow")
        if not isinstance(shadow, dict):
            continue
        status = shadow.get("status", "unknown")
        statuses[status] += 1
        if status != "PRE_CUTOFF_SHADOW_SWAP_ONLY":
            continue
        key = f"{day}|{r['venue']}|{r['race']}"
        if key in alerts:
            exclusions["official_refund_or_conflict"] += 1
            continue
        ok, why = _verify_race(r, official.get(key), day)
        if not ok:
            exclusions["official_" + why] += 1
            continue
        formal = r.get("bets")
        control = shadow.get("formal_control_bets")
        trial = shadow.get("shadow_alternative_bets")
        if (r.get("ticket_status") != "formal"
                or r.get("phase") != "exhibition"
                or shadow.get("model_role") != "research_shadow"
                or shadow.get("not_formal") is not True
                or shadow.get("no_additional_stake") is not True
                or shadow.get("result_data_used") is not False
                or shadow.get("odds_used") is not False
                or shadow.get("frozen_at_utc") != r.get("frozen_at_utc")
                or shadow.get("same_point_count") is not True
                or shadow.get("same_virtual_budget_yen") != RESEARCH_BUDGET
                or not isinstance(shadow.get("formal_bets_sha256"), str)
                or not isinstance(shadow.get("ranked_source_sha256"), str)
                or shadow.get("formal_bets_sha256") != hashlib.sha256(
                    json.dumps({"bets": formal}, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")).hexdigest()
                or not _valid_shadow_tickets(formal)
                or not _valid_shadow_tickets(control)
                or not _valid_shadow_tickets(trial)
                or len(formal) != len(trial)
                or _ticket_signature(formal) != _ticket_signature(control)):
            exclusions["invalid_or_unmatched_pre_cutoff_control"] += 1
            continue
        main_row = _shadow_trial_result(r, formal, official[key])
        trial_row = _shadow_trial_result(r, trial, official[key])
        baseline.append(main_row)
        alternative.append(trial_row)
        by_venue[r["venue"]]["formal"].append(main_row)
        by_venue[r["venue"]]["research"].append(trial_row)
        candidate = shadow.get("replacement_candidate")
        evidence = next((x for x in shadow.get("candidates", [])
                         if x.get("combination") == candidate), {})
        group = evidence.get("scenario", "OTHER_UNVERIFIED_SCENARIO")
        by_scenario[group]["formal"].append(main_row)
        by_scenario[group]["research"].append(trial_row)
    def grouped(source):
        return {name: {"formal": _metrics(x["formal"]),
                       "research_shadow": _metrics(x["research"])}
                for name, x in sorted(source.items())}
    return {
        "protocol": "pre_cutoff_hidden_1m_v01_vs_same_snapshot_formal",
        "not_formal_performance": True,
        "no_backfilled_counterfactuals": True,
        "same_point_count_and_50000yen": True,
        "status_counts": dict(sorted(statuses.items())),
        "official_verified_equal_point_pairs": len(baseline),
        "formal": _metrics(baseline),
        "research_shadow": _metrics(alternative),
        "head_misses_recovered": sum(a["stage"] == "head_miss" and
                                    b["stage"] != "head_miss"
                                    for a, b in zip(baseline, alternative)),
        "new_head_misses": sum(a["stage"] != "head_miss" and
                              b["stage"] == "head_miss"
                              for a, b in zip(baseline, alternative)),
        "second_misses_recovered": sum(a["stage"] == "second_miss" and
                                      b["stage"] in ("hit", "third_miss")
                                      for a, b in zip(baseline, alternative)),
        "new_second_misses": sum(a["stage"] != "second_miss" and
                                b["stage"] == "second_miss"
                                for a, b in zip(baseline, alternative)),
        "by_venue": grouped(by_venue),
        "by_scenario": grouped(by_scenario),
        "exclusions": dict(sorted(exclusions.items())),
        "warning": ("Hypothesized maneuvers are not observed; do not promote "
                    "without >=100 independent matched races plus venue splits. "
                    "Both gains and newly introduced misses must be reported."),
    }


def _formal_v24_forward_report(forecasts, official, alerts, day):
    """Official-only v2.4 vs pre-cutoff same-input frozen v2.3 controls."""
    trial, old = [], []
    excluded = Counter()
    by_venue = defaultdict(lambda: {"trial": [], "old": []})
    generated = 0
    for r in forecasts:
        proof = r.get("formal_insight_v24")
        if not isinstance(proof, dict) or proof.get("formal_component") is not True:
            continue
        generated += 1
        key = f"{day}|{r['venue']}|{r['race']}"
        if key in alerts:
            excluded["official_refund_or_conflict"] += 1
            continue
        eligible, reason = _verify_race(r, official.get(key), day)
        if not eligible:
            excluded["official_" + reason] += 1
            continue
        control = proof.get("control_bets")
        if (r.get("model_version") != "four-factor-v2.4-entry-exhibition-balance-untrained"
                or r.get("ticket_status") != "formal"
                or r.get("phase") != "exhibition"
                or proof.get("pre_cutoff_only") is not True
                or proof.get("result_data_used") is not False
                or proof.get("odds_used") is not False
                or proof.get("no_additional_stake") is not True
                or proof.get("old_control_result_data_used") is not False
                or proof.get("frozen_at_utc") != r.get("frozen_at_utc")
                or proof.get("control_frozen_at_utc") != r.get("frozen_at_utc")
                or not isinstance(proof.get("main_ranked_sha256"), str)
                or not isinstance(proof.get("control_ranked_sha256"), str)):
            excluded["missing_forward_provenance"] += 1
            continue
        if (not _valid_shadow_tickets(control)
                or not _valid_shadow_tickets(r.get("bets"))
                or proof.get("same_point_count") is not True
                or len(control) != len(r["bets"])):
            excluded["not_equal_point_count_or_invalid_budget"] += 1
            continue
        alt = _shadow_trial_result(r, r["bets"], official[key])
        base = _shadow_trial_result(r, control, official[key])
        trial.append(alt)
        old.append(base)
        by_venue[r["venue"]]["trial"].append(alt)
        by_venue[r["venue"]]["old"].append(base)
    return {
        "protocol": "forward_frozen_v24_vs_same_time_v23",
        "generated_before_official_reconciliation": generated,
        "official_verified_equal_point_pairs": len(trial),
        "formal_v24": _metrics(trial),
        "frozen_v23_control_not_formal": _metrics(old),
        "by_venue": {
            venue: {"formal_v24": _metrics(rows["trial"]),
                    "frozen_v23_control_not_formal": _metrics(rows["old"])}
            for venue, rows in sorted(by_venue.items())
        },
        "exclusions": dict(sorted(excluded.items())),
        "historical_forecasts_immutable": True,
        "not_calibrated": True,
        "note": "Same 50000 yen, point-count-matched, freeze-first. >=100 prospective races before accuracy claims.",
    }


def _formal_v25_forward_report(forecasts, official, alerts, day):
    """Official-only, same-time v2.5 vs frozen v2.4, no hindsight."""
    trial, old = [], []
    excluded = Counter()
    by_venue = defaultdict(lambda: {"trial": [], "old": []})
    generated = 0
    changed = 0
    for r in forecasts:
        proof = r.get("formal_head_risk_v25")
        if not isinstance(proof, dict) or proof.get("formal_component") is not True:
            continue
        generated += 1
        changed += int(proof.get("actual_ticket_or_allocation_changed") is True)
        key = f"{day}|{r['venue']}|{r['race']}"
        if key in alerts:
            excluded["official_refund_or_conflict"] += 1
            continue
        eligible, reason = _verify_race(r, official.get(key), day)
        if not eligible:
            excluded["official_" + reason] += 1
            continue
        control = proof.get("control_bets")
        if (r.get("model_version") != "four-factor-v2.5-evidence-head-switch-untrained"
                or r.get("ticket_status") != "formal"
                or r.get("phase") != "exhibition"
                or proof.get("pre_cutoff_only") is not True
                or proof.get("result_data_used") is not False
                or proof.get("odds_used") is not False
                or proof.get("no_additional_stake") is not True
                or proof.get("frozen_at_utc") != r.get("frozen_at_utc")
                or proof.get("control_frozen_at_utc") != r.get("frozen_at_utc")
                or proof.get("prior_model") != "four-factor-v2.4-entry-exhibition-balance-untrained"
                or not isinstance(proof.get("control_ranked_sha256"), str)
                or not isinstance(proof.get("main_ranked_sha256"), str)):
            excluded["missing_forward_provenance"] += 1
            continue
        if (not _valid_shadow_tickets(control)
                or not _valid_shadow_tickets(r.get("bets"))
                or proof.get("same_point_count") is not True
                or len(control) != len(r["bets"])):
            excluded["not_equal_point_count_or_invalid_budget"] += 1
            continue
        alt = _shadow_trial_result(r, r["bets"], official[key])
        base = _shadow_trial_result(r, control, official[key])
        trial.append(alt)
        old.append(base)
        by_venue[r["venue"]]["trial"].append(alt)
        by_venue[r["venue"]]["old"].append(base)
    return {
        "protocol": "forward_frozen_v25_vs_same_time_v24",
        "generated_before_official_reconciliation": generated,
        "actual_ticket_or_allocation_changes": changed,
        "official_verified_equal_point_pairs": len(trial),
        "formal_v25": _metrics(trial),
        "frozen_v24_control_not_formal": _metrics(old),
        "by_venue": {
            venue: {"formal_v25": _metrics(rows["trial"]),
                    "frozen_v24_control_not_formal": _metrics(rows["old"])}
            for venue, rows in sorted(by_venue.items())
        },
        "exclusions": dict(sorted(excluded.items())),
        "historical_forecasts_immutable": True,
        "not_calibrated": True,
        "note": "Same stake and point count; evaluate >=100 prospective matched races and venue splits before accuracy claims.",
    }


def analyze(dataset: dict):
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
    report["head_focus_learning"] = inspect_head_focus(raw, verified)
    report["venue_weather_learning"] = inspect_venue_weather(raw, verified)
    if day >= "2026-11-10":
        report["head_risk_breakpoint"] = _head_risk_breakpoint_report(raw, verified, day)
    report["outside_head_forward_shadow_comparison"] = _outside_head_forward_shadow_report(
        raw, official, alerts, day
    )
    report["learned_formal_comparison"] = _learned_formal_comparison(
        raw, official, alerts, day
    )
    report["expert_scenario_portfolio_comparison"] = _expert_scenario_portfolio_report(
        raw, official, alerts, day
    )
    report["expert_scenario_formal_comparison"] = _expert_scenario_formal_report(
        raw, official, alerts, day
    )
    report["experimental_race_flow_comparison"] = _experimental_race_flow_report(
        raw, official, alerts, day
    )
    report["learned_exhibition_effect_comparison"] = _learned_exhibition_effect_report(
        raw, official, alerts, day
    )
    report["learned_conditional_shadow_comparison"] = _learned_conditional_shadow_report(
        raw, official, alerts, day
    )
    report["third_place_pilot_comparison"] = _third_place_pilot_report(
        raw, official, alerts, day
    )
    report["venue_metric_ablation"] = _venue_metric_ablation_report(
        raw, official, alerts, day
    )
    report["three_leg_primary_comparison"] = _three_leg_primary_report(
        raw, official, alerts, day
    )
    report["formal_v24_forward_comparison"] = (
        _formal_v24_forward_report(raw, official, alerts, day)
    )
    report["formal_v25_forward_comparison"] = (
        _formal_v25_forward_report(raw, official, alerts, day)
    )
    report["coverage_reselection_forward_comparison"] = (
        _coverage_reselection_forward_report(raw, official, alerts, day)
    )
    report["hidden_path_forward_comparison"] = (
        _hidden_path_forward_report(raw, official, alerts, day)
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
