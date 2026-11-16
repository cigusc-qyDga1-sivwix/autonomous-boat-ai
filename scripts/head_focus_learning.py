"""Post-race observational learning only: immutable pre-cutoff signals vs official outcomes.

This NEVER changes model coefficients, ticket allocation, forecasts, or historical
records. The official result is used to LABEL cohorts, never to generate features.
Missing pre-race evidence stays in an explicit unknown cohort.
"""
from __future__ import annotations
import math

VERSION = "head-focus-observational-v0.1"
ST_GAP_SECONDS = .05
MOTOR_GAP_POINTS = 10.0
WIN_RATE_GAP_POINTS = 1.5


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value)


def _summary(rows):
    n=len(rows)
    return {
        "verified_races":n,
        "lane1_wins":sum(r["actual_head"]=="1" for r in rows),
        "outside_wins":sum(r["actual_head"]!="1" for r in rows),
        "first_ticket_head1":sum(r["first_bet_head"]=="1" for r in rows),
        "only_lane1_head_bets":sum(r["only_lane1_head_bets"] for r in rows),
        "outside_win_head_misses":sum(r["actual_head"]!="1" and r["stage"]=="head_miss" for r in rows),
        "outside_win_lane1_second":sum(r["actual_head"]!="1" and r["actual_second"]=="1" for r in rows),
        "head_misses":sum(r["stage"]=="head_miss" for r in rows),
        "second_misses":sum(r["stage"]=="second_miss" for r in rows),
        "third_misses":sum(r["stage"]=="third_miss" for r in rows),
        "hits":sum(r["stage"]=="hit" for r in rows),
        "outside_win_share":round(sum(r["actual_head"]!="1" for r in rows)/n,5) if n else None,
    }


def inspect(forecasts, verified):
    """Only accepted official rows whose race/venue/SHA matches the saved input."""
    sources={(r.get("venue"),r.get("race"),r.get("sha256")):r
             for r in forecasts if isinstance(r,dict)}
    formal=[]
    buckets={"0":[],"1":[],"2_or_more":[],"insufficient_pre_cutoff_evidence":[]}
    feature_counts={"inner_slower_exhibition_st_005":0,"outside_motor_10pt_stronger":0,
                    "outside_national_win_rate_15_stronger":0,"lane1_not_in_course1":0}
    for row in verified:
        if row.get("ticket_status")!="formal":
            continue
        r=sources.get((row.get("venue"),row.get("race"),row.get("snapshot_sha256")))
        if not r or r.get("phase")!="exhibition":
            continue
        bets=r.get("bets") or []
        head_set={b.get("combination","")[:1] for b in bets if isinstance(b,dict)}
        item={**row, "only_lane1_head_bets":head_set=={"1"},
              "actual_second":row.get("actual_finish","").split("-")[1]
              if isinstance(row.get("actual_finish"),str)
              and len(row["actual_finish"].split("-"))==3 else ""}
        formal.append(item)
        racers=r.get("racers") or []
        if not isinstance(racers,list) or len(racers)!=6:
            buckets["insufficient_pre_cutoff_evidence"].append(item)
            continue
        by_lane={v.get("lane"):v for v in racers if isinstance(v,dict)
                 and type(v.get("lane")) is int and 1<=v["lane"]<=6}
        if len(by_lane)!=6:
            buckets["insufficient_pre_cutoff_evidence"].append(item)
            continue
        lanes=[by_lane[i] for i in range(1,7)]
        # All 6 boats and all 3 numeric input families must be present.
        families=[[ _number(v.get(key)) for v in lanes] for key in
                  ("exhibition_st","motor_top_2_percent","national_win_rate")]
        if any(any(v is None for v in values) for values in families):
            buckets["insufficient_pre_cutoff_evidence"].append(item)
            continue
        st,motor,skill=families
        signals={
            "inner_slower_exhibition_st_005":st[0]-min(st[1:])>=ST_GAP_SECONDS,
            "outside_motor_10pt_stronger":max(motor[1:])-motor[0]>=MOTOR_GAP_POINTS,
            "outside_national_win_rate_15_stronger":max(skill[1:])-skill[0]>=WIN_RATE_GAP_POINTS,
            "lane1_not_in_course1":lanes[0].get("course")!=1,
        }
        for name,active in signals.items():
            feature_counts[name]+=int(active)
        count=sum(signals.values())
        buckets["2_or_more" if count>=2 else str(count)].append(item)
    return {
        "schema":VERSION,
        "source":"SHA-matched official outcomes with immutable pre-cutoff race features",
        "only_verified_formal_exhibition":True,
        "postrace_labels_not_forecast_inputs":True,
        "research_only":True,
        "formal_forecasts_modified":False,
        "formal":_summary(formal),
        "fixed_pre_cutoff_signal_thresholds":{
            "inside_st_slower_than_fastest_outside_seconds":ST_GAP_SECONDS,
            "best_outside_motor_advantage_percentage_points":MOTOR_GAP_POINTS,
            "best_outside_national_win_rate_advantage":WIN_RATE_GAP_POINTS,
            "lane1_actual_course_not_1":True,
        },
        "cohorts":{name:_summary(items) for name,items in buckets.items()},
        "signal_counts":feature_counts,
        "notes":[
            "A single observational day is not evidence that these thresholds predict winner changes.",
            "These thresholds are research buckets only, never used to select or modify bets.",
            "Insufficient pre-cutoff features are not silently treated as low risk.",
            "Compare forward-frozen alternatives for >=100 official-verified matched races before promotion.",
        ],
    }
