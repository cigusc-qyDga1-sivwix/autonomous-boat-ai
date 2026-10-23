"""Read-only 24-venue feature research harvester for BOAT LAB.

The purpose is to collect a pre-race research corpus, with provenance and
source freshness, NOT to modify or backdate forecasts or official results.

BoatraceCSV is an independent third-party data source. Its historical snapshots
may have been published AFTER the race even if the displayed information looks
pre-race. This output MUST NOT enter an immutable pre-cutoff forecast without a
separately captured time-bounded source snapshot and hash.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = "https://boatracecsv.github.io/data/"
JST = ZoneInfo("Asia/Tokyo")
DAY_SOURCE_PATHS = {
    "race_cards": "programs/race_cards",
    "waku10": "programs/waku10",
    "recent_national": "programs/recent_national",
    "recent_local": "programs/recent_local",
    "motor_stats": "programs/motor_stats",
    "title": "programs/title",
}
REQUIRED = ("race_cards", "waku10")
MAX_CSV_BYTES = 18_000_000  # refuse unexpectedly huge responses
MAX_RECORDS = 24 * 12  # one code per venue/race, incomplete days allowed

def source_url(name: str, day: date) -> str:
    if name == "monthly_schedule":
        return f"{ROOT}programs/monthly_schedule/{day:%Y/%m}.csv"
    if name == "motor_history":
        path = "programs/motor_history"
    else:
        path = DAY_SOURCE_PATHS[name]
    return f"{ROOT}{path}/{day:%Y/%m/%d}.csv"

def fetch_csv(name: str, day: date) -> tuple[list[dict[str, str]], dict]:
    url = source_url(name, day)
    note = {"url": url, "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "rows": 0, "state": "missing_or_unavailable", "error": None,
            "sha256": None}
    try:
        req = Request(url, headers={"User-Agent": "BOAT-LAB-data-research/0.1"})
        with urlopen(req, timeout=18) as response:
            payload = response.read(MAX_CSV_BYTES + 1)
        if len(payload) > MAX_CSV_BYTES:
            raise ValueError("source size exceeds safety limit")
        content = payload.decode("utf-8-sig")
        table = list(csv.DictReader(io.StringIO(content)))
        if table and "レースコード" not in table[0] and name not in ("motor_stats", "motor_history", "monthly_schedule"):
            raise ValueError("missing race join key; upstream schema may have changed")
        note.update(rows=len(table), state="available" if table else "empty",
                    sha256=hashlib.sha256(payload).hexdigest())
        return table, note
    except (HTTPError, URLError, TimeoutError, UnicodeError, ValueError, OSError) as exc:
        note["error"] = type(exc).__name__ + ": " + str(exc)[:140]
        return [], note

def numeric(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None

def integer(value):
    value = numeric(value)
    return int(value) if value is not None and value.is_integer() else None

def select(row, specs):
    result = {}
    for field, key, kind in specs:
        raw = row.get(key)
        if kind == "num": value = numeric(raw)
        elif kind == "int": value = integer(raw)
        else: value = (raw or "").strip() or None
        if value is not None:
            result[field] = value
    return result

def by_race(rows, day):
    prefix = day.strftime("%Y%m%d")
    return {r["レースコード"]: r for r in rows
            if r.get("レースコード", "").startswith(prefix)
            and len(r.get("レースコード", "")) == 12
            and r["レースコード"][8:10].isdigit()
            and 1 <= int(r["レースコード"][8:10]) <= 24
            and r["レースコード"][10:12].isdigit()
            and 1 <= int(r["レースコード"][10:12]) <= 12}

def extract_sessions(row, lane):
    session = []
    for d in range(1, 8):
        for run in (1, 2):
            root = f"艇{lane}_節D{d}走{run}_"
            race = integer(row.get(root+"R番号"))
            if race is None: continue
            session.append({"day":d,"run":run,"race":race,
                 "course":integer(row.get(root+"進入")),
                 "frame":integer(row.get(root+"枠")),
                 "start":numeric(row.get(root+"ST")),
                 "finish":row.get(root+"着順") or None})
    return session

def extract_prior10(row, lane):
    prior = []
    for j in range(1, 11):
        root = f"艇{lane}_過去{j}走_"
        fields={k:row.get(root+k) for k in ("着順","進入","グレード")}
        if any(v not in (None, "") for v in fields.values()):
            prior.append({"n":j,"finish":fields["着順"] or None,
                 "course":fields["進入"] or None,"grade":fields["グレード"] or None})
    return prior

def extract_recent(row, lane):
    sections=[]
    for j in range(1,6):
        prefix=f"艇{lane}_前{j}節_"
        begin=row.get(prefix+"開始日") or None
        end=row.get(prefix+"終了日") or None
        if begin is None and end is None: continue
        sections.append({"n":j,"start":begin,"end":end,
           "venue_code":row.get(prefix+"場コード") or None,
           "grade":row.get(prefix+"グレード") or None,
           "finishes":row.get(prefix+"着順列") or None})
    return sections

def motor_registry(rows):
    by_motor={}
    for row in rows:
        venue=integer(row.get("場コード"))
        motor=integer(row.get("モーター番号"))
        if venue is None or not 1<=venue<=24 or motor is None: continue
        key=f"{venue:02d}-{motor}"
        by_motor[key]=select(row,[
          ("date","記録日","str"),("period_start","モーター期起算日","str"),
          ("motor","モーター番号","int"),("wins_pct","2連対率","num"),
          ("podium_pct","3連対率","num"),("win_rank","2連対率順位","int"),
          ("runs","出走数","int"),("victories","1着回数","int"),
          ("lap_seconds","平均ラップ秒","num"),("lap_rank","平均ラップ順位","int"),
          ("maintenance_date","直近メンテ日","str"),
          ("maintenance_1","整備種別1回数","int"),
          ("maintenance_2","整備種別2回数","int"),
          ("maintenance_3","整備種別3回数","int"),
          ("maintenance_4","整備種別4回数","int"),
          ("maintenance_5","整備種別5回数","int"),
          ("maintenance_6","整備種別6回数","int"),
        ])
    return by_motor

def previous_meeting_end_dates(day: date, schedules: list[dict], active_codes: set[int],
                               max_keys: int = 12) -> list[date]:
    """Look up each active venue's most recent completed meeting, not yesterday."""
    most_recent={}
    for row in schedules:
        venue=integer(row.get("場コード"))
        if venue not in active_codes: continue
        try: end=date.fromisoformat(row.get("節終了日") or "")
        except ValueError: continue
        if end>=day: continue
        if venue not in most_recent or most_recent[venue]<end:
            most_recent[venue]=end
    return sorted(set(most_recent.values()),reverse=True)[:max_keys]

