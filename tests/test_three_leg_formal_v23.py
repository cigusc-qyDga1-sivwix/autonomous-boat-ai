"""Forward-only formal v2.3 movement redistribution; frozen controls never backfilled."""
from copy import deepcopy
from datetime import datetime
from scripts import autonomous_daily as A

DAY="2026-11-10"
TIME=datetime.fromisoformat("2026-11-10T12:00:00+09:00")
BEFORE=datetime.fromisoformat("2026-11-10T10:20:00+09:00")

def race():
    r={
        "closed_at": DAY+" 13:00:00",
        "racers": {str(i): {
            "name": f"選手{i}", "number":4000+i,
            "national_win_rate": 6.5-i*.12,
            "average_start_timing": .13+i*.007,
            "motor_top_2_percent": 53-i*4
        } for i in range(1,7)},
        "preview": {"wind_speed":2,"wave_height":1,"racers":{
            str(i):{"course_number":i,"start_timing":round(.10+i*.011,3),
                    "exhibition_time":round(6.71+i*.031,3),
                    "tilt_adjustment":0} for i in range(1,7)}},
        "_exhibition_origin":{
            "source":"BoatraceCSV","captured_before_cutoff":True,
            "observed_at_jst":"2026-11-10T11:20:00+09:00"},
        "_exhibition_original":{
            "lap_time":{str(i):round(36.0-i*.10,2) for i in range(1,7)},
            "turn_time":{str(i):round(5.9-i*.12,2) for i in range(1,7)},
            "straight_time":{str(i):round(7.1+i*.042,3) for i in range(1,7)}
        }
    }
    return r

def test_pre_cutoff_formal_v23_three_legs_and_old_control():
    new=A.prediction(race(),"徳山",1,"exhibition",TIME,"fixture")
    assert new["model_version"]==A.CONDITIONAL_SECOND_MAIN_MODEL
    assert new["model_role"]=="main"
    leg=new["three_leg_primary"]
    assert leg["status"]=="applied"
    assert leg["applied"] is True
    assert leg["formal_component"] is True
    assert leg["source_exhibition_weight_unchanged"] is True
    assert leg["same_input_prior_v23_control"] is True
    assert leg["control_no_postrace_data"] is True
    assert leg["frozen_at_utc"]==new["frozen_at_utc"]
    assert len(new["bets"])==len(leg["control_bets"]) if leg["same_point_count"] else True
    assert sum(b["virtual_yen"] for b in leg["control_bets"])==50000
    assert sum(b["virtual_yen"] for b in new["bets"])==50000
    assert leg["control_ranked_sha256"] != leg["main_ranked_sha256"]
    assert len(leg["rows"])==6
    assert all(abs(x["multipliers"]["go"]-1)<1e-12 for x in leg["rows"])
    assert new["sha256"]==A.stable_hash({k:v for k,v in new.items() if k!="sha256"})
    with_results=deepcopy(race())
    with_results["result"]={"finish":"6-5-4"}
    with_results["official_pay"]={"payout_per_100":99999}
    assert A.prediction(with_results,"徳山",1,"exhibition",TIME,"fixture")["bets"]==new["bets"]

def test_missing_original_turn_does_not_change_new_main():
    r=race()
    r["_exhibition_original"]["turn_time"].pop("3")
    snap=A.prediction(r,"徳山",1,"exhibition",TIME,"fixture")
    assert snap["three_leg_primary"]["status"]=="incomplete_required_exhibition"
    assert snap["three_leg_primary"]["applied"] is False
    assert snap["three_leg_primary"]["same_input_prior_v23_control"] is False

def test_historical_pre_activation_v23_kept_and_archival_versions_immutable():
    r=race()
    old=A.prediction(r,"徳山",1,"exhibition",BEFORE,"fixture")
    assert old["model_version"]==A.CONDITIONAL_SECOND_MAIN_MODEL
    assert "three_leg_primary" not in old
    src={"programs":{"stadiums":{"18":{"races":{"1":r}}}}}
    ledger,_,_=A.build(None,src,BEFORE,"fixture")
    initial=deepcopy(ledger["race_records"]["18-1"]["versions"])
    again,_,_=A.build(ledger,src,TIME,"fixture")
    assert again["race_records"]["18-1"]["versions"][:len(initial)]==initial
    closed,_,_=A.build(again,src,
        datetime.fromisoformat("2026-11-10T13:10:00+09:00"),"fixture")
    assert closed["race_records"]["18-1"]["versions"]==again["race_records"]["18-1"]["versions"]

def test_baseline_not_given_three_leg_primary():
    r=race()
    r.pop("preview")
    result=A.prediction(r,"徳山",1,"baseline",TIME,"fixture")
    assert "three_leg_primary" not in result
