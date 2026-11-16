"""Source-field audit must never promote late/partial previews into formal predictions."""
from copy import deepcopy
from datetime import datetime,timedelta
from scripts.preview_field_coverage import extract,merge,summarize,run,SCHEMA

NOW=datetime.fromisoformat("2026-11-16T09:40:00+09:00")
def racer(lane):
    return {"course_number":lane,"start_timing":0.14,"exhibition_time":6.8,
            "tilt_adjustment":0,"weight":52.4,"weight_adjustment":0,
            "parts":[],"propeller":None}

def payload(cutoff="2026-11-16 10:00:00",include_parts=True):
    a={str(i):racer(i) for i in range(1,7)}
    if not include_parts:
        for v in a.values(): v.pop("parts");v.pop("propeller")
    return {"programs":{"stadiums":{"16":{"races":{"1":{
        "closed_at":cutoff,"preview":{
          "racers":a,"wind_speed":5,"wind_direction_number":4,
          "wave_height":4,"weather_number":1,"water_temperature":19,
          "air_temperature":17},"result":{"technique_number":9}}},
         "3":{"races":{"1":{"closed_at":cutoff,"preview":{"racers":a}}}}}}}}

def test_clean_source_collects_six_boat_data_only_before_cutoff():
    data=payload()
    original=deepcopy(data)
    records,diag=extract(data,NOW)
    assert "16-1" in records
    one=records["16-1"]
    assert one["six_boat_exhibition_complete"]
    assert one["field_counts"]["weight"]==6
    assert one["field_counts"]["weight_adjustment"]==6
    assert one["field_counts"]["parts"]==6
    assert one["field_counts"]["propeller"]==6
    assert one["weather"]["water_temperature"]==19
    assert "result" not in str(one)
    assert one["original_observation_time_verified"] is False
    assert "3-1" not in records
    assert data==original
    close=datetime.fromisoformat("2026-11-16T09:59:00+09:00")
    late,_=extract(data,close)
    assert not late

def test_missing_exchange_fields_are_unknown_not_no_replacement():
    records,_=extract(payload(include_parts=False),NOW)
    first=records["16-1"]
    assert first["field_counts"]["parts"]==0
    assert first["field_counts"]["propeller"]==0
    assert all(first["racers"][str(i)]["parts"] is None for i in range(1,7))

def test_incomplete_course_cannot_be_formal_ready():
    d=payload()
    d["programs"]["stadiums"]["16"]["races"]["1"]["preview"]["racers"]["6"]["course_number"]=5
    r,_=extract(d,NOW)
    assert not r["16-1"]["six_boat_exhibition_complete"]

def test_merge_preserves_first_precutoff_capture_with_latest_version():
    r,_=extract(payload(),NOW)
    first=merge({},r,"2026-11-16")
    after=NOW+timedelta(minutes=1)
    next_doc=payload()
    next_doc["programs"]["stadiums"]["16"]["races"]["1"]["preview"]["racers"]["1"]["tilt_adjustment"]=0.5
    new,_=extract(next_doc,after)
    combined=merge({"schema":SCHEMA,"event_date":"2026-11-16","records":first},new,"2026-11-16")
    assert combined["16-1"]["first"]["racers"]["1"]["tilt_adjustment"]==0
    assert combined["16-1"]["latest"]["racers"]["1"]["tilt_adjustment"]==0.5
    assert combined["16-1"]["revisions"]==1
    doc=summarize(combined,"2026-11-16",after,"test","ok",{})
    assert doc["totals"]["six_of_six"]["tilt_adjustment"]==1
    assert doc["by_venue"]["児島"]["races"]==1

def test_network_failure_retains_last_good_snapshot(tmp_path):
    good=lambda url:payload()
    d=run(tmp_path,now=NOW,fetcher=good)
    assert d["totals"]["races"]==1
    def bad(url):raise OSError("offline")
    d=run(tmp_path,now=NOW+timedelta(minutes=1),fetcher=bad)
    assert d["fetch_status"]=="unavailable"
    assert d["totals"]["races"]==1
    assert d["formal_forecasts_modified"] is False
