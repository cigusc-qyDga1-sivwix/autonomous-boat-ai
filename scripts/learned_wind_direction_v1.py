"""Forward-only, capped wind-direction overlay on an existing learned 120-way forecast.

The existing SHA-verified model has already learned wind speed and wave by
course from prior races. The directional contrast itself is a bounded,
UNTRAINED rule requested for forward testing, never a learned coefficient.
No result, payout, odds, retrospective weather or post-cutoff replay is used.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from itertools import permutations
from math import exp, isfinite
from boat_ai.statistical import digest

VERSION = "learned-relative-wind-formal-v0.1-forward-uncalibrated"
SOURCE_CODES = "https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/codes.md"
POLICY = {
    "version": VERSION, "source": "precutoff_boatrace_preview",
    "direction_codes": {"tailwind": [3,4,5,6,7], "headwind": [11,12,13,14,15]},
    "min_wind_mps": 2.0, "min_cutoff_lead_minutes": 5,
    "log_shift_at_2m": .06, "log_shift_per_additional_mps": .025,
    "max_abs_log_shift": .17,
    "model_requirement": "fresh_sha_verified_previously_trained_learned_model",
    "coefficient_status": "direction_untrained_hypothesis_not_calibrated",
}
POLICY_SHA256 = digest(POLICY)
ALL_TRIPLES = {"-".join(map(str,p)) for p in permutations(range(1,7),3)}


def _num(x, lower, upper):
    if type(x) not in (int,float) or not isfinite(x) or not lower <= x <= upper:
        return None
    return float(x)


def _inputs(racers):
    if not isinstance(racers,list) or len(racers)!=6:
        raise ValueError("six entrants required")
    by_lane, seen_courses = {}, set()
    for row in racers:
        if not isinstance(row,dict):
            raise ValueError("invalid entrant")
        lane,course=row.get("lane"),row.get("course")
        if (type(lane) is not int or type(course) is not int or lane not in range(1,7)
                or course not in range(1,7) or lane in by_lane or course in seen_courses):
            raise ValueError("unique actual entry courses required")
        by_lane[lane]={"course":course,"exhibition_st":_num(row.get("exhibition_st"),-.5,1)}
        seen_courses.add(course)
    if set(by_lane)!=set(range(1,7)) or seen_courses!=set(range(1,7)):
        raise ValueError("incomplete actual course entries")
    return by_lane


def _ranking(rows):
    if not isinstance(rows,list) or len(rows)!=120:
        raise ValueError("learned canonical 120 outcomes required")
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row).difference({"combination","score"}):
            raise ValueError("unexpected score data; no postrace fields permitted")
        combo=row.get("combination")
        score=_num(row.get("score"),1e-14,1)
        if combo not in ALL_TRIPLES or combo in seen or score is None:
            raise ValueError("duplicate, missing or invalid learned score")
        seen.add(combo)
    if len(seen)!=120 or abs(sum(row["score"] for row in rows)-1)>1e-5:
        raise ValueError("learned scores must be normalized")
    return rows


def _clock(raw):
    if not isinstance(raw,str):
        raise ValueError("invalid timestamp")
    stamp=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("naive timestamp")
    return stamp


def _gate(snapshot):
    if snapshot.get("phase")!="exhibition":
        return None,"NO_EXHIBITION"
    frozen,cutoff=_clock(snapshot["frozen_at_utc"]),_clock(snapshot["cutoff_iso_jst"])
    if frozen >= cutoff-timedelta(minutes=POLICY["min_cutoff_lead_minutes"]):
        return None,"TOO_LATE_FOR_WIND"
    origin=snapshot.get("exhibition_origin") or {}
    if (origin.get("source")!="BoatraceOpenAPI" or
            origin.get("captured_before_cutoff") is not True or
            _clock(origin.get("captured_at_utc",""))>frozen):
        return None,"EXHIBITION_SOURCE_UNVERIFIED"
    weather=snapshot.get("weather_used") or {}
    if (weather.get("site_observed") is not True or
            weather.get("wind_source")!="boatrace_preview" or
            weather.get("source")!="boatrace_preview"):
        return None,"NO_ONSITE_PREVIEW_WIND"
    speed=_num(weather.get("wind_speed"),0,65)
    code=_num(weather.get("wind_direction_number"),1,17)
    if speed is None or speed<POLICY["min_wind_mps"] or code is None or not code.is_integer():
        return None,"WIND_SPEED_OR_CODE_UNAVAILABLE"
    code=int(code)
    if code in POLICY["direction_codes"]["tailwind"]:
        direction="tailwind"
    elif code in POLICY["direction_codes"]["headwind"]:
        direction="headwind"
    else:
        return None,"CROSSWIND_OR_CALM_NOT_WEIGHTED"
    return {"direction":direction,"wind_direction_number":code,"wind_speed_mps":speed,
            "source":weather["wind_source"]},"READY"


def rescore(ranked, snapshot):
    """Return a normalized 120-row ranking and auditable pre-cutoff policy."""
    control=_ranking(ranked)
    signal,why=_gate(snapshot)
    audit={"version":VERSION,"policy_sha256":POLICY_SHA256,
           "status": "APPLIED_FORWARD_UNCALIBRATED" if signal else why,
           "formal_component":bool(signal),"result_data_used":False,
           "odds_used":False,"calibrated":False,
           "direction_effect_trained":False,
           "trained_base_model_is_preserved":True,
           "source_observation_time_verified":False,
           "source_caveat":"OpenAPI preview source acquisition precedes cutoff; upstream observation time is not supplied.",
           "wind_codes_reference":SOURCE_CODES}
    if signal is None:
        return [dict(x) for x in control],audit
    by_lane=_inputs(snapshot.get("racers"))
    amount=min(POLICY["max_abs_log_shift"],
               POLICY["log_shift_at_2m"]+(signal["wind_speed_mps"]-2)*POLICY["log_shift_per_additional_mps"])
    raw=[]
    for entry in control:
        first,second,third=(int(x) for x in entry["combination"].split("-"))
        a,b,c=(by_lane[lane]["course"] for lane in (first,second,third))
        st=by_lane[first]["exhibition_st"]
        # A negative exhibition ST is an exhibition F, never faster-start credit.
        readiness=.72 if st is None or st<0 or st>.5 else max(.75,min(1.10,1+.70*(.16-st)))
        if signal["direction"]=="tailwind":
            direction_path=(.82 if a==2 else 0.0)+(.49 if a==1 and b==2 else 0.0)
            direction_path+=(.20 if a==2 and b==1 else 0.0)-(.22 if a>=4 else 0.0)
        else:
            direction_path=(.82 if a in (3,4) else 0.0)-(.72 if a==1 else 0.0)
            direction_path+=(.23 if a==4 and b in (5,6) else 0.0)
            direction_path+=(.12 if a==4 and c in (5,6) else 0.0)
        log_delta=max(-amount,min(amount,amount*direction_path*readiness))
        raw.append(float(entry["score"])*exp(log_delta))
    total=sum(raw)
    changed=[{"combination":row["combination"],"score":score/total}
             for row,score in zip(control,raw)]
    changed.sort(key=lambda row:(-row["score"],row["combination"]))
    audit.update({
        "signal":signal,"max_abs_log_shift":round(amount,6),
        "before_ranked_sha256":digest(control),
        "after_ranked_sha256":digest(changed),
        "before_head_shares":{str(i):round(sum(x["score"] for x in control
                          if x["combination"].startswith(str(i)+"-")),6) for i in range(1,7)},
        "after_head_shares":{str(i):round(sum(x["score"] for x in changed
                          if x["combination"].startswith(str(i)+"-")),6) for i in range(1,7)},
    })
    return changed,audit
