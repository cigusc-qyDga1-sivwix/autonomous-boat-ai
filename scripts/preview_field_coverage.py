"""Pre-cutoff OpenAPI preview completeness audit (not a prediction pipeline).

The merged Boatrace Open API payload includes result fields from later times.
Read ONLY race.preview and discard every race past a strict cutoff margin.
Missing propeller/parts keys are NOT synonymous with 'no replacement'.
No prior immutable predictions, official pay, or model weights are touched.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")
SOURCE = "https://boatraceopenapi.github.io/api/v1"
SCHEMA = "boatlabs.openapi-preview-field-coverage.v1"
MARGIN = timedelta(minutes=2)
FIELDS = ("course_number","start_timing","exhibition_time","tilt_adjustment",
          "weight","weight_adjustment","parts","propeller")
WEATHER = ("weather_number","wind_direction_number","wind_speed","wave_height",
           "air_temperature","water_temperature")
RESEARCH_ONLY = True
VENUES = {
    "1":"桐生","2":"戸田","3":"江戸川","4":"平和島","5":"多摩川",
    "6":"浜名湖","7":"蒲郡","8":"常滑","9":"津","10":"三国",
    "11":"びわこ","12":"住之江","13":"尼崎","14":"鳴門","15":"丸亀",
    "16":"児島","17":"宮島","18":"徳山","19":"下関","20":"若松",
    "21":"芦屋","22":"福岡","23":"唐津","24":"大村",
}


def _numeric(value, low, high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        return None
    return value if low <= value <= high else None


def _field(name, value):
    if name == "course_number":
        num=_numeric(value,1,6)
        return int(num) if num is not None and num==int(num) else None
    if name == "start_timing":
        return _numeric(value,-0.5,1)
    if name == "exhibition_time":
        return _numeric(value,5,10)
    if name == "tilt_adjustment":
        return _numeric(value,-2,3)
    if name == "weight":
        return _numeric(value,35,110)
    if name == "weight_adjustment":
        return _numeric(value,0,15)
    if name == "parts":
        if not isinstance(value,list):
            return None
        if not all(isinstance(v,dict) and type(v.get("number")) is int and 0<=v["number"]<=99
                   and (v.get("quantity") is None or type(v["quantity"]) is int and 0<=v["quantity"]<=99)
                   for v in value):
            return None
        return [{"number":v["number"],"quantity":v.get("quantity")} for v in value]
    if name == "propeller":
        return value if value in (None,"新") else None
    return None


def _cutoff(race):
    raw = race.get("closed_at")
    if not isinstance(raw,str):
        return None
    try:
        return datetime.strptime(raw,"%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
    except ValueError:
        return None


def _valid_weather(preview):
    out={}
    for name in WEATHER:
        raw=preview.get(name)
        if name in ("weather_number","wind_direction_number"):
            num=_numeric(raw,0,100)
            out[name]=int(num) if num is not None and int(num)==num else None
        elif name=="wind_speed":
            out[name]=_numeric(raw,0,65)
        elif name=="wave_height":
            out[name]=_numeric(raw,0,150)
        else:
            out[name]=_numeric(raw,-20,60) if name=="air_temperature" else _numeric(raw,-5,45)
    return out


def extract(document,at):
    if at.tzinfo is None:
        raise ValueError("Pre-cutoff audit requires aware clock")
    if not isinstance(document,dict):
        return {},{"status":"invalid_document"}
    day=at.astimezone(JST).date()
    stadiums=(document.get("programs") or {}).get("stadiums")
    if not isinstance(stadiums,dict):
        return {},{"status":"invalid_stadiums"}
    captured=at.astimezone(UTC).isoformat()
    records={}
    diagnostics=Counter()
    for code,stadium in stadiums.items():
        if code not in VENUES or code=="3" or not isinstance(stadium,dict):
            continue
        races=stadium.get("races")
        if not isinstance(races,dict):
            continue
        for key,race in races.items():
            if not isinstance(key,str) or not key.isdigit() or not 1<=int(key)<=12 or not isinstance(race,dict):
                continue
            cutoff=_cutoff(race)
            if not cutoff or cutoff.date()!=day:
                continue
            if at>=cutoff-MARGIN:
                diagnostics["no_longer_pre_cutoff"]+=1
                continue
            preview=race.get("preview")
            if not isinstance(preview,dict):
                diagnostics["preview_missing"]+=1
                continue
            racers=preview.get("racers")
            if not isinstance(racers,dict):
                diagnostics["racers_missing"]+=1
                continue
            six={}
            field_counts={name:0 for name in FIELDS}
            replacement_events=0
            for lane in range(1,7):
                raw=racers.get(str(lane))
                raw=raw if isinstance(raw,dict) else {}
                clean={}
                for field in FIELDS:
                    # A missing key is unknown, not proof of zero replacement.
                    if field not in raw:
                        clean[field]=None
                        continue
                    value=_field(field,raw[field])
                    clean[field]=value
                    if field=="propeller" and raw[field] is None:
                        field_counts[field]+=1
                    elif value is not None:
                        field_counts[field]+=1
                    if field=="parts" and value:
                        replacement_events+=1
                six[str(lane)]=clean
            w=_valid_weather(preview)
            full=six and all(field_counts[x]==6 for x in ("course_number","start_timing","exhibition_time"))
            courses=[six[str(i)]["course_number"] for i in range(1,7)]
            full=bool(full and set(courses)==set(range(1,7)))
            v={
                "venue":VENUES[code],"venue_code":int(code),"race":int(key),
                "cutoff_jst":cutoff.isoformat(),"captured_at_utc":captured,
                "original_observation_time_verified":False,
                "api_url":f"{SOURCE}/{day:%Y}/{day:%Y%m%d}.json",
                "racers":six,"weather":w,"field_counts":field_counts,
                "six_boat_exhibition_complete":full,
                "parts_replacement_boats":replacement_events,
                "formal_forecast_input":False,"research_only":True,
            }
            v["sha256"]=hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
            records[f"{code}-{int(key)}"]=v
    return records,dict(diagnostics)


def merge(prior,current,day):
    if not isinstance(prior,dict) or prior.get("schema")!=SCHEMA or prior.get("event_date")!=day:
        prior={}
    records=dict(prior.get("records") or {})
    for key,row in current.items():
        entry=records.get(key)
        if entry is None:
            records[key]={"first":row,"latest":row,"revisions":0}
        elif row["captured_at_utc"]>entry["latest"]["captured_at_utc"]:
            if row["field_counts"]!=entry["latest"]["field_counts"] or row["weather"]!=entry["latest"]["weather"] or row["racers"]!=entry["latest"]["racers"]:
                entry["revisions"]+=1
            entry["latest"]=row
    return records


def summarize(records,day,now,source_url,source_status,diagnostics):
    per={}
    for v in VENUES.values():
        if v!="江戸川":
            per[v]={"races":0,"six_boat_ready":0,"six_of_six":{x:0 for x in FIELDS},
                    "weather_present":{x:0 for x in WEATHER},"parts_exchange_boats":0}
    for entry in records.values():
        row=entry["latest"]
        v=per[row["venue"]]
        v["races"]+=1
        v["six_boat_ready"]+=int(row["six_boat_exhibition_complete"])
        for key,num in row["field_counts"].items():
            v["six_of_six"][key]+=int(num==6)
        for key,value in row["weather"].items():
            v["weather_present"][key]+=int(value is not None)
        v["parts_exchange_boats"]+=row["parts_replacement_boats"]
    totals={
        "races":sum(x["races"] for x in per.values()),
        "six_boat_ready":sum(x["six_boat_ready"] for x in per.values()),
        "six_of_six":{name:sum(x["six_of_six"][name] for x in per.values()) for name in FIELDS},
        "weather_present":{name:sum(x["weather_present"][name] for x in per.values()) for name in WEATHER},
        "parts_exchange_boats":sum(x["parts_exchange_boats"] for x in per.values()),
    }
    return {
        "schema":SCHEMA,"event_date":day,"checked_at_utc":now.astimezone(UTC).isoformat(),
        "source_url":source_url,"fetch_status":source_status,
        "records":records,"totals":totals,"by_venue":per,
        "this_run_diagnostics":diagnostics,
        "source_role":"nonofficial_pre_cutoff_OpenAPI_json_not_site_sensor",
        "raw_wind_direction_not_relative":True,
        "original_source_observation_timestamp_verified":False,
        "no_results_used":True,"research_only":True,"formal_forecasts_modified":False,
        "warning":"Source is a periodic snapshot. Missing replacement keys are not proof of no exchange; results are never read.",
    }


def run(directory=Path("app/data/exhibition-preview-evidence"),now=None,fetcher=None):
    now=now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Aware clock required")
    day=now.astimezone(JST).date()
    url=f"{SOURCE}/{day:%Y}/{day:%Y%m%d}.json"
    status="ok"
    if fetcher is None:
        def fetcher(url):
            request=Request(url,headers={"User-Agent":"BOAT-LAB-field-coverage-research/1.0"})
            with urlopen(request,timeout=15) as response:
                body=response.read(10_000_001)
                if len(body)>10_000_000:
                    raise ValueError("Source payload too large")
                return json.loads(body)
    try:
        payload=fetcher(url)
        checked=datetime.now(UTC) if fetcher.__name__=="fetcher" else now
        if checked.astimezone(JST).date()!=day:
            raise ValueError("Day changed during fetch")
        current,diagnostics=extract(payload,checked)
    except (OSError,HTTPError,URLError,TimeoutError,ValueError,TypeError) as exc:
        checked=datetime.now(UTC) if fetcher.__name__=="fetcher" else now
        current,diagnostics={},{"fetch_error":type(exc).__name__}
        status="unavailable"
    target=directory/f"{day.isoformat()}.json"
    try:
        existing=json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except (OSError,ValueError):
        existing={}
    records=merge(existing,current,day.isoformat())
    report=summarize(records,day.isoformat(),checked,url,status,diagnostics)
    directory.mkdir(parents=True,exist_ok=True)
    for output in (target,directory/"latest.json"):
        temp=output.with_name(output.name+".tmp")
        temp.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
        temp.replace(output)
    return report


def main():
    document=run()
    print(json.dumps({"date":document["event_date"],"source":document["fetch_status"],
                      "races":document["totals"]["races"],
                      "six_boat_ready":document["totals"]["six_boat_ready"],
                      "six_boat_tilt":document["totals"]["six_of_six"]["tilt_adjustment"],
                      "six_boat_weight":document["totals"]["six_of_six"]["weight"],
                      "six_boat_parts":document["totals"]["six_of_six"]["parts"]},ensure_ascii=False))


if __name__=="__main__":
    main()
