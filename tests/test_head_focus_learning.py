"""Outcomes label risk cohorts only; all signals come from original pre-cutoff data."""
from copy import deepcopy
from scripts.head_focus_learning import inspect, VERSION

def sample(venue, race, finish, st_inner=.18, motor_inner=32, skill_inner=5.0,
           complete=True, status="formal", sha="sha", heads=("1","2")):
    row={
        "venue":venue,"race":race,"sha256":sha,"phase":"exhibition",
        "ticket_status":status,
        "bets":[{"combination":head+"-3-4","virtual_yen":50000//len(heads)} for head in heads],
        "racers":[{"lane":i,"course":i,
                   "exhibition_st":st_inner if i==1 else .11,
                   "motor_top_2_percent":motor_inner if i==1 else 46,
                   "national_win_rate":skill_inner if i==1 else 7.0}
                  for i in range(1,7)],
    }
    if not complete:row["racers"][1].pop("exhibition_st")
    outcome={"venue":venue,"race":race,"snapshot_sha256":sha,
             "ticket_status":status,"actual_finish":finish,
             "actual_head":finish[0],"first_bet_head":heads[0],
             "stage":"head_miss" if finish[0] not in heads else "second_miss"}
    return row,outcome

def test_fixed_precutoff_signals_and_labeling():
    a,b=sample("若松",1,"5-1-3")
    c,d=sample("若松",2,"1-3-4",st_inner=.10,motor_inner=47,skill_inner=7.1)
    e,f=sample("若松",3,"3-1-2",complete=False)
    rows=[a,c,e];labels=[b,d,f]
    original=deepcopy([rows,labels])
    out=inspect(rows,labels)
    assert out["schema"]==VERSION
    assert out["research_only"] and out["postrace_labels_not_forecast_inputs"]
    assert not out["formal_forecasts_modified"]
    assert out["formal"]["verified_races"]==3
    assert out["formal"]["outside_wins"]==2
    assert out["formal"]["outside_win_head_misses"]==2
    assert out["formal"]["outside_win_lane1_second"]==2
    assert out["cohorts"]["2_or_more"]["verified_races"]==1
    assert out["cohorts"]["2_or_more"]["outside_wins"]==1
    assert out["cohorts"]["0"]["verified_races"]==1
    assert out["cohorts"]["insufficient_pre_cutoff_evidence"]["verified_races"]==1
    assert [rows,labels]==original

def test_excludes_provisional_and_wrong_sha():
    a,b=sample("唐津",1,"1-3-4",sha="a")
    c,d=sample("唐津",2,"3-1-2",sha="b",status="provisional")
    e,f=sample("唐津",3,"1-3-2",sha="c")
    f["snapshot_sha256"]="mismatch"
    out=inspect([a,c,e],[b,d,f])
    assert out["formal"]["verified_races"]==1
    assert out["formal"]["lane1_wins"]==1

def test_no_postrace_label_used_to_compute_risk_membership():
    r,a=sample("児島",1,"1-3-4")
    flipped={**a,"actual_finish":"5-2-4","actual_head":"5","stage":"head_miss"}
    left=inspect([r],[a]);right=inspect([r],[flipped])
    assert {key:value["verified_races"] for key,value in left["cohorts"].items()} == {
        key:value["verified_races"] for key,value in right["cohorts"].items()}
    assert left["cohorts"]["2_or_more"]["outside_wins"]==0
    assert right["cohorts"]["2_or_more"]["outside_wins"]==1
