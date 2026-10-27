"""Forward-only venue v1.4: 23 venue gating, immutable forecasts, contemporaneous controls."""
import copy
from datetime import datetime
from scripts import autonomous_daily as A


def payload(code):
    race={
      "closed_at":"2026-10-27 21:00:00",
      "racers":{str(i):{
        "name":f"Racer {i}",
        "national_win_rate":[5.7,5.4,6.4,5.9,6.4,6.0][i-1],
        "average_start_timing":.09 if i==3 else .17,
        "motor_top_2_percent":51 if i==3 else 33
      } for i in range(1,7)},
      "preview":{"wind_speed":2,"wave_height":1,
        "racers":{str(i):{
          "course_number":i,"exhibition_time":6.83 if i==3 else 6.92,
          "start_timing":.08 if i==3 else .17,"tilt_adjustment":0
        } for i in range(1,7)}}
    }
    return {"programs":{"stadiums":{code:{"races":{"12":race}}}}}


def version(ledger,code):
    return ledger["race_records"][f"{code}-12"]["versions"]


def test_v14_preserves_existing_v13_sha_and_gets_same_time_controls():
    before_t=datetime.fromisoformat("2026-10-27T18:20:00+09:00")
    after_t=datetime.fromisoformat("2026-10-27T19:20:00+09:00")
    old,_,_=A.build(None,payload("02"),before_t,"fixture")
    versions=copy.deepcopy(version(old,"02"))
    assert versions[-1]["model_version"]==A.POSTRACE_CONDITIONAL_MODEL
    new,ui,status=A.build(old,payload("02"),after_t,"fixture")
    now_versions=version(new,"02")
    assert now_versions[:len(versions)]==versions
    v=now_versions[-1]
    assert v["model_version"]==A.VENUE_TACTICS_MODEL
    assert v["model_upgrade"]["previous_sha256"]==versions[-1]["sha256"]
    assert v["sha256"]!=versions[-1]["sha256"]
    assert v["venue_tactics_v2"]["pre_cutoff_only"] is True
    assert v["venue_tactics_v2"]["result_data_used"] is False
    assert v["venue_tactics_v2"]["eligible"] is True
    assert v["venue_tactics_ab"]["prior_model"]==A.POSTRACE_CONDITIONAL_MODEL
    assert v["venue_tactics_ab"]["generated_pre_cutoff"] is True
    assert v["venue_tactics_ab"]["frozen_at_utc"]==v["frozen_at_utc"]
    assert v["venue_tactics_ab"]["no_additional_stake"] is True
    assert 4<=len(v["bets"])<=12
    assert sum(x["virtual_yen"] for x in v["bets"])==50_000
    assert ui["forecast_races"][0]["venue_tactics_v2"]["eligible"] is True
    unchanged=copy.deepcopy(now_versions)
    same,_,_=A.build(new,payload("02"),after_t,"fixture")
    assert version(same,"02")==unchanged
    closed,_,_=A.build(new,payload("02"),datetime.fromisoformat("2026-10-27T21:01:00+09:00"),"fixture")
    assert version(closed,"02")==unchanged


def test_edogawa_remains_on_v13_while_others_upgrade():
    t=datetime.fromisoformat("2026-10-27T19:20:00+09:00")
    toda,_,_=A.build(None,payload("02"),t,"fixture")
    edogawa,_,_=A.build(None,payload("03"),t,"fixture")
    assert version(toda,"02")[-1]["model_version"]==A.VENUE_TACTICS_MODEL
    assert version(edogawa,"03")[-1]["model_version"]==A.POSTRACE_CONDITIONAL_MODEL
    assert "venue_tactics_v2" not in version(edogawa,"03")[-1]


def test_result_and_payout_cannot_change_pre_cutoff_venue_model():
    t=datetime.fromisoformat("2026-10-27T19:20:00+09:00")
    a,_,_=A.build(None,payload("02"),t,"fixture")
    b=payload("02")
    b["programs"]["stadiums"]["02"]["races"]["12"].update({
       "result":{"finish":"3-4-1"},"payout":123000,"odds":{"3-4-1":10},
       "actual_race_st":{"3":.02}})
    c,_,_=A.build(None,b,t,"fixture")
    assert version(a,"02")==version(c,"02")
