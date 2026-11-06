"""Independent JMA astronomical tide *prediction* collector.

Tide-height forecast at JMA reference stations, NEVER water current/flow.
No station is silently mapped to a BOATRACE venue; local hydraulics matter.
Source text specification: 1-72 (24 x 3 chars) hourly height, 73-78 date,
79-80 station code, 81-108 high tides, 109-136 low tides. JST, cm.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime, date, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
SCHEMA = "weather_lab.jma_tide_reference.v1"
# Verified against JMA public 2026 text data. These are REFERENCE stations,
# not on-course gauging points, and have no automatic venue effect.
STATIONS = {"TK":"東京", "OS":"大阪", "ST":"洲本"}
BASE = "https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt"
FORMAT_URL = "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/readme.html"
JCG_CURRENTS = "https://portal.msil.go.jp/msil-api-list"


def _height(field: str):
    if not isinstance(field,str) or len(field)!=3:
        return None
    try:
        n=int(field)
    except ValueError:
        return None
    return n if -200<=n<=900 and n!=999 else None


def _events(area: str):
    events=[]
    for j in range(0,28,7):
        text=area[j:j+7]
        if len(text)!=7:
            raise ValueError("Malformed tide event fields")
        hhmm=text[:4].strip()
        cm=_height(text[4:7])
        if hhmm=="9999":
            continue
        if not re.fullmatch(r"[0-2]\d[0-5]\d",hhmm) or int(hhmm[:2])>23 or cm is None:
            raise ValueError("Malformed tidal event time/height")
        events.append({"time_jst":hhmm[:2]+":"+hhmm[2:], "height_cm_datum":cm})
    return events


def parse(text: str, station: str, day: date) -> dict | None:
    if station not in STATIONS:
        raise ValueError("Unverified tide station")
    if not isinstance(text,str):
        raise ValueError("No tide text")
    found=[]
    for raw in text.splitlines():
        if len(raw)<136:
            continue
        if raw[78:80]!=station:
            continue
        try:
            yy=int(raw[72:74]);mm=int(raw[74:76]);dd=int(raw[76:78])
        except ValueError:
            continue
        if (yy,mm,dd)!=(day.year%100,day.month,day.day):
            continue
        if len(raw)!=136:
            raise ValueError("Unexpected JMA text row length")
        hourly=[_height(raw[i:i+3]) for i in range(0,72,3)]
        if len(hourly)!=24:
            raise ValueError("Missing hourly tide columns")
        highs=_events(raw[80:108])
        lows=_events(raw[108:136])
        found.append({"date_jst":day.isoformat(), "station_code":station,
                      "station_name":STATIONS[station], "hourly_height_cm_datum":hourly,
                      "high_tides":highs, "low_tides":lows,
                      "datum":"JMA station-specific tide-table datum (not common sea-level reference)",
                      "data_kind":"astronomical_tide_prediction_not_measured",
                      "on_course_station":False,
                      "current_flow_observed":False,
                      "current_velocity_mps":None,"current_direction":None,
                      "venue_effect_applied":False})
    if len(found)>1:
        raise ValueError("Duplicate station day in JMA tide text")
    return found[0] if found else None


def fetch(now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("Need timezone-aware collection clock")
    day=now.astimezone(JST).date()
    stations=[]
    failed={}
    for code in STATIONS:
        url=f"{BASE}/{day.year}/{code}.txt"
        req=Request(url,headers={"User-Agent":"WEATHER-LAB-tide-research/0.1","Accept":"text/plain"})
        try:
            with urlopen(req,timeout=12) as response:
                if response.status!=200:
                    raise ValueError("Non-200 JMA response")
                raw=response.read(120_001)
            if len(raw)>120_000:
                raise ValueError("JMA text is unexpectedly large")
            record=parse(raw.decode("utf-8-sig"),code,day)
            if record is None:
                failed[code]="date_missing"
            else:
                record["source_url"]=url
                stations.append(record)
        except (HTTPError,URLError,TimeoutError,OSError,ValueError,UnicodeError) as exc:
            failed[code]=type(exc).__name__
    return {"schema":SCHEMA,"event_date":day.isoformat(),
      "collected_at_utc":now.astimezone(timezone.utc).isoformat(),
      "provider":{"name":"JMA astronomical tide table","url":FORMAT_URL,
         "source_kind":"predicted_tide_not_measured_or_current",
         "fetch_status":"ok" if stations else "unavailable"},
      "stations":stations,"missing_station_codes":failed,
      "venue_mapping":{"status":"unverified", "automatically_mapped":False,
                       "site_tidal_correction_applied":False},
      "current_source":{"name":"Japan Coast Guard MSIL tidal-current predictions",
                        "url":JCG_CURRENTS,
                        "status":"not_connected_subscription_key_and_site_mapping_required",
                        "current_speed":None,"current_direction":None},
      "formal_forecasts_unchanged":True}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args(argv)
    doc=fetch(datetime.now(timezone.utc))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"source":"JMA","date":doc["event_date"],
      "station_count":len(doc["stations"]),"status":doc["provider"]["fetch_status"],
      "current_flow_collected":False,"formal_forecasts_unchanged":True}))
    if not doc["stations"]:
        raise SystemExit(2)


if __name__=="__main__":
    main()
