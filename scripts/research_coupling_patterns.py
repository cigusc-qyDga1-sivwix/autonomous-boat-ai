"""Descriptive interaction evidence from archived outcomes; NEVER train/freeze from results.

A winner's official/archived decision plus final rank is NOT a measurement of
who crossed which wake at 1M. This analysis flags hypotheses for manual video
labeling; it never writes predictive weights or immutable pre-race snapshots.
"""
from __future__ import annotations
import json
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
from scripts.research_outside_roles import rows_from_docs, DATA_DIR

DECISIONS = {"まくり", "まくり差し", "逃げ", "差し", "抜き", "恵まれ"}
MIN_SUPPORT = 30

def summarize(rows):
    patterns = defaultdict(lambda: Counter())
    coverage = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        courses = row.get("finish_courses")
        if not isinstance(courses, (tuple, list)) or len(courses) != 3:
            continue
        try:
            a, b, c = (int(v) for v in courses)
        except (TypeError, ValueError):
            continue
        if len({a,b,c}) != 3 or not all(1 <= v <= 6 for v in (a,b,c)):
            continue
        decision = row.get("decision") or "未記録"
        if decision not in DECISIONS:
            decision = "未記録"
        family = "outside_attack" if a>=3 and decision in {"まくり", "まくり差し"} else "other"
        key=(family,str(a),decision)
        p=patterns[key]
        p["total"] += 1
        p["following_course_second"] += int(a < 6 and b == a+1)
        p["following_course_third"] += int(a < 6 and c == a+1)
        p["inside_course_second"] += int(b < a)
        p["inside_course_third"] += int(c < a)
        p["both_inside_top3"] += int(b < a and c < a)
        coverage[row.get("venue") or "不明"] += 1
    slices=[]
    for (family,course,decision),p in sorted(patterns.items()):
        n=p["total"]
        rates={name:round(p[name]/n,4) for name in (
            "following_course_second","following_course_third",
            "inside_course_second","inside_course_third","both_inside_top3")}
        slices.append({
            "family":family,"winner_course":int(course),"reported_winning_decision":decision,
            "n":n,"counts":dict(p),"rates":rates,
            "support_status":"descriptive_only" if n>=MIN_SUPPORT else "insufficient_support",
            "min_support":MIN_SUPPORT
        })
    return {
        "schema":"boatlabs.six_boat_coupling_patterns.v1",
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "n_valid_results":sum(coverage.values()),
        "venue_n":dict(sorted(coverage.items())),
        "segments":slices,
        "source":"archived BoatraceCSV/realtime_unofficial results from pre-existing research",
        "critical_limits":[
            "Race outcome, reported winner technique and final 1-2-3 ranking are OBSERVED outcomes, not a video observation of other boats' maneuvers.",
            "Do not infer wave crossings, boat coordinates, actual paths or exact 1M timing from these results.",
            "Descriptive support thresholds are not calibration or proof of generalization.",
            "Never use this data in a pre-cutoff forecast or alter old frozen snapshots."
        ],
        "video_label_fields_needed":[
            "entry_course_confirmed","start_lead_per_boat","1m_attack_course",
            "attack_type","inner_boat_displaced","gap_opened","follower_course",
            "backstretch_order","2m_order","final_order","video_review_source"
        ]
    }

def research(source_dir=DATA_DIR):
    docs=[]
    for path in sorted(Path(source_dir).glob("????-??-??.json")):
        try: docs.append(json.loads(path.read_text(encoding="utf8")))
        except (ValueError, OSError): continue
    return summarize(rows_from_docs(docs))

def main():
    result=research()
    out=DATA_DIR/"coupling-patterns-latest.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(f"6-boat course/finish research: {result['n_valid_results']} validated rows; retrospective-only")

if __name__=="__main__":main()
