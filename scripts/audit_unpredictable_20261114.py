"""Read-only retrospective study of all frozen November 14 race decisions.

Risk labels depend ONLY on pre-cutoff snapshots. Official results are read
AFTERWARDS to evaluate missed heads/pairs/thirds. SKIP_SHADOW does not alter
historical records, formal bets, results, stakes, or production classifications.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from scripts.forecast_audit import _verify_race, _metrics
from scripts.uncertainty_gate_research import VERSION, evaluate

BUDGET = 50_000


def study(ledger: dict, baseline_audit: dict | None = None) -> dict:
    day = ledger["event_date"]
    rows = []
    withheld = Counter()
    by_cause = defaultdict(list)
    for key, rec in sorted((ledger.get("race_records") or {}).items()):
        versions = rec.get("versions") or []
        if not versions:
            withheld["no_frozen_snapshot"] += 1
            continue
        snap = versions[-1]
        if rec.get("official_conflict") or rec.get("official_review"):
            withheld["official_conflict_or_review"] += 1
            continue
        pay = rec.get("official_pay")
        raw = dict(snap)
        raw.setdefault("venue", rec.get("venue"))
        raw.setdefault("race", rec.get("race"))
        raw.setdefault("cutoff_jst", rec.get("cutoff_jst"))
        valid, reason = _verify_race(raw, {**pay, "virtual_stake": BUDGET} if isinstance(pay, dict) else None, day)
        if not valid:
            withheld[reason] += 1
            continue
        finish = pay["finish"]
        bets = raw["bets"]
        matched = next((b for b in bets if b["combination"] == finish), None)
        heads = {b["combination"][0] for b in bets}
        pairs = {b["combination"][:3] for b in bets}
        stage = ("hit" if matched else
                 "head_miss" if finish[0] not in heads else
                 "second_miss" if finish[:3] not in pairs else "third_miss")
        payout = matched["virtual_yen"] * pay["payout_per_100"] // 100 if matched else 0
        risk = evaluate(raw)  # no post-race fields are provided by evaluate
        row = {
            "venue": raw["venue"], "race": raw["race"], "stage": stage,
            "actual_finish": finish, "first_bet_head": bets[0]["combination"][0],
            "model_version": raw.get("model_version"),
            "phase": raw.get("phase"),
            "frozen_at_utc": raw.get("frozen_at_utc"),
            "snapshot_sha256": raw.get("sha256"),
            "risk_status": risk["status"],
            "risk_points": risk.get("risk_points", 0),
            "risk_signals": risk.get("signals", {}),
            "virtual_stake_yen": BUDGET,
            "virtual_payout_yen": payout,
            "payout_per_100": pay["payout_per_100"],
        }
        rows.append(row)
        by_cause[risk["status"]].append(row)

    all_metrics = _metrics(rows)
    groups = {k: _metrics(v) for k, v in sorted(by_cause.items())}
    stages = {
        cause: dict(sorted(Counter(r["stage"] for r in group).items()))
        for cause, group in sorted(by_cause.items())
    }
    audit_confirmation = None
    if baseline_audit:
        target = baseline_audit["metrics"]
        audit_confirmation = {
            k: (all_metrics[k] == target[k])
            for k in ("verified_races", "hits", "head_miss", "second_miss",
                      "third_miss", "virtual_payout_yen")
        }
    return {
        "version": VERSION,
        "event_date": day,
        "source": "immutable daily ledger, source-held pre-race signals and verified official settlement",
        "experimental_not_formal": True,
        "no_ticket_or_record_modifications": True,
        "historical_label_leakage": False,
        "historical_selection_bias_warning": (
            "A retrospective gate performance is not forward validation; do not "
            "claim improvement or automatically remove any race from formal stats."
        ),
        "cohort_policy": {
            "KEEP_SHADOW": "low-signal comparison group, not proven predictable",
            "WATCH_SHADOW": "uncertain cohort: forward comparison",
            "SKIP_SHADOW": "high-risk trial group, separately audited; do not exclude from training or formal forecasts yet",
            "HOLD_*": "unusable/incomplete pre-cutoff exhibition evidence",
        },
        "all_eligible": all_metrics,
        "by_predetermined_risk": groups,
        "by_risk_and_failure_stage": stages,
        "excluded_from_official_comparison": dict(sorted(withheld.items())),
        "audit_reconciliation": audit_confirmation,
        "loss_cases": [
            {k: r[k] for k in (
                "venue", "race", "stage", "actual_finish", "first_bet_head",
                "risk_status", "risk_points", "risk_signals",
                "payout_per_100", "snapshot_sha256"
            )} for r in rows if r["stage"] != "hit"
        ],
        "keep_cohort": [{"venue":r["venue"],"race":r["race"]}
                        for r in by_cause.get("KEEP_SHADOW", [])],
        "next_validation": (
            "At least 100 independently pre-cutoff frozen common eligible races; "
            "compare per-group hit rate, ROI, lost winning cases and exclusion cost."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default="2026-11-14")
    parser.add_argument("--data-dir", type=Path, default=Path("app/data/live"))
    parser.add_argument("--out", type=Path, default=Path("/tmp/boatlabs_uncertainty_research.json"))
    args = parser.parse_args()
    ledger_path = args.data_dir / (args.day + ".json")
    audit_path = args.data_dir / "audit" / (args.day + ".json")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else None
    report = study(ledger, audit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trimmed = {k: v for k, v in report.items() if k not in ("loss_cases", "keep_cohort")}
    print("AUDIT_SUMMARY_JSON=" + json.dumps(trimmed, ensure_ascii=False))
    print("LOSS_CASES_JSON=" + json.dumps(report["loss_cases"], ensure_ascii=False))
    assert report["audit_reconciliation"] is None or all(report["audit_reconciliation"].values()), (
        "Research settle output differs from official existing audit. Do not use data until reconciled."
    )


if __name__ == "__main__":
    main()
