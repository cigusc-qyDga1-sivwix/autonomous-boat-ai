"""Backfill official trifecta results without ever generating post-race forecasts.

The daily forecast workflow is best-effort and only reconciles the current JST
date. This independent job revisits previous days' *already frozen* predictions.
Official pay evidence is mandatory; no unofficial result becomes a settlement.
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.autonomous_daily import APP_DATA, JST, integrate_official, write_json
from scripts.official_pay import fetch_official_pay


def valid_snapshot(snapshot: dict | None, day: str) -> bool:
    return bool(
        isinstance(snapshot, dict)
        and snapshot.get("date") == day
        and snapshot.get("source_url") == (
            "https://www.boatrace.jp/owpc/pc/race/pay?hd=" + day.replace("-", "")
        )
        and snapshot.get("evidence_type") == "official_boatrace_pay_snapshot"
        and snapshot.get("status") == "verified_by_server_fetch"
        and isinstance(snapshot.get("results"), dict)
        and isinstance(snapshot.get("reviews"), dict)
        and isinstance(snapshot.get("cancellations"), dict)
    )


def merge_verified(old: dict | None, new: dict, day: str) -> dict:
    """Only append matching official results; quarantine any correction."""
    if new.get("date") != day or new.get("source_url") != (
        "https://www.boatrace.jp/owpc/pc/race/pay?hd=" + day.replace("-", "")
    ):
        raise ValueError("Official result date or source URL mismatch")
    prior = old if valid_snapshot(old, day) else {}
    merged = copy.deepcopy(new)
    results = copy.deepcopy(prior.get("results", {}))
    reviews = copy.deepcopy(prior.get("reviews", {}))
    reviews.update(new.get("reviews") or {})
    cancellations = copy.deepcopy(prior.get("cancellations", {}))
    cancellations.update(new.get("cancellations") or {})
    conflicts = copy.deepcopy(prior.get("conflicts", {}))
    for race, incoming in (new.get("results") or {}).items():
        if race in results and results[race] != incoming:
            conflicts[race] = {"previous": results[race], "incoming": incoming}
            reviews[race] = {"reason": "official_correction_conflict"}
        elif race not in conflicts:
            results[race] = incoming
    for race in set(conflicts) | set(reviews) | set(cancellations):
        results.pop(race, None)
    merged.update({
        "results": results, "reviews": reviews, "cancellations": cancellations,
        "conflicts": conflicts, "status": "verified_by_server_fetch",
        "evidence_type": "official_boatrace_pay_snapshot",
    })
    return merged


def reconcile_day(directory: Path, day: str, now: datetime,
                  fetcher=fetch_official_pay) -> dict:
    """Reconcile an existing date; preserve every pre-cutoff version byte-for-byte."""
    status = {"date": day, "fresh_fetch": False, "newly_verified": 0,
              "forecast_records": 0, "verified": 0, "needs_review": 0}
    path = directory / (day + ".json")
    if not path.exists():
        status["state"] = "NO_FROZEN_LEDGER"
        return status
    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("event_date") != day or not isinstance(ledger.get("race_records"), dict):
        status["state"] = "INVALID_LEDGER"
        return status
    records = ledger["race_records"]
    status["forecast_records"] = sum(bool(r.get("versions")) for r in records.values())
    if not status["forecast_records"]:
        status["state"] = "NO_PRE_RACE_FORECASTS"
        return status
    if day > now.astimezone(JST).date().isoformat():
        status["state"] = "FUTURE_DATE"
        return status

    pay_path = directory / "official-pay" / (day + ".json")
    cached = None
    if pay_path.exists():
        try:
            candidate = json.loads(pay_path.read_text(encoding="utf-8"))
            if valid_snapshot(candidate, day):
                cached = candidate
        except (OSError, ValueError):
            pass
    try:
        official = fetcher(day.replace("-", ""))
        merged = merge_verified(cached, official, day)
        status["fresh_fetch"] = True
    except Exception as exc:
        status["fetch_error"] = str(exc)[:350]
        if cached is None:
            status["state"] = "SOURCE_UNAVAILABLE"
            return status
        merged = cached
    if status["fresh_fetch"] and merged != cached:
        write_json(pay_path, merged)

    # The hashing and immutable forecast versions are deliberately untouched.
    frozen_before = json.dumps(
        {k: r.get("versions", []) for k, r in records.items()},
        sort_keys=True, ensure_ascii=False,
    )
    before = copy.deepcopy(ledger)
    is_today = day == now.astimezone(JST).date().isoformat()
    latest_path = directory / "latest.json"
    view = {}
    if is_today and latest_path.exists():
        candidate = json.loads(latest_path.read_text(encoding="utf-8"))
        if candidate.get("event_date") == day and candidate.get("mode") == "auto-live":
            view = candidate
    view = integrate_official(ledger, view, merged, now)
    frozen_after = json.dumps(
        {k: r.get("versions", []) for k, r in records.items()},
        sort_keys=True, ensure_ascii=False,
    )
    if frozen_before != frozen_after:
        raise AssertionError("Reconciliation modified a frozen forecast")
    if ledger != before:
        write_json(path, ledger)
    if is_today and view.get("mode") == "auto-live":
        # Do not modify prediction timestamps or cached forecast SHA values.
        view["result_sync"] = {
            "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
            "fresh_fetch": status["fresh_fetch"],
            "verified": len(view.get("official_results", {})),
            "needs_review": len(view.get("settlement_alerts", {})),
        }
        write_json(latest_path, view)
    status["state"] = "UPDATED" if ledger != before else "UNCHANGED"
    status["verified"] = len(view.get("official_results", {}))
    status["newly_verified"] = view.get("official_pay_info", {}).get("newly_confirmed", 0)
    status["needs_review"] = len(view.get("settlement_alerts", {}))
    status["official_page_results"] = len(merged.get("results", {}))
    return status


def run(directory: Path, now: datetime, days: int,
        fetcher=fetch_official_pay) -> dict:
    if now.tzinfo is None or not 1 <= days <= 14:
        raise ValueError("An aware clock and 1–14 days are required")
    today = now.astimezone(JST).date()
    states = [
        reconcile_day(directory, (today - timedelta(days=offset)).isoformat(),
                      now, fetcher)
        for offset in range(days - 1, -1, -1)
    ]
    report = {
        "schema": "boatlabs.official_result_reconciliation.v1",
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "days_checked": days,
        "fresh_fetches": sum(r["fresh_fetch"] for r in states),
        "newly_verified": sum(r["newly_verified"] for r in states),
        "verified_frozen_races": sum(r["verified"] for r in states),
        "days": states,
        "note": "Official-only. Missing, disputed and unforecast races are not losses; no retroactive forecast creation.",
    }
    write_json(directory / "result-sync-latest.json", report)
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=5)
    p.add_argument("--out-dir", type=Path, default=APP_DATA)
    args = p.parse_args()
    report = run(args.out_dir, datetime.now(timezone.utc), args.days)
    print(json.dumps(report, ensure_ascii=False))
    if any(r["state"] in ("SOURCE_UNAVAILABLE", "INVALID_LEDGER") for r in report["days"]):
        print("WARNING: Some days could not be fully reconciled; see result-sync-latest.json")


if __name__ == "__main__":
    main()
