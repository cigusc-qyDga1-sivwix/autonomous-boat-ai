"""Retrospective exhibition-ST vs outside 1st/2nd outcomes. NO forecast training.

This is EXHIBITION ST, NOT the observed race start. The difference in course
entry/conditions means correlation cannot identify a physical start maneuver.
Source-provenance and race-code checks prevent fake leakage-free claims.
"""
from __future__ import annotations
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("app/data/exhibition")
RACE = re.compile(r"^[0-9]{12}$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WIN_METHODS={"まくり", "まくり差し"}

def bucket(gap):
    if gap is None:
        return "unavailable"
    if gap >= .03:
        return "earlier_by_003s_plus"
    if gap <= -.03:
        return "later_by_003s_plus"
    return "within_003s"

def normalized_st(boat):
    if boat.get("exhibition_f") is True:
        return None
    try:
        v=float(boat.get("exhibition_st"))
    except (TypeError, ValueError):
        return None
    return v if 0<=v<=.45 else None

def study(docs):
    seen=set()
    rows=defaultdict(Counter)
    venues=Counter()
    attempted=0
    excluded=Counter()
    for doc in docs:
        day=doc.get("event_date") if isinstance(doc,dict) else None
        if not DAY.fullmatch(str(day)) or doc.get("schema")!="boatlabs.exhibition_research.v1":
            continue
        for race in doc.get("records",[]):
            code=str(race.get("race_code",""))
            if not RACE.fullmatch(code) or code[:8]!=day.replace("-",""):
                excluded["invalid_race_code"]+=1
                continue
            if code in seen:
                excluded["duplicate_race"]+=1
                continue
            seen.add(code)
            result=race.get("result") or {}
            finish=result.get("finish")
            if (result.get("source")!="BoatraceCSV/realtime_unofficial"
                or not isinstance(finish,str) or not re.fullmatch(r"[1-6]-[1-6]-[1-6]",finish)
                or len(set(finish.split("-")))!=3):
                excluded["unverified_result"]+=1
                continue
            boats=race.get("boats") or []
            if len(boats)!=6:
                excluded["invalid_boats"]+=1
                continue
            try:
                actual={int(b["course"]):b for b in boats}
                lanes={int(b["lane"]):int(b["course"]) for b in boats}
            except (TypeError,ValueError,KeyError):
                excluded["invalid_course"]+=1
                continue
            if set(actual)!=set(range(1,7)) or set(lanes)!=set(range(1,7)) or set(lanes.values())!=set(range(1,7)):
                excluded["invalid_course"]+=1
                continue
            first,second=[lanes[int(x)] for x in finish.split("-")[:2]]
            method=str(result.get("decision","")).replace(" ","").replace("　","")
            attempted+=1
            venues[str(race.get("venue") or "不明")]+=1
            for course in (4,5,6):
                st=normalized_st(actual[course])
                prev=normalized_st(actual[course-1])
                gap=prev-st if st is not None and prev is not None else None
                group=bucket(gap)
                ct=rows[(course,group)]
                ct["n"]+=1
                ct["first"]+=int(first==course)
                ct["second"]+=int(second==course)
                ct["top2"]+=int(first==course or second==course)
                if first==course and method in WIN_METHODS:
                    ct["winning_makuri_or_makurizashi"]+=1
                ct["exhibition_f_or_missing"]+=int(gap is None)
    reports=[]
    for (course,group),r in sorted(rows.items()):
        n=r["n"]
        reports.append({
            "course":course,"exhibition_gap_vs_inner":group,
            "n":n,"first":r["first"],"second":r["second"],"top2":r["top2"],
            "winning_makuri_or_makurizashi":r["winning_makuri_or_makurizashi"],
            "first_rate":round(r["first"]/n,4),"second_rate":round(r["second"]/n,4),
            "top2_rate":round(r["top2"]/n,4),
            "support":"descriptive_only" if n>=30 else "insufficient_sample"
        })
    return {
      "schema":"boatlabs.outside_exhibition_st_outcome_research.v1",
      "created_at_utc":datetime.now(timezone.utc).isoformat(),
      "valid_result_races":attempted,"venues":dict(sorted(venues.items())),
      "groups":reports,"excluded":dict(excluded),
      "st_definition":"exhibition ST (negative/F excluded), gap=inner adjacent exhibition ST - own; positive implies outer earlier at exhibition only",
      "warning":"Research of retrospective exhibited ST vs finishing, NOT actual race ST. Exhibition/course may differ from race. Correlation is not causation. This data MUST NEVER feed current-day pre-cutoff forecasts or change frozen tickets."
    }

def research(source_dir=BASE):
    docs=[]
    for path in sorted(Path(source_dir).glob("????-??-??.json")):
        try:docs.append(json.loads(path.read_text(encoding="utf8")))
        except (OSError,ValueError):pass
    return study(docs)

def main():
    output=research()
    dest=BASE/"outside-start-gap-research-latest.json"
    dest.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(f"Outside exhibition ST retrospective: {output['valid_result_races']} result races")

if __name__=="__main__":
    main()
