"""BOAT LAB retrospective WAKE HYPOTHESIS study, never measured wake contact.

Official beginner guides affirm that following boats can suffer from the
leader's wake, especially from 1st lap 2M onward. Archived race results
contain finishes and winner's decision method, NOT wake positions, contact
timestamps, or motion footage. This script only studies finish-order proxies.

The output must NEVER be fed to same-day pre-cutoff forecasts, rewritten
frozen bets, or published as calibrated wake-contact probabilities.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from scripts.research_outside_roles import rows_from_docs, DATA_DIR

SOURCE_DOCS = [
    "https://www.kojimaboat.jp/beginner_guide.html",
    "https://www.boatrace-tokuyama.jp/modules/beginner/",
    "https://guide.boatrace-suminoe.jp/jp/basic_race.html",
    "https://www.oregon.gov/osmb/boater-info/pages/wake.aspx",
]
ATTACKS = {"まくり", "まくり差し"}
MIN_SAMPLE = 30

def summarize(rows):
    buckets = defaultdict(lambda: {"races":0,"inner_second":0,"inner_third":0,
      "inner_both_top3":0,"next_course_second":0,"next_course_third":0,
      "outside_second":0})
    all_rows = 0
    for row in rows:
        if not isinstance(row,dict): continue
        fins=row.get("finish_courses")
        if not isinstance(fins,(tuple,list)) or len(fins)!=3: continue
        try: head,second,third=(int(x) for x in fins)
        except (ValueError,TypeError): continue
        if len({head,second,third})!=3 or not all(1<=x<=6 for x in (head,second,third)):
            continue
        decision=row.get("decision") or "未記録"
        if decision not in {"逃げ","差し","まくり","まくり差し","抜き","恵まれ"}:
            decision="未記録"
        all_rows += 1
        bucket=("center_outer_attack" if head>=3 and decision in ATTACKS
                else "inside_1_escape" if head==1 and decision=="逃げ"
                else "other_winner")
        keys=[bucket,bucket+"@"+str(head)]
        for key in keys:
            out=buckets[key]
            out["races"] += 1
            out["inner_second"] += int(second<head)
            out["inner_third"] += int(third<head)
            out["inner_both_top3"] += int(second<head and third<head)
            out["next_course_second"] += int(head<6 and second==head+1)
            out["next_course_third"] += int(head<6 and third==head+1)
            out["outside_second"] += int(second>head)
    report=[]
    for label,item in sorted(buckets.items()):
        n=item["races"]
        report.append({"segment":label,"sample":n,"counts":dict(item),
          "descriptive_fractions":{key:round(item[key]/n,4)
            for key in ("inner_second","inner_third","inner_both_top3",
                        "next_course_second","next_course_third","outside_second")},
          "support":"descriptive_only" if n>=MIN_SAMPLE else "too_few_cases"})
    return {
      "schema":"boatlabs.wake_scenario_outcomes.v0.8",
      "created_at_utc":datetime.now(timezone.utc).isoformat(),
      "sample_races":all_rows,
      "source":"existing BoatraceCSV/realtime_unofficial archived race results",
      "official_background_urls":SOURCE_DOCS,
      "segments":report,
      "missing_physical_observations":["actual_boat_trajectories",
        "wake_crossing_per_boat","wake_contact_time","wake_height_at_contact",
        "speed_loss_after_contact","2m_passages"],
      "warning":"Outcome-based survivor/follower proxies do NOT observe wake contact. Never claim measured speed loss, predictive calibration or true wake probabilities.",
      "predictor_training":"disabled",
      "frozen_forecasts":"unchanged",
    }

def research(source_dir=DATA_DIR):
    docs=[]
    for path in sorted(Path(source_dir).glob("????-??-??.json")):
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError,OSError): continue
    return summarize(rows_from_docs(docs))

def main():
    result=research()
    file=Path(DATA_DIR)/"wake-study-latest.json"
    file.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wake scenario hypotheses: {result['sample_races']} archived outcome rows; no observed wake contacts")

if __name__=="__main__":
    main()
