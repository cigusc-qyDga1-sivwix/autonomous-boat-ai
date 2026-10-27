"""BOAT LAB 2026-10-28 morning/day/night first-turn VIDEO study audit.

This is an observation ledger, NOT a trained video model. Public historical
exhibition / unofficial result rows are mirrored for 3 venues, with evidence
gaps explicit. Nothing here rewrites/feeds forecasts or the official ledger.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

JST=ZoneInfo("Asia/Tokyo")
STUDY_DAY="2026-10-28"
SCHEMA="boatlabs.turn_video_three_venues.v1"
PLACES={
    "morning":{"venue":"唐津","venue_code":"23","focus":"①の旋回軌道と内側に生じる差し場"},
    "day":{"venue":"児島","venue_code":"16","focus":"ターンの流れ・立ち上がり・2〜3着追走"},
    "night":{"venue":"蒲郡","venue_code":"07","focus":"①の逃げ失敗と③〜⑥の攻め連動"},
}
MISSING_VIDEO={
    "status":"NO_LICENSED_VIDEO_ANALYZED",
    "turn_mark_clearance_m":None,
    "turn_radius_m":None,
    "turn_exit_speed_ratio":None,
    "confirmed_boat_tracks":0,
    "inside_gap_observed":None,
    "reason":"Official video machine-use permission and verified first-mark tracks are not established.",
}
RECORD_VERSION=1


def sha(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,
            separators=(",",":")).encode("utf-8")).hexdigest()


def check_time(value):
    try:
        if not isinstance(value,str):
            return None
        result=datetime.fromisoformat(value.replace("Z","+00:00"))
        return result if result.tzinfo else None
    except (TypeError,ValueError):
        return None


def race_cutoff(day,HHMM):
    try:
        if not isinstance(HHMM,str) or len(HHMM)!=5:
            return None
        hh,mm=map(int,HHMM.split(":"))
        return datetime.fromisoformat(day+"T"+f"{hh:02d}:{mm:02d}:00+09:00")
    except (ValueError,TypeError):
        return None


def valid_research_row(row,day,venue_code,number):
    if not isinstance(row,dict):
        return False
    code=day.replace("-","")+venue_code+f"{number:02d}"
    if row.get("race_code")!=code or row.get("venue_code")!=venue_code or row.get("race")!=number:
        return False
    if not isinstance(row.get("boats"),list) or len(row["boats"])!=6:
        return False
    return sorted(b.get("lane") for b in row["boats"] if isinstance(b,dict))==[1,2,3,4,5,6]


def _numeric_excerpt(row):
    """Descriptive inputs, NOT turn-video scores and NOT a forecast."""
    boats=row["boats"]
    return [{
        "lane":b["lane"],"name":b.get("name"),
        "entry_course":b.get("course"),"exhibition_st":b.get("exhibition_st"),
        "exhibition_f":b.get("exhibition_f"),
        "exhibition_time":b.get("exhibition_time"),
        "tilt":b.get("tilt"),
        "original_exhibition":b.get("original_exhibition") or [],
    } for b in sorted(boats,key=lambda b:b["lane"])]


def outcome_label(row):
    """Only label 1-course escape outcome; never infer a turn mistake.

    Source results are unofficial until separately verified with BOATRACE.
    An entry reshuffle changes which boat actually has course 1.
    """
    if not isinstance(row,dict) or not isinstance(row.get("result"),dict):
        return {"state":"RESULT_UNAVAILABLE","first_mark_cause":"UNOBSERVED"}
    results=row["result"]
    finish=results.get("finish")
    if not isinstance(finish,str) or len(finish)!=5:
        return {"state":"RESULT_INVALID","first_mark_cause":"UNOBSERVED"}
    lanes=finish.split("-")
    if len(lanes)!=3 or len(set(lanes))!=3 or any(x not in "123456" or len(x)!=1 for x in lanes):
        return {"state":"RESULT_INVALID","first_mark_cause":"UNOBSERVED"}
    inside=next((b["lane"] for b in row["boats"] if b.get("course")==1),None)
    if inside is None:
        classification="COURSE_ONE_UNKNOWN"
    elif str(inside)==lanes[0]:
        classification="COURSE_ONE_WON"
    else:
        classification="COURSE_ONE_LOST"
    return {
        "state":"UNOFFICIAL_RESULT_RESEARCH_ONLY",
        "first_mark_cause":"UNOBSERVED",
        "course_one_boat":inside,
        "outcome":classification,
        "finish":finish,
        "decision":results.get("decision"),
        "source":results.get("source"),
        "source_observed_jst":results.get("recorded_jst"),
        "escape_failed_by_turn_error":None,
        "note":"Winner, tactics and turn mistake are different. Video evidence is required for turn-cause labels.",
    }


def _blank(day,now):
    cases=[]
    for part,config in PLACES.items():
        for r in range(1,13):
            cases.append({
                "race_key":day.replace("-","")+config["venue_code"]+f"{r:02d}",
                "session":part,"venue":config["venue"],"venue_code":config["venue_code"],"race":r,
                "focus":config["focus"],"cutoff_jst":None,
                "data_status":"WAITING_EXHIBITION_DATA",
                "first_captured_at_utc":None,
                "first_numeric_observation":None,
                "earliest_observation_before_cutoff":"UNCONFIRMED",
                "outcome":{"state":"RESULT_UNAVAILABLE","first_mark_cause":"UNOBSERVED"},
                "video":dict(MISSING_VIDEO),
            })
    return {
        "schema":SCHEMA,"event_date":day,"created_at_utc":now.isoformat(),
        "updated_at_utc":now.isoformat(),
        "format_version":RECORD_VERSION,
        "scope":"12R each: 23唐津 morning / 16児島 day / 07蒲郡 night",
        "source":"BoatraceCSV exhibition archive, not a video stream",
        "model_state":"UNTRAINED_TURN_VIDEO_RESEARCH_PILOT",
        "video_auto_ingestion":"DISABLED_NO_CONFIRMED_RIGHTS",
        "forecast_status":"UNMODIFIED",
        "official_settlement_status":"UNMODIFIED",
        "targets":cases,
        "summary":{},
    }


def build(day, archived, previous=None, *, now=None):
    if day!=STUDY_DAY:
        raise ValueError("this isolated study is for 2026-10-28 only")
    timestamp=now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("timezone_aware_now_required")
    ledger=_blank(day,timestamp)
    if isinstance(previous,dict) and previous.get("schema")==SCHEMA and previous.get("event_date")==day:
        old={x.get("race_key"):x for x in previous.get("targets",[]) if isinstance(x,dict)}
    else:
        old={}
    if not isinstance(archived,dict) or archived.get("event_date")!=day or archived.get("schema")!="boatlabs.exhibition_research.v1":
        records=[]
        source_state="NOT_AVAILABLE_OR_UNVERIFIED"
    else:
        records=archived.get("records") if isinstance(archived.get("records"),list) else []
        source_state="RESEARCH_ARCHIVE_READ"
    bycode={r.get("race_code"):r for r in records if isinstance(r,dict)}
    for target in ledger["targets"]:
        key=target["race_key"]
        prior=old.get(key,{})
        # First accepted capture is immutable and cannot be backfilled post-cutoff.
        for field in ("first_captured_at_utc","first_numeric_observation","earliest_observation_before_cutoff"):
            if field in prior:
                target[field]=prior[field]
        row=bycode.get(key)
        if not valid_research_row(row,day,target["venue_code"],target["race"]):
            # Retain evidence from an earlier successful run during transient data errors.
            if target["first_numeric_observation"]:
                target["data_status"]="FIRST_NUMERIC_OBSERVATION_PRESERVED"
            continue
        cutoff=race_cutoff(day,row.get("cutoff_jst"))
        target["cutoff_jst"]=row.get("cutoff_jst")
        observed=check_time(row.get("source_observed_jst"))
        first_seen=check_time(row.get("first_seen_at_utc"))
        source_is_before=bool(cutoff and observed and first_seen and
                             observed<cutoff and first_seen<cutoff)
        # "first_seen" is source import timestamp, not independent forecast freeze.
        first_here_is_before=bool(cutoff and timestamp.astimezone(JST)<cutoff)
        if target["first_numeric_observation"] is None:
            if source_is_before and first_here_is_before:
                values=_numeric_excerpt(row)
                evidence={
                    "archive_first_seen_at_utc":row.get("first_seen_at_utc"),
                    "archive_source_observed_jst":row.get("source_observed_jst"),
                    "pilot_capture_at_utc":timestamp.isoformat(),
                    "boats":values,"weather":row.get("weather") or {},
                    "provenance":"PRE_CUTOFF_RESEARCH_OBSERVATION_NOT_FORMAL_FORECAST",
                }
                target["first_captured_at_utc"]=timestamp.isoformat()
                target["first_numeric_observation"]={"sha256":sha(evidence),**evidence}
                target["earliest_observation_before_cutoff"]="OBSERVED_RESEARCH_ONLY_NOT_SHA_FROZEN_FORECAST"
            else:
                target["earliest_observation_before_cutoff"]="NOT_CONFIRMED_PRIOR_TO_CUTOFF"
        target["data_status"]="SIX_BOAT_EXHIBITION_RESEARCH_AVAILABLE"
        target["latest_numeric_source_observed_jst"]=row.get("source_observed_jst")
        target["outcome"]=outcome_label(row)
        # No archive fields are permitted to claim that a particular turn caused the outcome.
        target["video"]=dict(MISSING_VIDEO)
    counts={
        "target_races":len(ledger["targets"]),
        "exhibition_rows_seen":sum(t["data_status"]=="SIX_BOAT_EXHIBITION_RESEARCH_AVAILABLE" for t in ledger["targets"]),
        "precutoff_numeric_pilot_captures":sum(t["first_numeric_observation"] is not None for t in ledger["targets"]),
        "unofficial_result_rows":sum(t["outcome"]["state"]=="UNOFFICIAL_RESULT_RESEARCH_ONLY" for t in ledger["targets"]),
        "course_one_wins_unofficial":sum(t["outcome"].get("outcome")=="COURSE_ONE_WON" for t in ledger["targets"]),
        "course_one_losses_unofficial":sum(t["outcome"].get("outcome")=="COURSE_ONE_LOST" for t in ledger["targets"]),
        "video_races_analyzed":0,
        "turn_mistakes_verified":0,
    }
    ledger["summary"]=counts
    ledger["source_status"]=source_state
    ledger["source_created_at_utc"]=archived.get("created_at_utc") if isinstance(archived,dict) else None
    ledger["evidence_policy"]=(
        "No licensed videos currently analyzed. Exhibition figures and unofficial results "
        "cannot prove that a turn was wide, a speed loss occurred, or an inside gap existed. "
        "Results are never inputs to a prestart forecast.")
    return ledger


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default=STUDY_DAY)
    p.add_argument("--exhibition",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.date!=STUDY_DAY:
        p.error("study date is fixed to 2026-10-28")
    source=args.exhibition or Path(f"app/data/exhibition/{STUDY_DAY}.json")
    output=args.out or Path(f"app/data/experiments/turn-video-pilot-{STUDY_DAY}.json")
    try:
        archive=json.loads(source.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        archive=None
    try:
        previous=json.loads(output.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        previous=None
    outcome=build(STUDY_DAY,archive,previous)
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(output)
    print(json.dumps({"path":str(output),"source":outcome["source_status"],
                     "summary":outcome["summary"]},ensure_ascii=False))


if __name__=="__main__":
    main()
