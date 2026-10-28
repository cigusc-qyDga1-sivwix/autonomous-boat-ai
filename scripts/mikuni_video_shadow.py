"""Independent pre-cutoff six-boat video-motion *shadow* forecast.

Never overwrites main/frozen v1.5; never generates retrospectively. It requires
six externally VERIFIED calibrated boat trajectories tied to the same video SHA.
Unverified colour blobs are NOT inputs. Since no verified tracker exists yet,
live operation correctly yields "awaiting_verified_tracks" and zero bets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

SCHEMA="boatlabs.mikuni_video_motion_shadow_v0.1"
TRACK_SCHEMA="boatlabs.verified_six_boat_tracks.v1"
SOURCE_SCHEMA="boatlabs.mikuni_authorized_video_ingestion.v1"
JST=timezone(timedelta(hours=9))
LEAD=timedelta(seconds=120)
BUDGET=50_000
MODEL="mikuni-video-six-boat-shadow-v0.1-UNCALIBRATED"


def utc(value):
    try:
        x=datetime.fromisoformat(value.replace("Z","+00:00"))
        return x.astimezone(timezone.utc) if x.tzinfo is not None else None
    except (TypeError,ValueError,AttributeError):
        return None


def hexdigest(data):
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,
                                     separators=(",",":")).encode("utf-8")).hexdigest()


def valid_bets(bets):
    if not isinstance(bets,list) or not 1<=len(bets)<=120:
        return False
    names=[]
    for b in bets:
        if not isinstance(b,dict):return False
        comb=b.get("combination")
        if not isinstance(comb,str) or len(comb)!=5 or comb[1::2]!="--":
            return False
        lanes=comb[::2]
        if len(lanes)!=3 or len(set(lanes))!=3 or any(v not in "123456" for v in lanes):
            return False
        stake=b.get("virtual_yen")
        if isinstance(stake,bool) or not isinstance(stake,int) or stake<100 or stake%100:
            return False
        names.append(comb)
    return len(set(names))==len(names) and sum(b["virtual_yen"] for b in bets)==BUDGET


def _track_score(observations):
    """Pixel-free *metre-based* movement, separated into stretch and turn.

    Segment names have precise meanings. Ignore frames that cannot be
    independently assigned to a particular verified boat and calibrated area.
    """
    if not isinstance(observations,list) or len(observations)<8:
        raise ValueError("insufficient_verified_trajectory")
    groups={name:[] for name in ("start_early","start_late","turn_entry","turn_exit")}
    for sample in observations:
        if not isinstance(sample,dict):raise ValueError("invalid_sample")
        part=sample.get("segment")
        if part not in groups:continue
        t=sample.get("t_seconds");xy=sample.get("xy_m")
        if (isinstance(t,bool) or not isinstance(t,(int,float)) or
            not math.isfinite(t) or t<0 or not isinstance(xy,list) or len(xy)!=2 or
            any(isinstance(q,bool) or not isinstance(q,(int,float)) or
                not math.isfinite(q) or abs(q)>1000 for q in xy)):
            raise ValueError("invalid_calibrated_position")
        groups[part].append((float(t),tuple(map(float,xy))))
    speeds={}
    for part,items in groups.items():
        items.sort()
        if len(items)<2 or any(b[0]<=a[0] for a,b in zip(items,items[1:])):
            raise ValueError("missing_verified_segment")
        intervals=[]
        for a,b in zip(items,items[1:]):
            dt=b[0]-a[0]
            speed=math.hypot(b[1][0]-a[1][0],b[1][1]-a[1][1])/dt
            if not .2<=speed<=30:raise ValueError("implausible_boat_speed")
            intervals.append(speed)
        speeds[part]=round(sum(intervals)/len(intervals),3)
    return {
        "start_early_speed_mps":speeds["start_early"],
        "start_late_speed_mps":speeds["start_late"],
        "turn_entry_speed_mps":speeds["turn_entry"],
        "turn_exit_speed_mps":speeds["turn_exit"],
        "stretch_acceleration_ratio":round(speeds["start_late"]/speeds["start_early"],4),
        "turn_exit_entry_ratio":round(speeds["turn_exit"]/speeds["turn_entry"],4),
        "units":"mps_and_ratio_verified_input_not_actual_race_ST",
    }


def validate_six_tracks(record,observed_media,now,cutoff):
    """All six IDs, provenance, integrity, calibration and timestamps required."""
    if not isinstance(record,dict) or not isinstance(observed_media,dict):
        raise ValueError("verified_six_boat_tracks_missing")
    if observed_media.get("status")!="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY":
        raise ValueError("source_video_not_captured")
    if record.get("source_sha256")!=observed_media.get("source_sha256") or len(str(record.get("source_sha256","")))!=64:
        raise ValueError("video_digest_mismatch")
    if record.get("verification_kind")!="independent_camera_calibrated_six_boat_tracks":
        raise ValueError("unverified_boat_identity")
    if record.get("camera_calibration_confirmed") is not True or record.get("camera_motion_compensated") is not True:
        raise ValueError("camera_calibration_unverified")
    captured=utc(record.get("captured_at_utc"))
    verified=utc(record.get("verified_at_utc"))
    media_time=utc(observed_media.get("captured_at_utc"))
    if not captured or not verified or not media_time:
        raise ValueError("timing_or_capture_evidence_missing")
    if not captured<=verified<=now<=cutoff-LEAD or media_time>now or media_time>verified:
        raise ValueError("not_verified_before_cutoff")
    boats=record.get("boats")
    if not isinstance(boats,list) or len(boats)!=6:
        raise ValueError("not_six_boats")
    result={}
    for boat in boats:
        lane=boat.get("lane") if isinstance(boat,dict) else None
        q=boat.get("identity_confidence") if isinstance(boat,dict) else None
        if (isinstance(lane,bool) or not isinstance(lane,int) or lane not in range(1,7)
            or lane in result or not isinstance(q,(int,float)) or isinstance(q,bool)
            or not .93<=q<=1.0):
            raise ValueError("identity_confidence_or_lane_invalid")
        result[lane]=_track_score(boat.get("observations"))
    if len(result)!=6:raise ValueError("not_six_boats")
    return result


def score_by_lane(metrics):
    # Scores are only **uncalibrated exploratory modifiers**, not win probabilities.
    raw={lane:(
       .55*(m["stretch_acceleration_ratio"]-1)
       +.45*(m["turn_exit_entry_ratio"]-1))
       for lane,m in metrics.items()}
    mean=sum(raw.values())/6
    return {lane:max(-1.0,min(1.0,round((raw[lane]-mean)*2.0,5))) for lane in range(1,7)}


def redistribute_shadow(source,signals):
    """Only adjust a set of valid original tickets; never alter main version."""
    if not valid_bets(source):raise ValueError("invalid_main_bets")
    ratios=[]
    for bet in source:
        lanes=[int(x) for x in bet["combination"].split("-")]
        delta=.15*signals[lanes[0]]+.10*signals[lanes[1]]+.05*signals[lanes[2]]
        ratios.append(float(bet["virtual_yen"])*math.exp(delta))
    free_units=BUDGET//100-len(source)
    total=sum(ratios)
    floor=[math.floor(x/total*free_units) for x in ratios]
    balance=free_units-sum(floor)
    fractions=sorted(range(len(source)),key=lambda i:(-(ratios[i]/total*free_units-floor[i]),i))
    for i in fractions[:balance]:floor[i]+=1
    output=[{**b,"virtual_yen":(floor[i]+1)*100,
             "video_shadow_modifier_uncalibrated":round(ratios[i]/b["virtual_yen"],6)}
            for i,b in enumerate(source)]
    if not valid_bets(output):raise ValueError("invalid_shadow_allocation")
    return output


def build(day,live,media,tracks,previous=None,*,now=None):
    datetime.strptime(day,"%Y-%m-%d")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("timezone_required")
    if previous and previous.get("schema")==SCHEMA and previous.get("event_date")==day:
        rows=list(previous.get("records",[]))
    else:rows=[]
    seen={(r["venue"],r["race"]) for r in rows if isinstance(r,dict)}
    rejected=[]
    if not isinstance(live,dict) or live.get("event_date")!=day:
        return _wrap(day,now,rows,[{"reason":"current_forecast_snapshot_unavailable"}])
    if not isinstance(media,dict) or media.get("schema")!=SOURCE_SCHEMA or media.get("event_date")!=day:
        return _wrap(day,now,rows,[{"reason":"current_video_source_ledger_unavailable"}])
    indexed={}
    if isinstance(tracks,dict) and tracks.get("schema")==TRACK_SCHEMA and tracks.get("event_date")==day and tracks.get("venue_code")=="10":
        indexed={t["race"]:t for t in tracks.get("records",[]) if isinstance(t,dict) and isinstance(t.get("race"),int) and t.get("race") in range(1,13)}
    for entry in live.get("forecast_races",[]):
        if not isinstance(entry,dict) or entry.get("venue")!="三国":continue
        race=entry.get("race")
        if isinstance(race,bool) or not isinstance(race,int) or not 1<=race<=12:continue
        if ("三国",race) in seen:continue
        cutoff_jst=entry.get("cutoff_iso_jst")
        try:
            cutoff=datetime.fromisoformat(cutoff_jst) if cutoff_jst else datetime.fromisoformat(
                day+"T"+entry["cutoff_jst"]+":00+09:00")
        except (TypeError,ValueError,KeyError):
            rejected.append({"race":race,"reason":"invalid_cutoff"});continue
        if cutoff.tzinfo is None:rejected.append({"race":race,"reason":"invalid_cutoff"});continue
        cutoff=cutoff.astimezone(timezone.utc)
        # Fail closed. Even valid frames after cutoff cannot produce a pre-race revision.
        if now>cutoff-LEAD:
            rejected.append({"race":race,"reason":"too_late_to_freeze_video_shadow"});continue
        if (entry.get("phase")!="exhibition" or entry.get("ticket_status")!="formal"
            or entry.get("entry_exhibition_gate",{}).get("final_eligible") is not True
            or entry.get("model_version")!="four-factor-v1.5-point-free-untrained"
            or entry.get("formal_snapshot_sha256")!=entry.get("sha256")
            or not isinstance(entry.get("sha256"),str) or len(entry["sha256"])!=64):
            rejected.append({"race":race,"reason":"verified_exhibition_formal_v15_required"});continue
        model_bets=entry.get("bets")
        if not valid_bets(model_bets):
            rejected.append({"race":race,"reason":"invalid_frozen_bets"});continue
        source=media.get("races",{}).get(str(race))
        try:
            metrics=validate_six_tracks(indexed.get(race),source,now,cutoff)
            signals=score_by_lane(metrics)
            revised=redistribute_shadow(model_bets,signals)
        except (TypeError,KeyError,ValueError) as exc:
            rejected.append({"race":race,"reason":str(exc)[:75]});continue
        data={
            "venue":"三国","race":race,"event_date":day,
            "frozen_at_utc":now.astimezone(timezone.utc).isoformat(),
            "cutoff_jst":cutoff.astimezone(JST).strftime("%H:%M"),
            "baseline_sha256":entry["sha256"],
            "source_video_sha256":source["source_sha256"],
            "track_evidence_sha256":hexdigest(indexed[race]),
            "model":MODEL,"model_role":"prospective_experimental_shadow_only",
            "source_bets":model_bets,"shadow_bets":revised,
            "six_boat_video_metrics":metrics,
            "lane_uncalibrated_signal":signals,
            "verified_before_cutoff":True,"result_data_used":False,
            "actual_placing_used":False,"odds_used":False,
            "formal_buy_and_settlement_unchanged":True,
            "virtual_budget_yen":BUDGET,
            "research_note":"A/B shadow, not adopted. 6 calibrated input tracks verified; model coefficients NOT calibrated.",
        }
        data["record_sha256"]=hexdigest(data)
        rows.append(data);seen.add(("三国",race))
    return _wrap(day,now,rows,rejected)


def _wrap(day,now,records,rejected):
    records.sort(key=lambda r:(r.get("race",0),r.get("frozen_at_utc","")))
    return {
        "schema":SCHEMA,"event_date":day,"venue":"三国",
        "updated_at_utc":now.astimezone(timezone.utc).isoformat(),
        "records":records,"rejected":rejected,
        "summary":{"video_shadow_frozen_races":len(records),
                   "unverified_or_unavailable_races":len(rejected),
                   "formal_forecasts_modified":0,"video_not_assumed_to_be_verified":True},
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",default=datetime.now(JST).date().isoformat())
    args=parser.parse_args(argv)
    base=Path("app/data")
    read=lambda p:json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    live=read(base/"live"/f"{args.date}.json")
    media=read(base/"experiments"/f"mikuni-video-auto-{args.date}.json")
    tracks=read(base/"experiments"/f"mikuni-tracks-verified-{args.date}.json")
    destination=base/"experiments"/f"mikuni-video-shadow-{args.date}.json"
    previous=read(destination)
    old_shas={(r["venue"],r["race"]):r["record_sha256"] for r in
              (previous or {}).get("records",[])}
    current=build(args.date,live,media,tracks,previous)
    for row in current["records"]:
        key=(row["venue"],row["race"])
        if key in old_shas and old_shas[key]!=row["record_sha256"]:
            raise RuntimeError("immutable_video_shadow_record_changed")
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(current,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"date":args.date,"summary":current["summary"]},ensure_ascii=False))


if __name__=="__main__":main()
