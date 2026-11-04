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
    )
    if r.get("model_version") == "four-factor-v2.1-actual-entry-primary-untrained":
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
        "by_points": _group(verified, "points"),
        "by_venue": _group(verified, "venue"),
        "exclusions": dict(exclusions),
        "unhit_examples": race_examples[:30],
    }
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
