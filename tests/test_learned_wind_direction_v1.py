"""Forward-only tests: previous trained model -> directional wind -> actual tickets.

No result/odds/payout may become a formal feature. Six actual courses and
on-site pre-cutoff OpenAPI observation are mandatory.
"""
from copy import deepcopy
from datetime import datetime
from itertools import permutations
from zoneinfo import ZoneInfo

import pytest

from boat_ai.statistical import digest
from scripts.learned_wind_direction_v1 import rescore, POLICY_SHA256
from scripts.learned_formal import apply
from tests.test_learned_formal import fixture as old_fixture, model as old_model
from scripts import autonomous_daily as pipeline

JST = ZoneInfo("Asia/Tokyo")
VALID_FROZEN = "2026-11-21T01:00:00+00:00"
VALID_ORIGIN = "2026-11-21T00:59:00+00:00"


def model():
    m=old_model()
    m.update(created_at_utc="2026-11-20T01:00:00+00:00",
             trained_through="2026-11-20",training_n=4048)
    m["model_sha256"]=digest({k:v for k,v in m.items() if k!="model_sha256"})
    return m


def snapshot(code=5, speed=7, count=20):
    x=old_fixture("exhibition",count)
    x.update(
        frozen_at_utc=VALID_FROZEN,
        cutoff_iso_jst="2026-11-21T12:00:00+09:00",
        cutoff_jst="12:00",
        exhibition_origin={
            "source":"BoatraceOpenAPI","captured_before_cutoff":True,
            "captured_at_utc":VALID_ORIGIN,
            "source_observation_time":"not_provided",
        },
        weather_used={
            "source":"boatrace_preview","wind_source":"boatrace_preview",
            "site_observed":True,"wind_speed":speed,
            "wind_direction_number":code,"wave_height":3,
        },
    )
    return x


def rank():
    pairs=["-".join(map(str,p)) for p in permutations(range(1,7),3)]
    total=sum(1/(i+7) for i in range(len(pairs)))
    return [{"combination":pair,"score":(1/(i+7))/total}
            for i,pair in enumerate(pairs)]


def signature(bets):
    return sorted((x["combination"],x["virtual_yen"]) for x in bets)


def test_relative_direction_mapping_and_canonical_score_normalization():
    for code in (3,4,5,6,7):
        _,audit=rescore(rank(),snapshot(code))
        assert audit["signal"]["direction"]=="tailwind"
    for code in (11,12,13,14,15):
        rows,audit=rescore(rank(),snapshot(code))
        assert audit["signal"]["direction"]=="headwind"
        assert len(rows)==120
        assert abs(sum(r["score"] for r in rows)-1)<1e-12
        assert audit["policy_sha256"]==POLICY_SHA256
        assert audit["direction_effect_trained"] is False


def test_tail_and_head_shift_course_head_marginals():
    rows=rank()
    original=deepcopy(rows)
    tail,ta=rescore(rows,snapshot(5,7))
    head,ha=rescore(rows,snapshot(13,7))
    assert rows==original
    assert ta["after_head_shares"]["2"]>ta["before_head_shares"]["2"]
    assert ha["after_head_shares"]["4"]>ha["before_head_shares"]["4"]
    assert ha["after_head_shares"]["1"]<ha["before_head_shares"]["1"]
    assert tail != head


def test_fail_closed_without_fresh_onsite_pre_cutoff_data():
    for changed,status in (
        ({"weather_used":{"source":"open-meteo-jma","wind_source":"open-meteo-jma",
                          "site_observed":False,"wind_speed":7,"wind_direction_number":13}},
         "NO_ONSITE_PREVIEW_WIND"),
        ({"weather_used":{"source":"boatrace_preview","wind_source":"boatrace_preview",
                          "site_observed":True,"wind_speed":1.5,"wind_direction_number":13}},
         "WIND_SPEED_OR_CODE_UNAVAILABLE"),
        ({"weather_used":{"source":"boatrace_preview","wind_source":"boatrace_preview",
                          "site_observed":True,"wind_speed":5,"wind_direction_number":17}},
         "CROSSWIND_OR_CALM_NOT_WEIGHTED"),
        ({"exhibition_origin":{"source":"BoatraceCSV","captured_before_cutoff":True,
                               "captured_at_utc":VALID_ORIGIN}},
         "EXHIBITION_SOURCE_UNVERIFIED"),
        ({"frozen_at_utc":"2026-11-21T02:56:00+00:00"},
         "TOO_LATE_FOR_WIND"),
    ):
        sample=snapshot(13)
        sample.update(changed)
        previous=rank()
        actual,audit=rescore(previous,sample)
        assert audit["status"]==status
        assert actual==previous


