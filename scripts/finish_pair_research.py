"""Past-race-only 2nd/3rd placement research for BOAT LAB.

A model TRAINING CORPUS, not a model, not a calibrated forecast and not a pick.
All rows must be dated strictly BEFORE the target event date. The actual
winning course and decision are historical outcome labels; never feed today's
winning decision or ST into today's forecast.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
SCHEMA = "boatlabs.historical_finish_pair_priors.v0.1"
URL_ROOT = "https://boatracecsv.github.io/data/results/realtime"
VENUE_CODES = tuple(f"{i:02d}" for i in range(1, 25) if i != 3)
METHODS = frozenset({"逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"})
MAX_CSV_BYTES = 3_000_000
PAIR_ALPHA = 0.5
PAIRS = tuple((second, third) for second in range(1, 7)
              for third in range(1, 7) if third != second)


def _race_day(code):
    if not isinstance(code, str) or not re.fullmatch(r"20\d{10}", code):
        return None
    try:
        day = date.fromisoformat(f"{code[:4]}-{code[4:6]}-{code[6:8]}")
    except ValueError:
        return None
    if code[8:10] not in VENUE_CODES or not 1 <= int(code[10:12]) <= 12:
        return None
    return day


def _valid_row(row, target_day):
    code = row.get("レースコード")
    raced = _race_day(code)
    if raced is None or raced >= target_day:
        return None
    if row.get("レース日") and row["レース日"] != raced.isoformat():
        return None
    course_to_lane = []
    for c in range(1, 7):
        boat = row.get(f"{c}コース_艇番")
        if boat not in ("1", "2", "3", "4", "5", "6"):
            return None
        if row.get(f"{c}コース_F", "").strip():
            return None
        st = row.get(f"{c}コース_スタートタイミング", "")
        try:
            if st and float(st) < 0:
                return None  # unmarked F also excluded
        except ValueError:
            pass  # missing ST is not used as a predictor
        course_to_lane.append(int(boat))
    if set(course_to_lane) != set(range(1, 7)):
        return None
    try:
        finishes = tuple(int(row.get(f"{rank}着_艇番")) for rank in (1, 2, 3))
    except (ValueError, TypeError):
        return None
    if any(not 1 <= n <= 6 for n in finishes) or len(set(finishes)) != 3:
        return None
    by_lane = {lane:course for course, lane in enumerate(course_to_lane, 1)}
    first, second, third = (by_lane[finishes[0]], by_lane[finishes[1]],
                             by_lane[finishes[2]])
    method = (row.get("決まり手") or "").strip()
    return {"code":code, "venue":code[8:10], "day":raced,
            "head_course":first, "second_course":second,
            "third_course":third, "method":method if method in METHODS else "other"}


def _group_summary(pairs, head, min_samples):
    n = sum(pairs.values())
    if n < min_samples:
        return {"sample_count": n, "status": "INSUFFICIENT_SAMPLE",
                "top_pairs": [], "minimum_required": min_samples}
    possible = [(s, t) for (s,t) in PAIRS if s != head and t != head]
    if len(possible) != 20:
        raise ValueError("invalid_conditional_pair_space")
    denom = n + PAIR_ALPHA * len(possible)
    leading = sorted(possible, key=lambda p:(-pairs.get(p, 0), p[0], p[1]))[:8]
    return {
        "sample_count": n,
        "status": "DESCRIPTIVE_ONLY_NOT_CALIBRATED",
        "possible_ordered_pairs": len(possible),
        "smoothing": "Jeffreys 0.5 per ordered pair; descriptive not validated",
        "top_pairs": [
            {"second_course":p[0], "third_course":p[1],
             "observed_count":pairs.get(p,0),
             "observed_share":round(pairs.get(p,0)/n, 5),
             "smoothed_share":round((pairs.get(p,0)+PAIR_ALPHA)/denom, 5)}
            for p in leading
        ],
    }


def build(target_day, rows, *, collected_at=None, min_samples=30):
    if not isinstance(target_day, date) or isinstance(target_day, datetime):
        raise ValueError("target_day_required")
    if type(min_samples) is not int or not 20 <= min_samples <= 200:
        raise ValueError("invalid_minimum_support")
    captured = collected_at or datetime.now(timezone.utc)
    if not isinstance(captured, datetime) or captured.tzinfo is None:
        raise ValueError("timezone_aware_research_clock_required")
    counts = defaultdict(Counter)
    method_counts = defaultdict(Counter)
    seen = set()
    rejected = Counter()
    oldest = newest = None
    for row in rows:
        if not isinstance(row, dict):
            rejected["malformed_record"] += 1
            continue
        rec = _valid_row(row, target_day)
        if rec is None:
            rejected["invalid_or_current_future_or_flying_race"] += 1
            continue
        if rec["code"] in seen:
            rejected["duplicate_race"] += 1
            continue
        seen.add(rec["code"])
        oldest = min(oldest,rec["day"]) if oldest else rec["day"]
        newest = max(newest,rec["day"]) if newest else rec["day"]
        hc, pair = rec["head_course"], (rec["second_course"],rec["third_course"])
        for key in (("all", "all", hc), ("venue", rec["venue"], hc)):
            counts[key][pair] += 1
            method_counts[key][rec["method"]] += 1

    groups = {}
    for key, observed in sorted(counts.items()):
        kind, venue, head = key
        label = f"{kind}:{venue}:head_course:{head}"
        groups[label] = {**_group_summary(observed, head, min_samples),
                         "scope":kind,"venue_code":venue,"winning_course":head,
                         "observed_winning_methods":dict(sorted(method_counts[key].items()))}
    return {
        "schema": SCHEMA, "target_event_date": target_day.isoformat(),
        "source": "BoatraceCSV historical realtime RESULTS only",
        "collected_at_utc": captured.astimezone(timezone.utc).isoformat(),
        "historical_date_range": {"min":oldest.isoformat() if oldest else None,
                                  "max":newest.isoformat() if newest else None},
        "validated_historical_races": len(seen),
        "rejected": dict(sorted(rejected.items())),
        "min_samples_per_head":min_samples,
        "group_count":len(groups), "groups":groups,
        "scoped_venues":"23 venues excluding Edogawa",
        "forecast_eligibility":"RESEARCH_ONLY_NOT_FROZEN_NOT_READY_FOR_AUTOMATIC_PICKS",
        "result_data_used_for_training": True,
        "result_data_used_for_current_race_prediction": False,
        "statistical_note": (
            "Observed winning course/method is known only after each HISTORICAL race. "
            "Current race winner/decision must never be looked up or entered as a predictor. "
            "Small samples excluded. These are descriptive cohort frequencies, "
            "not calibrated P(2nd,3rd) nor causal effects."),
        "formal_forecasts_modified": 0,
    }


def _fetch_one(day):
    url=f"{URL_ROOT}/{day:%Y/%m/%d}.csv"
    health={"date":day.isoformat(),"url":url,"rows":0,
            "state":"unavailable","sha256":None}
    try:
        req=Request(url,headers={"User-Agent":"BOAT-LAB-conditional-research/0.1"})
        with urlopen(req,timeout=12) as response:
            data=response.read(MAX_CSV_BYTES+1)
        if len(data)>MAX_CSV_BYTES:
            raise ValueError("source_too_large")
        rows=list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        if rows and "レースコード" not in rows[0]:
            raise ValueError("source_schema_changed")
        health.update(state="available" if rows else "empty",
                      rows=len(rows),sha256=hashlib.sha256(data).hexdigest())
        return rows,health
    except (HTTPError,URLError,TimeoutError,UnicodeError,ValueError,OSError) as exc:
        health["error"]=type(exc).__name__
        return [],health


def fetch_history(target_day, days, *, fetcher=_fetch_one):
    if type(days) is not int or not 7 <= days <= 90:
        raise ValueError("lookback_days_must_be_7_to_90")
    dates=[target_day-timedelta(days=i) for i in range(days,0,-1)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        collected=list(pool.map(fetcher,dates))
    rows=[r for batch,_ in collected for r in batch]
    health={d.isoformat():state for d,(_,state) in zip(dates,collected)}
    return rows,health


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--date",help="target JST YYYY-MM-DD, default current JST day")
    p.add_argument("--days",type=int,default=21)
    p.add_argument("--min-samples",type=int,default=30)
    p.add_argument("--out",type=Path)
    p.add_argument("--force",action="store_true",
                   help="replace an existing research report (no formal forecasts)")
    args=p.parse_args(argv)
    today=datetime.now(JST).date()
    target=date.fromisoformat(args.date) if args.date else today
    if target>today:
        p.error("cannot build a future-dated research ledger")
    output=args.out or Path(f"app/data/experiments/finish-pair-priors-{target}.json")
    if output.exists() and not args.force:
        print(f"[research] existing independent prior preserved: {output}")
        return
    try:
        rows,health=fetch_history(target,args.days)
        report=build(target,rows,min_samples=args.min_samples)
        report["source_health"]=health
        report["lookback_days_requested"]=args.days
    except ValueError as exc:
        p.error(str(exc))
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(output)
    print("[research] prior-only",target,"verified historical",report["validated_historical_races"],
          "group count",report["group_count"],"NO live forecast changes")


if __name__ == "__main__":
    main()