def historical_motors(rows, current_day: date):
    """Only previous-meet history; never present race day or future usage."""
    result={}
    for row in rows:
        venue=integer(row.get("場コード")); motor=integer(row.get("モーター番号"))
        end=row.get("使用終了日") or ""
        if venue is None or not 1<=venue<=24 or motor is None or not end: continue
        try: past=date.fromisoformat(end)
        except ValueError: continue
        if past>=current_day: continue
        key=f"{venue:02d}-{motor}"
        result.setdefault(key,[]).append({
          "end":end,"start":row.get("使用開始日") or None,
          "racer":row.get("使用者名") or None,"finish_sequence":row.get("着順列") or None,
          "grade":row.get("グレード") or None
        })
    for key in result:
        dedup={(x["end"],x["racer"],x["finish_sequence"]):x for x in result[key]}
        result[key]=sorted(dedup.values(),key=lambda x:x["end"],reverse=True)[:6]
    return result

def make_research(day, rows_by_source, source_states, collected_at_utc, prior=None):
    """Build reproducible JOIN result; NEVER read the official results file."""
    pre={k:by_race(rows_by_source.get(k,[]),day) for k in
         ("race_cards","waku10","recent_national","recent_local","title")}
    motors=motor_registry(rows_by_source.get("motor_stats",[]))
    historical=historical_motors(rows_by_source.get("motor_history",[]),day)
    codes=sorted(set().union(*(set(x) for x in pre.values())))
    if len(codes)>MAX_RECORDS:raise ValueError("Suspiciously many race keys")
    records=[]
    for code in codes:
        card=pre["race_cards"].get(code,{})
        waku=pre["waku10"].get(code,{})
        nat=pre["recent_national"].get(code,{})
        loc=pre["recent_local"].get(code,{})
        title=pre["title"].get(code,{})
        venue=code[8:10]
        boats=[]
        for n in range(1,7):
            prefix=f"艇{n}_"
            racer=select(card,[
              ("racer_id",prefix+"登録番号","int"),
              ("name",prefix+"選手名","str"),
              ("grade",prefix+"級別","str"),
              ("national_win",prefix+"全国勝率","num"),
              ("national_st",prefix+"全国平均ST","num"),
              ("national_top3",prefix+"全国3連対率","num"),
              ("local_win",prefix+"当地勝率","num"),
              ("local_top3",prefix+"当地3連対率","num"),
              ("f_count",prefix+"F本数","int"),("l_count",prefix+"L本数","int"),
              ("motor_no",prefix+"モーター番号","int"),
              ("motor_top2",prefix+"モーター2連対率","num"),
              ("motor_top3",prefix+"モーター3連対率","num"),
              ("boat_no",prefix+"ボート番号","int"),
              ("boat_top2",prefix+"ボート2連対率","num"),
              ("boat_top3",prefix+"ボート3連対率","num"),
            ])
            racer["lane"]=n
            racer["session"]=extract_sessions(card,n)
            racer["frame_history"]=select(waku,[
              ("frame_win",prefix+"枠番別勝率","num"),
              ("frame_st",prefix+"枠番別平均ST","num"),
              ("frame_start_order",prefix+"枠番別平均スタート順","num")
            ])
            racer["past10"]=extract_prior10(waku,n)
            racer["recent_national"]=extract_recent(nat,n)
            racer["recent_local"]=extract_recent(loc,n)
            mot=racer.get("motor_no")
            if mot is not None:
                mk=f"{venue}-{mot}"
                racer["motor_stats"]=motors.get(mk)
                racer["motor_previous_users"]=historical.get(mk,[])
            else:
                racer["motor_stats"]=None
                racer["motor_previous_users"]=[]
            boats.append(racer)
        records.append({
          "race_code":code,"venue_code":venue,"race":int(code[-2:]),
          "race_title":title.get("レース名") or None,
          "grade":title.get("グレード") or None,
          "meeting_day":title.get("日次") or None,
          "data_sources_available":[k for k,v in pre.items() if code in v],
          "racers":boats
        })
    today_status={k:{
        "state":v.get("state"),"rows":v.get("rows",0),
        "fetched_at_utc":v.get("fetched_at_utc"),
        "sha256":v.get("sha256"),"url":v.get("url"),
        "error":v.get("error")
    } for k,v in source_states.items()}
    return {
      "schema":"boatlabs.intelligence_research.v1",
      "event_date":day.isoformat(),
      "created_at_utc":collected_at_utc,
      "provenance":"Independent BoatraceCSV public data, source timestamp and fetch status recorded per CSV.",
      "forecast_eligibility":"research_only_until_independent_pre_cutoff_capture_and_hash",
      "source_policy":"No BOATERS scraping. No results/odds leakage. Not calibrated probabilities.",
      "warning":"Historical CSV re-download is NOT proof of data availability before a past race. Do not rewrite immutable predictions.",
      "sources":today_status,
      "coverage":{
        "races":len(records),"venue_count":len({x["venue_code"] for x in records}),
        "racer_rows":len(records)*6,"race_cards":len(pre["race_cards"]),
        "waku10":len(pre["waku10"]),
        "recent_national":len(pre["recent_national"]),
        "recent_local":len(pre["recent_local"]),
        "motor_stat_rows":len(motors),
        "motor_history_pairs":len(historical),
        "has_complete_racers":sum(bool(all(r.get("racer_id") for r in x["racers"])) for x in records),
      },"races":records
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",help="YYYY-MM-DD (default JST today)")
    parser.add_argument("--out-dir",type=Path,default=Path("app/data/intelligence"))
    parser.add_argument("--history-days",type=int,default=3,help="Previous-meet snapshot dates, 0-7")
    args=parser.parse_args()
    if not 0<=args.history_days<=7:parser.error("--history-days must be 0..7")
    now=datetime.now(timezone.utc)
    day=date.fromisoformat(args.date) if args.date else now.astimezone(JST).date()
    # Historical data is still *research*; do not relabel as pre-race.
    path=args.out_dir/(day.isoformat()+".json")
    rows,states={},{}
    for name in DAY_SOURCE_PATHS:
        rows[name],states[name]=fetch_csv(name,day)
    # The motor-history URL date refers to the previous meeting END date,
    # not the research day. Use the monthly schedule to find it by venue.
    first=day.replace(day=1)
    last_month=first-timedelta(days=1)
    schedule_today,health_today=fetch_csv("monthly_schedule",day)
    schedule_before,health_before=fetch_csv("monthly_schedule",last_month)
    states["monthly_schedule_"+day.strftime("%Y-%m")]=health_today
    states["monthly_schedule_"+last_month.strftime("%Y-%m")]=health_before
    active_codes={int(code[8:10]) for code in by_race(rows.get("race_cards",[]),day)}
    lookup_dates=previous_meeting_end_dates(
        day,schedule_today+schedule_before,active_codes)
    # If schedule is unavailable, attempt a few recent dates only as a fallback.
    if not lookup_dates:
        lookup_dates=[day-timedelta(days=n) for n in range(1,args.history_days+1)]
    history=[]
    for oldday in lookup_dates:
        record,health=fetch_csv("motor_history",oldday)
        states["motor_history_"+oldday.isoformat()]=health
        history.extend(record)
    rows["motor_history"]=history
    doc=make_research(day,rows,states,now.isoformat())
    prev=json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    # Keep the newest nonempty historical snapshot when upstream is temporarily
    # unreachable. NEVER overwrite a usable archive with zero-race payload.
    core_good=all(states[k]["state"]=="available" for k in REQUIRED)
    if prev and prev.get("event_date")==day and (
        prev.get("coverage",{}).get("races",0)>doc["coverage"]["races"]
        or not core_good):
        doc["races"]=prev["races"]
        doc["coverage"]=prev["coverage"]
        doc["warning"] += " Previous archive retained because key sources were missing or sparse."
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(doc,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    status={
      "event_date":day.isoformat(),"last_attempt_utc":now.isoformat(),
      "research_races":doc["coverage"]["races"],
      "coverage":doc["coverage"],
      "source_status":{k:{"state":v["state"],"rows":v["rows"],"error":v["error"]}
                       for k,v in states.items()},
      "forecast_eligibility":doc["forecast_eligibility"]
    }
    (path.parent/"status-latest.json").write_text(
      json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"research_collected","date":day.isoformat(),
                     "races":doc["coverage"]["races"],
                     "sources_ok":sum(x["state"]=="available" for x in states.values()),
                     "sources_checked":len(states)},ensure_ascii=False))
    if not any(states[k]["state"]=="available" for k in REQUIRED):
        print("[intelligence] WARNING: core sources unavailable; no fake observations")

if __name__=="__main__":
    main()