def test_actual_entry_not_frame_and_f_not_fast_bonus():
    first=snapshot(5)
    rotated=deepcopy(first)
    rotated["racers"][0]["course"]=2
    rotated["racers"][1]["course"]=1
    control=rescore(rank(),first)[0]
    with_change=rescore(rank(),rotated)[0]
    assert control!=with_change
    bad_f=deepcopy(first)
    bad_f["racers"][1]["exhibition_st"]=-.09
    f_rank=rescore(rank(),bad_f)[0]
    indexed=lambda v,combo: next(x["score"] for x in v if x["combination"]==combo)
    assert indexed(f_rank,"2-1-3")/indexed(f_rank,"1-4-3") < (
        indexed(control,"2-1-3")/indexed(control,"1-4-3"))


def test_learned_model_formal_tickets_recomputed_using_wind_and_saved_control():
    m=model()
    raw=snapshot(13)
    old=deepcopy(raw)
    result=apply(raw,m)
    audit=result["learned_wind_direction_v1"]
    assert raw==old
    assert audit["status"]=="APPLIED_FORWARD_UNCALIBRATED",audit
    assert audit["formal_component"] is True
    assert audit["learned_training_n"]==4048
    assert audit["learned_model_sha256"]==m["model_sha256"]
    assert audit["same_time_comparison_status"]=="MATCHED_SAME_TIME"
    assert audit["same_point_count"] is True
    assert audit["same_time_final_control_bets"]
    assert sum(b["virtual_yen"] for b in result["bets"])==50000
    assert signature(audit["same_time_final_control_bets"])!=signature(result["bets"])
    assert audit["actual_ticket_or_allocation_changed"] is True
    assert "learned-wind-direction-forward-v01" in result["learned_formal"]["inference_variant"]
    assert result["learned_formal"]["wind_direction_effect_trained"] is False
    assert result["classification"]=="WATCH"
    assert audit["no_proven_performance_gain"] is True


def test_missing_wind_keeps_existing_learned_formal_exactly():
    m=model()
    with_wind=snapshot(13)
    no_wind=deepcopy(with_wind)
    no_wind["weather_used"]["wind_direction_number"]=None
    as_was=apply(no_wind,m)
    alternative=deepcopy(no_wind)
    alternative["weather_used"]["wind_direction_number"]=17
    quiet=apply(alternative,m)
    assert signature(as_was["bets"])==signature(quiet["bets"])
    assert as_was["learned_wind_direction_v1"]["formal_component"] is False
    assert "wind_direction_policy_sha256" not in as_was["learned_formal"]


def test_results_odds_never_influence_directional_bets():
    m=model()
    inp=snapshot(5)
    control=apply(inp,m)
    contaminated=deepcopy(inp)
    contaminated["result"]={"finish":"6-5-4"}
    contaminated["odds"]=19
    contaminated["payout"]=999999
    new=apply(contaminated,m)
    assert signature(control["bets"])==signature(new["bets"])


def test_builder_preserves_prior_versions_and_shows_final_audit(monkeypatch):
    m=model()
    monkeypatch.setattr(pipeline,"ACTIVE_LEARNED_MODEL",m)
    race={
        "closed_at":"2026-11-21 12:00:00",
        "racers":{str(i):{
            "name":f"選手{i}","national_win_rate":5.2,
            "motor_top_2_percent":32.0,"average_start_timing":.16,
        } for i in range(1,7)},
        "preview":{
            "wind_speed":7,"wind_direction_number":13,"wave_height":3,
            "racers":{str(i):{
                "course_number":i,"start_timing":.13+i*.01,
                "exhibition_time":6.80-i*.01,
            } for i in range(1,7)},
        },
    }
    d={"programs":{"stadiums":{"18":{"races":{"1":race}}}}}
    at=datetime(2026,11,21,10,0,tzinfo=JST)
    ledger,view,_=pipeline.build(None,d,at,"fixture")
    version=ledger["race_records"]["18-1"]["versions"][-1]
    assert version["phase"]=="exhibition"
    assert version["learned_wind_direction_v1"]["status"]=="APPLIED_FORWARD_UNCALIBRATED"
    shown=view["forecast_races"][0]
    assert shown["learned_wind_direction_v1"]==version["learned_wind_direction_v1"]
    assert shown["bets"]==version["bets"]
    assert version["sha256"]==pipeline.stable_hash({
        k:v for k,v in version.items() if k!="sha256"})
    saved=deepcopy(version)
    newer,_,s=pipeline.build(ledger,d,datetime(2026,11,21,10,1,tzinfo=JST),"fixture")
    assert newer["race_records"]["18-1"]["versions"][-1]==saved


def test_invalid_model_not_promoted_by_directional_overlay():
    m=model()
    from scripts.learned_formal import verify_model
    assert not verify_model({**m,"training_n":5},datetime(2026,11,21,10,tzinfo=JST))
