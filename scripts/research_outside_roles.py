"""Descriptive outside-course research from archived exhibition/result snapshots.

Never used to construct or revise immutable pre-cutoff picks. Retrospective records
do not prove data was received before a race. Require source + lane-course checks.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR=Path("app/data/exhibition")
SCHEMA="boatlabs.exhibition_research.v1"
EXACT_RESULT=re.compile(r"^[1-6]-[1-6]-[1-6]$")
EXACT_DAY=re.compile(r"^\d{4}-\d{2}-\d{2}$")

def rows_from_docs(docs):
    unique={}
    for doc in docs:
        if not isinstance(doc,dict) or doc.get("schema")!=SCHEMA or not EXACT_DAY.fullmatch(str(doc.get("event_date") or "")):
            continue
        day=doc["event_date"]
        for r in doc.get("records",[]):
            if not isinstance(r,dict) or r.get("race_code","")[:8]!=day.replace("-","") or len(r.get("race_code",""))!=12:
                continue
            result=r.get("result")
            if not isinstance(result,dict) or result.get("source")!="BoatraceCSV/realtime_unofficial":
                continue
            finish=result.get("finish")
            if not isinstance(finish,str) or not EXACT_RESULT.fullmatch(finish) or len(set(finish.split("-")))!=3:
                continue
            boats=r.get("boats")
            if not isinstance(boats,list) or len(boats)!=6:
                continue
            try:
                lane_course={int(b["lane"]):int(b["course"]) for b in boats}
            except (TypeError,KeyError,ValueError):
                continue
            if set(lane_course)!=set(range(1,7)) or set(lane_course.values())!=set(range(1,7)):
                continue
            courses=tuple(lane_course[int(n)] for n in finish.split("-"))
            unique[r["race_code"]]={"venue":r.get("venue",""),"race_code":r["race_code"],
                "finish_courses":courses,"finish_lanes":finish,
                "decision":result.get("decision") or "未記録"}
    return sorted(unique.values(),key=lambda x:x["race_code"])

def summarize(rows):
    positions={str(course):{"first":0,"second":0,"third":0,"top3":0} for course in range(1,7)}
    venue_counts=Counter()
    attack=defaultdict(lambda:{"total":0,"second_outside":0,"third_outside":0,"fifth_second":0,"sixth_second":0})
    for r in rows:
        venue_counts[r["venue"]]+=1
        finish=r["finish_courses"]
        for place,course in enumerate(finish):
            positions[str(course)][("first","second","third")[place]]+=1
            positions[str(course)]["top3"]+=1
        winner,second,third=finish
        if winner in (3,4,5,6) and r["decision"] in ("まくり","まくり差し"):
            item=attack[str(winner)]
            item["total"]+=1
            item["second_outside"]+=int(second>winner)
            item["third_outside"]+=int(third>winner)
            item["fifth_second"]+=int(second==5)
            item["sixth_second"]+=int(second==6)
    n=len(rows)
    rates={}
    for course,raw in positions.items():
        rates[course]={
            "n":n,
            "first":raw["first"],"second":raw["second"],"third":raw["third"],
            "first_rate":round(raw["first"]/n,4) if n else None,
            "second_rate":round(raw["second"]/n,4) if n else None,
            "third_rate":round(raw["third"]/n,4) if n else None,
            "top3_rate":round(raw["top3"]/n,4) if n else None
        }
    return {
        "schema":"boatlabs.outside_course_research.v1",
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "source":"archived BoatraceCSV/realtime_unofficial, race-course mapping required",
        "sample_races":n,"course_finish":rates,
        "venue_sample_counts":dict(sorted(venue_counts.items())),
        "outside_attack_follow":{c:dict(v) for c,v in sorted(attack.items())},
        "assessment":"insufficient_for_parameter_learning" if n<250 else "descriptive_only_not_calibrated",
        "min_sample_threshold":250,
        "caveat":"Retrospective outcome study; source capture is NOT proof of pre-cutoff availability. In-sample frequency is not a predictive win probability. NEVER rewrite any frozen SHA/bets.",
    }

def research(source_dir=DATA_DIR):
    docs=[]
    for file in sorted(source_dir.glob("????-??-??.json")):
        try:
            docs.append(json.loads(file.read_text(encoding="utf-8")))
        except (OSError,ValueError):
            continue
    return summarize(rows_from_docs(docs))

def main():
    output=DATA_DIR/"outside-role-research-latest.json"
    result=research()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Outside-course research: {result['sample_races']} valid results / {result['assessment']}")

if __name__=="__main__":
    main()
