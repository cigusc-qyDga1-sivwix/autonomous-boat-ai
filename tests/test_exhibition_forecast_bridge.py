"""End-to-end pre-cutoff exhibitions change (or explicitly preserve) predictions."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.exhibition_bridge import inject, available_rows
from scripts.autonomous_daily import build, preview_complete

JST = ZoneInfo("Asia/Tokyo")

def race():
    return {"closed_at":"2026-10-23 11:20:00",
            "racers":{str(i):{"name":f"選手{i}","national_win_rate":5.2,
                              "motor_top_2_percent":33,"average_start_timing":.16}
                       for i in range(1,7)}}

def source():
    return {"programs":{"stadiums":{"18":{"races":{"3":race()}}}}}

def row():
    return {
        "race_code":"202610231803","venue_code":"18","venue":"徳山","race":3,
        "source_status":"historical_research_only_not_frozen_forecast",
        "source_observed_jst":"2026-10-23T11:09:00+09:00",
        "boats":[{
            "lane":i,"course":i,"exhibition_st":.08 if i==3 else .20,
            "exhibition_time":6.6 if i==3 else 6.9,
            "tilt":0,"original_exhibition":[
                {"metric":"一周","value":30 if i==3 else 50},
                {"metric":"まわり足","value":4 if i==3 else 15},
                {"metric":"直線","value":5 if i==3 else 12},
            ]} for i in range(1,7)
        ],
        "weather":{"wind_mps":3,"wave_cm":2},
        # Deliberately wrong result: the forecast MUST never inspect it.
        "result":{"finish":"6-5-4"},"payout":{"finish":"6-5-4","yen_per_100":99900},
    }

def test_missing_csv_yields_only_baseline():
    now=datetime(2026,10,23,11,0,tzinfo=JST)
    _,ui,status=build(None,source(),now,"api",exhibition_rows={})
    assert status["new_baseline"]==1
    assert status["new_exhibition"]==0
    assert ui["forecast_races"][0]["phase"]=="baseline"

def test_six_boat_exhibition_creates_new_frozen_version_with_comparison():
    old,_,_=build(None,source(),datetime(2026,10,23,11,0,tzinfo=JST),"api")
    baseline=deepcopy(old["race_records"]["18-3"]["versions"][0])
    changed,ui,status=build(old,source(),datetime(2026,10,23,11,12,tzinfo=JST),
                            "api",exhibition_rows={row()["race_code"]:row()})
    assert status["new_exhibition"]==1
    assert changed["race_records"]["18-3"]["versions"][0]==baseline
    latest=changed["race_records"]["18-3"]["versions"][-1]
    assert latest["phase"]=="exhibition"
    assert latest["model_version"]=="tactical-outside-start-gap-v0.7-untrained"
    assert latest["model_role"]=="main"
    assert latest["legacy_control"]["model_version"]=="heuristic-0.6-csv-exhibition-test-untrained"
    assert latest["exhibition_origin"]["source"]=="BoatraceCSV"
    assert latest["racers"][2]["original_exhibition"]["lap_time"]==30
    assert latest["racers"][2]["exhibition_time"]==6.6
    assert latest["exhibition_change"]["previous_top"]==baseline["bets"][0]["combination"]
    assert latest["exhibition_change"]["new_top"]==latest["bets"][0]["combination"]
    assert latest["exhibition_change"]["bets_changed"]
    assert latest["start_v07"]["slit_signals"]
    assert latest["legacy_control"]["bets"] != baseline["legacy_control"]["bets"]
    assert latest["legacy_control"]["model_role"]=="shadow_validation"
    assert latest["sha256"]!=baseline["sha256"]
    assert sum(b["virtual_yen"] for b in latest["bets"])==50000
    assert 4<=len(latest["bets"])<=12
    assert ui["official_results"]=={}
    assert ui["forecast_races"][0]["exhibition_change"]==latest["exhibition_change"]

def test_no_late_data_can_rewrite_original_forecast():
    old,_,_=build(None,source(),datetime(2026,10,23,11,0,tzinfo=JST),"api")
    baseline=deepcopy(old["race_records"]["18-3"]["versions"][0])
    late=datetime(2026,10,23,11,25,tzinfo=JST)
    unusable, provenance=inject(race(),row(),late,"18",3)
    assert provenance is None
    assert not preview_complete(unusable)
    same,view,status=build(old,source(),late,"api",exhibition_rows={row()["race_code"]:row()})
    assert status["new_exhibition"]==0
    assert same["race_records"]["18-3"]["versions"]==[baseline]
    assert view["forecast_races"][0]["phase"]=="baseline"

def test_mismatch_or_future_timestamp_is_rejected():
    sample=row()
    wrong=deepcopy(sample);wrong["boats"][0]["course"]=2
    assert inject(race(),wrong,datetime(2026,10,23,11,12,tzinfo=JST),"18",3)[1] is None
    future=deepcopy(sample);future["source_observed_jst"]="2026-10-23T11:50:00+09:00"
    assert inject(race(),future,datetime(2026,10,23,11,12,tzinfo=JST),"18",3)[1] is None

def test_same_exhibition_is_not_repeated_and_source_revision_is_preserved():
    first,_,_=build(None,source(),datetime(2026,10,23,11,12,tzinfo=JST),"api",
                    exhibition_rows={row()["race_code"]:row()})
    version=deepcopy(first["race_records"]["18-3"]["versions"][-1])
    same,_,stats=build(first,source(),datetime(2026,10,23,11,13,tzinfo=JST),
                       "api",exhibition_rows={row()["race_code"]:row()})
    assert stats["new_exhibition"]==0
    assert same["race_records"]["18-3"]["versions"][-1]==version
