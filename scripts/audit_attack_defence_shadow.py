"""Read-only same-race forward A/B of pre-cutoff attack/defence shadow.

Reads only pre-existing SHA-fixed main predictions and verified official pay.
No reconstruction, late rescore, bet changes, or backfilled trial tickets.
The branch can be run per completed JST date; reports afternoon venue slices.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from scripts.forecast_audit import RESEARCH_BUDGET, _verify_race


def ticket_result(bets, finish, payout_per_100):
    exact = next((x for x in bets if x.get("combination") == finish), None)
    stage = ("hit" if exact else
             "head_miss" if finish[0] not in {x["combination"][0] for x in bets} else
             "second_miss" if finish[:3] not in {x["combination"][:3] for x in bets} else
             "third_miss")
    paid = int(exact["virtual_yen"] * payout_per_100 // 100) if exact else 0
    return {"hit": bool(exact), "stage": stage, "paid": paid}


def metrics(rows):
    n = len(rows)
    main = [r["main"] for r in rows]
    trial = [r["shadow"] for r in rows]
    def item(subset):
        return {"hits": sum(r["hit"] for r in subset),
                "hit_rate": round(sum(r["hit"] for r in subset)/n, 5) if n else None,
                "return_rate": round(sum(r["paid"] for r in subset)/(RESEARCH_BUDGET*n), 5) if n else None,
                "virtual_payout_yen": sum(r["paid"] for r in subset),
                "head_miss": sum(r["stage"] == "head_miss" for r in subset),
                "second_miss": sum(r["stage"] == "second_miss" for r in subset),
                "third_miss": sum(r["stage"] == "third_miss" for r in subset)}
    return {"matched_races": n, "same_point_count": True,
            "main": item(main), "shadow": item(trial),
            "main_head_misses_recovered": sum(r["main"]["stage"] == "head_miss" and
                                              r["shadow"]["stage"] != "head_miss" for r in rows),
            "new_shadow_head_misses": sum(r["main"]["stage"] != "head_miss" and
                                         r["shadow"]["stage"] == "head_miss" for r in rows)}


def time_bucket(cutoff_hm):
    hour = int(cutoff_hm[:2])
    return "before_12" if hour < 12 else "12_to_15" if hour < 15 else "15_to_18" if hour < 18 else "after_18"


def valid_shadow(snapshot):
    shadow = snapshot.get("attack_defence_shadow")
    if not isinstance(shadow, dict):
        return False, "no_forward_shadow"
    if not (shadow.get("model_role") == "shadow_validation" and
            shadow.get("status") == "BOUNDED_HYPOTHESIS_UNCALIBRATED" and
            shadow.get("not_formal") is True and shadow.get("result_data_used") is False and
            shadow.get("no_additional_stake") is True and
            shadow.get("frozen_at_utc") == snapshot.get("frozen_at_utc")):
        return False, "invalid_or_unmatched_shadow_provenance"
    if not shadow.get("point_count_matched"):
        return False, "unequal_point_count_not_strictly_comparable"
    shadow_bets = shadow.get("forecast_alternative_bets")
    main_bets = snapshot.get("bets")
    for bets in (main_bets, shadow_bets):
        if not isinstance(bets, list) or not 4 <= len(bets) <= 24:
            return False, "invalid_ticket_count"
        if len(set(x.get("combination") for x in bets)) != len(bets):
            return False, "duplicate_ticket"
        if not all(type(x.get("virtual_yen")) is int and x["virtual_yen"] >= 1000 and
                   x["virtual_yen"] % 1000 == 0 for x in bets):
            return False, "invalid_stake"
        if sum(x["virtual_yen"] for x in bets) != RESEARCH_BUDGET:
            return False, "wrong_budget"
    if len(main_bets) != len(shadow_bets):
        return False, "point_count_mismatch"
    return True, "ready"


def analyze_ledger(ledger):
    day = ledger["event_date"]
    rows, excluded = [], Counter()
    for record in (ledger.get("race_records") or {}).values():
        versions = record.get("versions") or []
        if not versions:
            excluded["no_frozen_main"] += 1
            continue
        snapshot = versions[-1]
        ok, reason = valid_shadow(snapshot)
        if not ok:
            excluded[reason] += 1
            continue
        if record.get("official_review") or record.get("official_conflict"):
            excluded["official_conflict_or_review"] += 1
            continue
        p = record.get("official_pay")
        official_view = {**p, "virtual_stake": RESEARCH_BUDGET} if isinstance(p, dict) else None
        valid, reason = _verify_race(snapshot, official_view, day)
        if not valid:
            excluded[reason] += 1
            continue
        shadow = snapshot["attack_defence_shadow"]
        rows.append({
            "venue": snapshot["venue"], "race": snapshot["race"],
            "time": time_bucket(snapshot["cutoff_jst"]),
            "phase": snapshot["phase"],
            "main": ticket_result(snapshot["bets"], p["finish"], p["payout_per_100"]),
            "shadow": ticket_result(shadow["forecast_alternative_bets"], p["finish"], p["payout_per_100"]),
        })
    buckets = {bucket: metrics([r for r in rows if r["time"] == bucket])
               for bucket in ("before_12", "12_to_15", "15_to_18", "after_18")}
    by_venue = {name: metrics([r for r in rows if r["venue"] == name])
                for name in sorted(set(r["venue"] for r in rows))}
    afternoon_by_venue = {name: metrics([r for r in rows if r["venue"] == name and
                                        r["time"] in ("12_to_15", "15_to_18")])
                          for name in sorted(set(r["venue"] for r in rows))}
    return {
        "event_date": day,
        "type": "strictly_forward_same_pre_cutoff_shadow_vs_main",
        "sample_note": "Uncalibrated pre-race hypothesis; no formal tickets edited; no causal claims from small samples.",
        "total": metrics(rows), "by_time": buckets,
        "by_venue": by_venue, "afternoon_by_venue": afternoon_by_venue,
        "excluded": dict(excluded),
        "read_only": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--out", type=Path, help="optional report path; never overwrites a ledger")
    args = ap.parse_args()
    result = analyze_ledger(json.loads(args.ledger.read_text(encoding="utf-8")))
    printed = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        if args.out.resolve() == args.ledger.resolve():
            raise ValueError("Refusing to overwrite immutable ledger")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(printed + "\n", encoding="utf-8")
    print(printed)


if __name__ == "__main__":
    main()
