"""Conservative, explicit venue model coverage; no hindsight or inferred tide."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest

from scripts.venue_profiles import VENUE_PROFILES, get_profile, adjust_weights
from scripts.autonomous_daily import build, VENUES

JST=ZoneInfo("Asia/Tokyo")

def runners():
    return {str(i):{"name":"選手"+str(i),"national_win_rate":5,
                     "average_start_timing":.15,"motor_top_2_percent":34} for i in range(1,7)}

def test_24_venues_unique_and_consistent_with_forecast_codes():
    assert len(VENUE_PROFILES)==len(VENUES)==24
    assert {str(int(k)) for k in VENUE_PROFILES}==set(VENUES)
    assert {v["name"] for v in VENUE_PROFILES.values()}==set(VENUES.values())
    for i in range(1,25):
        p=get_profile(str(i))
        assert 0.30<p["course1_reference_rate"]<.70
        assert p["wind_exposure"] in {"低","中","高"}
        assert p["water_type"] in {"淡水","海水","汽水"}
        assert p["tactical_focus"] and p["layout_focus"]

def test_only_actual_entry_course_1_prior_is_adjusted():
    w=[1.0]*6
    d=[{"lane":i,"course":i} for i in range(1,7)]
    # Todа's weaker inside versus Tokuyama's stronger inside.
    low,ld=adjust_weights(w,d,"02")
    high,hd=adjust_weights(w,d,"18")
    assert low[0]<w[0]<high[0]
    assert all(x==1 for x in low[1:]+high[1:])
    assert .90<=ld["course1_relative_multiplier"]<=1.1
    assert .90<=hd["course1_relative_multiplier"]<=1.1
    # Row changes the *actual course* rather than changing the frame label.
    swapped=[{"lane":i,"course":2 if i==1 else 1 if i==2 else i} for i in range(1,7)]
    y,meta=adjust_weights(w,swapped,"18")
    assert y[0]==1
    assert y[1]>1
    assert meta["course1_lane"]==2
    assert w==[1.0]*6

def test_missing_duplicate_course_cannot_invent_winner():
    d=[{"lane":i,"course":i} for i in range(1,7)]
    d[2]["course"]=2
    out,meta=adjust_weights([1.0]*6,d,"23")
    assert out==[1.0]*6
    assert not meta["applied"]

def test_weather_flags_only_with_observations():
    w=[1.0]*6
    d=[{"lane":i,"course":i} for i in range(1,7)]
    for venue in ("03","14","23"):
        _,meta=adjust_weights(w,d,venue)
        assert meta["wind_risk"] is None
    _,meta=adjust_weights(w,d,"03",{"wind_speed":6})
    assert meta["wind_risk"]
    assert "未取得" in meta["tide_data_status"]
    _,meta=adjust_weights(w,d,"23",{"wind_speed":6})
    assert meta["wind_risk"] is None # medium wind exposure, not forced high risk
    assert get_profile("23")["pit_layout_changed"]=="2025-12"

def test_frozen_pre_cutoff_forecast_includes_correct_venue_metadata():
    races={code:{"races":{"1":{"closed_at":"2026-10-23 13:00:00",
                                "racers":runners()}}} for code in VENUES}
    src={"programs":{"stadiums":races}}
    now=datetime(2026,10,23,10,20,tzinfo=JST)
    ledger,app,status=build(None,src,now,"fixture")
    assert status["new_baseline"]==24
    assert len(app["forecast_races"])==24
    for item in app["forecast_races"]:
        assert item["venue_profile"]["name"]==item["venue"]
        assert item["venue_adjustment"]["reference_type"]=="uncalibrated_weak_prior_third_party"
        assert 4<=len(item["bets"])<=12
        assert sum(b["virtual_yen"] for b in item["bets"])==50000
        assert datetime.fromisoformat(item["frozen_at_utc"]).astimezone(JST).strftime("%H:%M") < item["cutoff_jst"]
    # Same-day reruns must preserve previous freeze even if weather changes.
    original={k:list(v["versions"]) for k,v in ledger["race_records"].items()}
    ledger2,_,status2=build(ledger,src,datetime(2026,10,23,11,0,tzinfo=JST),"fixture")
    assert status2["new_baseline"]==0
    assert all(ledger2["race_records"][k]["versions"]==v for k,v in original.items())

def test_published_manifest_matches_canonical_profiles():
    doc=json.loads(Path("app/data/venue-profiles.json").read_text(encoding="utf-8"))
    assert doc["schema"]=="boatlabs.venue_profiles.v1"
    assert len(doc["profiles"])==24
    assert doc["profiles"]==[get_profile(str(i)) for i in range(1,25)]
