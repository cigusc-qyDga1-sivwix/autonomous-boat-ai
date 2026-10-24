"""Post-promotion invariant: canonical = JS v0.7; legacy = same-time shadow.
Previous snapshots are immutable. Official pay only scores current frozen primary.
"""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from scripts import autonomous_daily as ai

JST=ZoneInfo("Asia/Tokyo")
EARLY=datetime(2026,10,24,16,20,tzinfo=JST)
LATER=datetime(2026,10,24,17,5,tzinfo=JST)

def row(clock="2026-10-24 17:30:00", second=False):
    racers={str(i):{"name":f"Racer {i}","national_win_rate":5.0,
                    "average_start_timing":.18,"motor_top_2_percent":30}
            for i in range(1,7)}
    racers["4"].update(national_win_rate=8.7,average_start_timing=.08,motor_top_2_percent=68)
    racers["5"].update(national_win_rate=7.1,average_start_timing=.11,motor_top_2_percent=55)
    racers["3"].update(average_start_timing=.23)
    d={"closed_at":clock,"racers":racers}
    if second:
        d["preview"]={"wind_speed":2,"wave_height":0,"racers":{
            str(i):{"course_number":i,"start_timing":.08 if i==4 else .20,
                    "exhibition_time":6.55 if i==4 else 6.86}
            for i in range(1,7)
        }}
    return d

def feed(*items):
    return {"programs":{"stadiums":{"15":{"races":{str(i):r for i,r in items}}}}}

def test_canonical_new_main_and_same_time_legacy_shadow():
    source=feed((1,row()))
    first,view,status=ai.build(None,source,EARLY,"fixture")
    assert status["new_baseline"]==1
    snap=first["race_records"]["15-1"]["versions"][0]
    assert snap["model_version"]==ai.MAIN_MODEL
    assert snap["model_role"]=="main"
    assert snap["legacy_control"]["model_role"]=="shadow_validation"
    assert snap["legacy_control"]["model_version"].startswith("heuristic-")
    assert snap["legacy_control"]["frozen_at_utc"]==snap["frozen_at_utc"]
    assert snap["legacy_control"]["sha256"]
    assert snap["sha256"]==ai.stable_hash({k:v for k,v in snap.items() if k!="sha256"})
    assert snap["bets"]!=[] and snap["legacy_control"]["bets"]!=[]
    assert snap["start_v07"]["slit_signals"]
    assert 4<=len(snap["bets"])<=12
    assert sum(b["virtual_yen"] for b in snap["bets"])==50000
    assert sum(b["virtual_yen"] for b in snap["legacy_control"]["bets"])==50000
    assert view["forecast_races"][0]["model_role"]=="main"
    assert view["forecast_races"][0]["legacy_control"]["bets"]==snap["legacy_control"]["bets"]
    before=deepcopy(snap)
    again,_,s2=ai.build(first,source,datetime(2026,10,24,16,29,tzinfo=JST),"fixture")
    assert s2["new_baseline"]==0
    assert again["race_records"]["15-1"]["versions"][0]==before

def test_old_frozen_races_are_never_migrated_or_rewritten():
    new,_,_=ai.build(None,feed((1,row()),(2,row())),EARLY,"fixture")
    old=deepcopy(new["race_records"]["15-1"]["versions"][0])
    old["model_version"]="heuristic-0.7-venue-priors-test-untrained"
    old["bets"]=deepcopy(old["legacy_control"]["bets"])
    for extra in ("legacy_control","start_v07","coupled_v06","model_role","head_course_shares","role_coverage","role_changes"):
        old.pop(extra,None)
    old["sha256"]=ai.stable_hash({k:v for k,v in old.items() if k!="sha256"})
    new["race_records"]["15-1"]["versions"]=[old]
    later=feed((1,row()),(2,row()),(3,row("2026-10-24 18:30:00")))
    updated,view,s=ai.build(new,later,datetime(2026,10,24,16,30,tzinfo=JST),"fixture")
    assert updated["race_records"]["15-1"]["versions"]==[old]
    assert updated["race_records"]["15-3"]["versions"][0]["model_version"]==ai.MAIN_MODEL
    assert s["new_baseline"]==1
    assert next(r for r in view["forecast_races"] if r["race"]==1)["model_version"].startswith("heuristic-")

def test_official_result_scores_main_and_shadow_separately():
    src=feed((1,row()))
    ledger,view,_=ai.build(None,src,EARLY,"fixture")
    frozen=deepcopy(ledger["race_records"]["15-1"]["versions"][0])
    top=frozen["bets"][0]["combination"]
    official={"date":"2026-10-24","results":{"15-1":{"finish":top,"payout_per_100":1500}},
              "reviews":{},"cancellations":{},
              "source_url":"https://www.boatrace.jp/owpc/pc/race/pay?hd=20261024",
              "retrieved_at_utc":"2026-10-24T09:00:00Z"}
    done=ai.integrate_official(ledger,view,official,datetime(2026,10,24,18,0,tzinfo=JST))
    key="2026-10-24|丸亀|1"
    result=done["official_results"][key]
    assert result["hit"] is True
    assert result["snapshot_sha256"]==frozen["sha256"]
    assert result["legacy_comparison"]["source"]=="same_pre_cutoff_shadow_only"
    assert result["legacy_comparison"]["legacy_sha256"]==frozen["legacy_control"]["sha256"]
    assert done["main_vs_legacy"]["verified_comparisons"]==1
    assert done["main_vs_legacy"]["main_hits"]==1
    assert done["main_vs_legacy"]["virtual_stake_per_model"]==50000
    assert done["weather_backtest"]["races"]==0
    assert ledger["race_records"]["15-1"]["versions"][0]==frozen
    assert result["virtual_payout"]==frozen["bets"][0]["virtual_yen"]*15

def test_no_silent_fallback_to_old_model(monkeypatch):
    def unavailable(*args,**kwargs):
        raise FileNotFoundError("Node is not available")
    monkeypatch.setattr(ai.subprocess,"run",unavailable)
    with pytest.raises(RuntimeError,match="fail closed"):
        ai.prediction(row(),"丸亀",1,"baseline",EARLY,"fixture")

def test_no_post_cutoff_primary_or_shadow_backfill():
    late=datetime(2026,10,24,17,45,tzinfo=JST)
    ledger,view,status=ai.build(None,feed((1,row())),late,"fixture")
    assert status["forecast_races"]==0
    assert ledger["race_records"]["15-1"]["versions"]==[]
    assert view["official_results"]=={}
