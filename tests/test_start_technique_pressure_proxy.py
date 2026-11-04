"""Observational classification, never inferred confirmed marking."""
import pytest
from scripts.start_technique_pressure_proxy import interpret, summarize

SHA = "a"*64

def result(method="まくり", winner=4):
    row={"レースコード":"202611042101","1着_艇番":str(winner),"決まり手":method}
    for c in range(1,7):
        row[f"{c}コース_艇番"]=str(c)
        row[f"{c}コース_スタートタイミング"]="0.14"
        row[f"{c}コース_F"]=""
    row["4コース_スタートタイミング"]="0.08"
    return row

def check(r):
    return interpret(r,event_date="2026-11-04",source_sha256=SHA)

def test_outer_win_is_not_proof_of_marking():
    x=check(result())
    assert x["winner_course"]==4
    assert all(v["hypothesis"]=="outer_start_advantage" for v in x["comparisons"])
    assert x["confirmed_mark_count"] is None
    assert not x["eligible_as_same_race_forecast_input"]
    assert summarize([x])["comparison_counts"]["outer_start_advantage"]==3

def test_close_start_is_only_hypothesis():
    r=result()
    r["3コース_スタートタイミング"]="0.09"
    x=check(r)
    assert x["comparisons"][-1]["hypothesis"]=="close_start_possible_course_contest"

def test_flying_and_missing_st_are_unknown():
    r=result()
    r["3コース_スタートタイミング"]="-0.02"
    r["3コース_F"]="F"
    r["2コース_スタートタイミング"]="-"
    x=check(r)
    assert x["comparisons"][1]["status"]=="UNKNOWN_START"
    assert x["comparisons"][2]["status"]=="UNKNOWN_START"

def test_non_attack_decision_has_no_attack_inference():
    x=check(result(method="差し",winner=2))
    assert x["comparisons"]==[]

def test_bad_identity_and_course_rejected():
    r=result()
    r["レースコード"]="202611032101"
    with pytest.raises(ValueError):check(r)
    r=result()
    r["3コース_艇番"]="2"
    with pytest.raises(ValueError):check(r)

def test_no_double_counting_same_race():
    x=check(result())
    with pytest.raises(ValueError):summarize([x,x])
