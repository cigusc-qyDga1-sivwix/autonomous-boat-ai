"""One-off read-only local-hour performance attribution: 2026-11-05 and 06.

This script is intentionally branch-scoped. It NEVER updates a prediction,
payout, model parameter, or formal results. Source is the immutable daily
forecast ledger with a verified official-pay attachment per record.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from scripts.forecast_audit import _verify_race, RESEARCH_BUDGET
import json


DAYS = ("2026-11-05", "2026-11-06")
TIME_BUCKETS = [
    ("before_12", 0, 12),
    ("12_to_15", 12, 15),
    ("15_to_18", 15, 18),
    ("18_onward", 18, 24),
]


def summarize(rows):
    n = len(rows)
    hits = sum(row["hit"] for row in rows)
    paid = sum(row["paid"] for row in rows)
    heads = Counter(row["failure_stage"] for row in rows)
    phase = Counter(row["phase"] for row in rows)
    return {
        "races": n,
        "hits": hits,
        "hit_percent": round(100 * hits / n, 2) if n else None,
        "roi_percent": round(100 * paid / (RESEARCH_BUDGET * n), 2) if n else None,
        "stake": RESEARCH_BUDGET * n,
        "paid": paid,
        "net": paid - RESEARCH_BUDGET * n,
        "miss_types": dict(heads),
        "exhibition_races": phase.get("exhibition", 0),
        "exhibition_percent": round(100 * phase.get("exhibition", 0) / n, 1) if n else None,
        "first_ticket_head1": sum(r["first_ticket_head"] == "1" for r in rows),
        "actual_winner1": sum(r["actual_head"] == "1" for r in rows),
        "tickets_cover_head": sum(r["failure_stage"] != "head_miss" for r in rows),
        "tickets_cover_pair": sum(r["failure_stage"] in ("hit", "third_miss") for r in rows),
        "average_points": round(sum(r["points"] for r in rows)/n, 1) if n else None,
    }


def load(day):
    path = Path(f"app/data/live/{day}.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("event_date") != day:
        raise ValueError(f"Wrong ledger day: {path}")
    eligible, rejected = [], Counter()
    for code, record in (doc.get("race_records") or {}).items():
        versions = record.get("versions") or []
        if not versions:
            rejected["no_frozen_prediction"] += 1
            continue
        if record.get("official_conflict") or record.get("official_review"):
            rejected["official_conflict_or_review"] += 1
            continue
        p = record.get("official_pay")
        snapshot = dict(versions[-1])
        snapshot.setdefault("cutoff_jst", record.get("cutoff_jst"))
        # The compact immutable ledger stores verified official finish/payout
        # but not the denormalized virtual_stake field used by the web view.
        # Cross-check each frozen ticket sums to the fixed 50,000 research stake.
        # Supply that *derived view field only in memory* for audit validation.
        fixed = snapshot.get("bets") or []
        stake = sum(b.get("virtual_yen", 0) for b in fixed)
        pay_view = {**p, "virtual_stake": stake} if isinstance(p, dict) else None
        ok, reason = _verify_race(snapshot, pay_view, day)
        if not ok:
            rejected[reason] += 1
            continue
        time_str = snapshot["cutoff_jst"]
        hour = int(time_str.split(":")[0])
        win = p["finish"]
        bets = snapshot["bets"]
        exact = next((b for b in bets if b["combination"] == win), None)
        heads = {b["combination"][0] for b in bets}
        pairs = {b["combination"][:3] for b in bets}
        stage = ("hit" if exact is not None else "head_miss" if win[0] not in heads
                 else "second_miss" if win[:3] not in pairs else "third_miss")
        eligible.append({
            "venue": record["venue"], "race": record["race"], "cutoff": time_str,
            "hour": hour, "hit": exact is not None,
            "failure_stage": stage, "actual_finish": win,
            "actual_head": win[0],
            "paid": (exact["virtual_yen"] * p["payout_per_100"] // 100
                     if exact is not None else 0),
            "phase": snapshot.get("phase"),
            "classification": snapshot.get("classification"),
            "points": len(bets),
            "first_ticket_head": bets[0]["combination"][0],
            "version_count": len(versions),
        })
    return eligible, rejected


def main():
    summary = {}
    for day in DAYS:
        rows, rejected = load(day)
        slots = {name: [r for r in rows if low <= r["hour"] < high]
                 for name, low, high in TIME_BUCKETS}
        before = slots["before_12"]
        after = [r for r in rows if r["hour"] >= 12]
        pm = [r for r in rows if 12 <= r["hour"] < 18]
        venues = sorted({r["venue"] for r in rows})
        per_venue = {venue: {
            "before_12": summarize([r for r in before if r["venue"] == venue]),
            "12_to_18": summarize([r for r in pm if r["venue"] == venue]),
            "18_onward": summarize([r for r in after if r["venue"] == venue and r["hour"] >= 18]),
        } for venue in venues}
        summary[day] = {
            "verified": len(rows), "excluded": dict(rejected),
            "total": summarize(rows),
            "before_noon": summarize(before),
            "after_noon_all": summarize(after),
            "12_to_18": summarize(pm),
            "time_buckets": {name: summarize(part) for name, part in slots.items()},
            "venues": per_venue,
            "phases_12_to_18": {
                phase: summarize([r for r in pm if r["phase"] == phase])
                for phase in sorted({r["phase"] for r in pm})},
            "worst_miss_examples_12_to_18": [
                {k:r[k] for k in ("venue","race","cutoff","failure_stage","actual_finish","first_ticket_head","phase")}
                for r in pm if not r["hit"]
            ][:18]
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
