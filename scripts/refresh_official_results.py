"""Independent lightweight BOAT LAB official payoff updater.

Only modifies post-race evidence in the existing immutable daily ledger.
Crucial: this job does NOT run autonomous_daily's forecasting pipeline and
never constructs or changes historical pre-cutoff tickets or their hashes.
"""
from __future__ import annotations
import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.autonomous_daily import APP_DATA, integrate_official, write_json
from scripts.official_pay import fetch_official_pay

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc

def merge_pay(old: dict, incoming: dict) -> dict:
    """Preserve independently verified past official outputs; quarantine conflicts."""
    new = copy.deepcopy(incoming)
    if old.get("date") != new.get("date"):
        return new
    old_results=old.get("results") or {}
    conflicts={**(old.get("conflicts") or {}), **(new.get("conflicts") or {})}
    for key, value in old_results.items():
        updated=new.get("results",{}).get(key)
        if updated and updated!=value:
            conflicts[key]={"previous":value,"incoming":updated}
            new["results"].pop(key,None)
            new.setdefault("reviews",{})[key]={"reason":"official_correction_conflict"}
        elif not updated and key not in new.get("reviews",{}) and key not in new.get("cancellations",{}) and key not in conflicts:
            new["results"][key]=value
    for key in conflicts:
        new["results"].pop(key,None)
        new.setdefault("reviews",{})[key]={"reason":"official_correction_conflict"}
    new["conflicts"]=conflicts
    return new

def update(ledger: dict, view: dict, old: dict, pay: dict, now: datetime):
    if now.tzinfo is None:
        raise ValueError("Clock must include a timezone")
    day=now.astimezone(JST).date().isoformat()
    if ledger.get("event_date")!=day or view.get("event_date")!=day:
        raise ValueError("Official updater requires existing same-day pre-cutoff ledger/view")
    if pay.get("date")!=day:
        raise ValueError("Official date mismatch; refusing stale results")
    if not ledger.get("race_records") or not isinstance(view.get("forecast_races"),list):
        raise ValueError("Refusing incomplete source snapshot")
    snapshot_before={
        key:[(v["sha256"],json.dumps(v,sort_keys=True,ensure_ascii=False))
             for v in rec.get("versions",[])]
        for key,rec in ledger["race_records"].items()
    }
    merged=merge_pay(old,pay)
    merged["status"]="verified_by_server_fetch"
    merged["evidence_type"]="official_boatrace_pay_snapshot"
    updated_ledger=copy.deepcopy(ledger)
    updated_view=copy.deepcopy(view)
    before=len(updated_view.get("official_results") or {})
    integrate_official(updated_ledger,updated_view,merged,now)
    after=len(updated_view.get("official_results") or {})
    snapshot_after={
        key:[(v["sha256"],json.dumps(v,sort_keys=True,ensure_ascii=False))
             for v in rec.get("versions",[])]
        for key,rec in updated_ledger["race_records"].items()
    }
    if snapshot_after != snapshot_before:
        raise ValueError("Pre-cutoff forecast snapshot or SHA unexpectedly changed")
    # Give the UI a distinct, monotonic evidence timestamp, without overwriting
    # the prediction model's original capture timestamp.
    old_official=updated_view.get("official_pay_info",{})
    old_official["source_status"]="OK"
    updated_view["official_pay_info"]=old_official
    previous_keys={(key,rec.get("official_pay",{}).get("finish"),
                    rec.get("official_pay",{}).get("payout_per_100"),
                    json.dumps(rec.get("official_conflict",{}),sort_keys=True),
                    str(rec.get("official_review","")))
                   for key,rec in ledger["race_records"].items()}
    new_keys={(key,rec.get("official_pay",{}).get("finish"),
               rec.get("official_pay",{}).get("payout_per_100"),
               json.dumps(rec.get("official_conflict",{}),sort_keys=True),
               str(rec.get("official_review","")))
              for key,rec in updated_ledger["race_records"].items()}
    changed=previous_keys!=new_keys or after!=before
    if changed:
        updated_view["updated_at_utc"]=now.astimezone(UTC).isoformat()
        updated_view["official_results_updated_at_utc"]=now.astimezone(UTC).isoformat()
    return updated_ledger,updated_view,merged,changed,{
        "date":day,"before_verified":before,"after_verified":after,
        "newly_verified":max(0,after-before),"changed":changed,
        "page_verified":len(merged.get("results",{}))
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dir",type=Path,default=APP_DATA)
    args=parser.parse_args()
    now=datetime.now(UTC)
    day=now.astimezone(JST).date().isoformat()
    compact=day.replace("-","")
    path=args.dir/f"{day}.json"
    live=args.dir/"latest.json"
    pay_path=args.dir/"official-pay"/f"{day}.json"
    if not path.exists() or not live.exists():
        raise SystemExit("Forecast snapshot unavailable, cannot attach official outcome")
    ledger=json.loads(path.read_text(encoding="utf-8"))
    view=json.loads(live.read_text(encoding="utf-8"))
    previous=json.loads(pay_path.read_text(encoding="utf-8")) if pay_path.exists() else {}
    incoming=fetch_official_pay(compact)
    updated_ledger,updated_view,merged,changed,report=update(ledger,view,previous,incoming,now)
    # Publish only when official data has actually changed, never rewrite
    # a forecast or replay past races with a new inference model.
    if changed:
        write_json(path,updated_ledger)
        write_json(live,updated_view)
        write_json(pay_path,merged)
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()
