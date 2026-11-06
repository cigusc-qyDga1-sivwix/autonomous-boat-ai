"""Read-only strict prospective G1 parity shadow audit, not an optimizer.

Only uses exact pre-cutoff SHA-frozen main and G1 trial tickets, verified official
pay; G1 vs general *cohort* comparisons are descriptive and confounded by
venue, race number, entrants and date. No historical shadow reconstruction.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from scripts.audit_attack_defence_shadow import metrics, ticket_result, time_bucket
from scripts.forecast_audit import RESEARCH_BUDGET, _verify_race


def valid_trial(snapshot):
    trial = snapshot.get("grade_competition_shadow")
    if not isinstance(trial, dict):
        return False, "no_forward_g1_trial"
    grade = snapshot.get("grade_context") or {}
    if not (
        grade.get("grade_number") == 2
        and grade.get("status") == "SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK"
        and trial.get("grade_number") == 2
        and trial.get("model_role") == "shadow_validation"
        and trial.get("status") == "BOUNDED_G1_PARITY_HYPOTHESIS"
        and trial.get("not_formal") is True
        and trial.get("no_additional_stake") is True
        and trial.get("result_data_used") is False
        and trial.get("frozen_at_utc") == snapshot.get("frozen_at_utc")
        and trial.get("point_count_matched") is True
        and snapshot.get("phase") == "exhibition"
    ):
        return False, "invalid_grade_or_trial_provenance"
    main, alt = snapshot.get("bets"), trial.get("forecast_alternative_bets")
    if not isinstance(main, list) or not isinstance(alt, list) or len(main) != len(alt):
        return False, "unmatched_point_count"
    for bets in (main, alt):
        if not 4 <= len(bets) <= 24 or len(set(x.get("combination") for x in bets)) != len(bets):
            return False, "invalid_bets"
        if not all(
            type(x.get("virtual_yen")) is int and x["virtual_yen"] >= 1000
            and x["virtual_yen"] % 1000 == 0 for x in bets
        ) or sum(b["virtual_yen"] for b in bets) != RESEARCH_BUDGET:
            return False, "invalid_stakes"
    return True, "ready"


def analyze(ledger):
    day = ledger["event_date"]
    rows, excluded = [], Counter()
    for record in (ledger.get("race_records") or {}).values():
        versions = record.get("versions") or []
        if not versions:
            excluded["no_frozen_main"] += 1
            continue
        snapshot = versions[-1]
        valid, reason = valid_trial(snapshot)
        if not valid:
            excluded[reason] += 1
            continue
        if record.get("official_review") or record.get("official_conflict"):
            excluded["official_review_or_conflict"] += 1
            continue
        pay = record.get("official_pay")
        view = {**pay, "virtual_stake": RESEARCH_BUDGET} if isinstance(pay, dict) else None
        verified, reason = _verify_race(snapshot, view, day)
        if not verified:
            excluded[reason] += 1
            continue
        finish, payout = pay["finish"], pay["payout_per_100"]
        rows.append({
            "venue": snapshot["venue"],
            "race": snapshot["race"],
            "time_bucket": time_bucket(snapshot["cutoff_jst"]),
            "grade": snapshot["grade_context"]["grade"],
            "main": ticket_result(snapshot["bets"], finish, payout),
            "shadow": ticket_result(snapshot["grade_competition_shadow"]["forecast_alternative_bets"], finish, payout)
        })
    def grouped(key):
        return {v: metrics([r for r in rows if r[key] == v])
                for v in sorted({r[key] for r in rows})}
    return {
        "date": day,
        "method": "only_same_race_same_pre_cutoff_SHA_same_point_count_G1_v2.2_vs_shadow",
        "total": metrics(rows),
        "by_time": grouped("time_bucket"),
        "by_venue": grouped("venue"),
        "exclusions": dict(excluded),
        "notes": [
            "Only matched prospectively frozen paired predictions count.",
            "Missing exhibition or missing grade is excluded, not treated as loss.",
            "G1-specific adjustment is not trained, causal, or calibrated.",
            "Other grade groups require a separate descriptive stratified audit.",
            "No historical 11/5 or 11/6 results used to select the model.",
            "No formal predictions or historical SHA altered.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    result = analyze(json.loads(args.ledger.read_text(encoding="utf-8")))
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        if args.out.resolve() == args.ledger.resolve():
            raise ValueError("Refusing to overwrite immutable original ledger")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
