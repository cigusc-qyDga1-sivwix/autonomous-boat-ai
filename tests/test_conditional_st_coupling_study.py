"""Outcome-conditioned finish diagnostics: synthetic data, no real bet claims."""
import pytest
from scripts.conditional_st_coupling_study import (
    label_result, summarize, VENUES, VERSION,
)

SHA = "a"*64


def raw(code="202611032101", head=3, second=4, third=5,
        method="まくり", course1_st=".15", course3_st=".08"):
    out = {"レースコード": code,
           "1着_艇番": str(head),
           "2着_艇番": str(second), "3着_艇番": str(third),
           "決まり手": method}
    for course in range(1, 7):
        out[f"{course}コース_艇番"] = str(course)
        out[f"{course}コース_スタートタイミング"] = (
            course1_st if course == 1 else
            course3_st if course == 3 else ".15")
        out[f"{course}コース_F"] = ""
    return out


def label(row=None, day="2026-11-03"):
    return label_result(raw() if row is None else row, event_date=day, source_sha256=SHA)


def test_inside_lag_middle_and_one_outside():
    x = label()
    assert x["venue_code"] == "21"
    assert x["observed_slit_group"] == "inside_behind_middle"
    assert x["course1_finish"] == "outside_top3"
    assert x["winner_course"] == 3 and x["second_course"] == 4
    assert x["third_course"] == 5
    assert x["confirmed_mark_count"] is None
    assert x["confirmed_1m_path"] is None
    assert not x["eligible_for_current_race_forecast"]


def test_equal_st_and_missing_or_f_st():
    x = label(raw(head=1, second=2, third=3, method="逃げ",
                  course1_st=".15", course3_st=".15"))
    assert x["observed_slit_group"] == "near_even_start"
    x = raw()
    x["3コース_スタートタイミング"] = "-"
    assert label(x)["observed_slit_group"] == "unknown_st"
    x = raw()
    x["3コース_スタートタイミング"] = "-0.02"
    x["3コース_F"] = "F"
    assert label(x)["observed_slit_group"] == "unknown_st"


def test_complete_23_venue_report_and_edogawa_exclusion():
    group = [
        label(),
        label(raw("202611030201", head=1, second=2, third=3,
                  method="逃げ", course1_st=".10", course3_st=".15")),
        label(raw("202611030301", head=4, second=5, third=6)),
    ]
    report = summarize(group, before_date="2026-11-04")
    assert len(VENUES) == 23 and "03" not in VENUES
    assert len(report["venues"]) == 23
    assert report["included_races"] == 2
    assert report["excluded_edogawa_races"] == 1
    assert report["venues"]["21"]["course1_finish_counts"]["outside_top3"] == 1
    assert report["venues"]["02"]["course1_finish_counts"]["1"] == 1
    assert report["venues"]["21"]["conditional_followups_by_winner_course"]["3"]["second_course_counts"]["4"] == 1


def test_pairwise_historical_counts_are_conditional_not_mark_labels():
    rows = []
    for i in range(40):
        date_s = ["20261031", "20261101", "20261102", "20261103"][i//10]
        code = date_s + "21" + f"{i%10 + 1:02d}"
        day = date_s[:4] + "-" + date_s[4:6] + "-" + date_s[6:]
        if i < 20:
            r = raw(code, head=3, second=4, third=5)
        else:
            r = raw(code, head=1, second=2, third=3,
                    method="逃げ", course1_st=".10", course3_st=".15")
        rows.append(label(r, day))
    out = summarize(rows, before_date="2026-11-04")
    comparison = out["venues"]["21"]["adjacent_course_conditional_finish"]["3head_2partner"]
    assert comparison["status"] == "DESCRIPTIVE"
    assert comparison["head_races"] == 20
    assert comparison["other_races"] == 20
    assert comparison["inner_top3_given_head_rate"] == 0.0
    assert comparison["inner_top3_given_other_head_rate"] == 1.0
    assert comparison["meaning"] == "finish correlation, not observed marking or attack"


def test_unknown_does_not_count_as_inside_lead():
    x = raw()
    x["1コース_スタートタイミング"] = "-"
    out = summarize([label(x)], before_date="2026-11-04")
    assert out["venues"]["21"]["by_observed_slit"]["unknown_st"]["races"] == 1
    assert out["venues"]["21"]["by_observed_slit"]["inside_clear_start_lead"]["races"] == 0


def test_no_today_aftercutoff_duplicate_or_fake_1m_maneuver():
    x = label()
    with pytest.raises(ValueError):
        summarize([x], before_date="2026-11-03")
    with pytest.raises(ValueError):
        summarize([x, x], before_date="2026-11-04")
    x["eligible_for_current_race_forecast"] = True
    with pytest.raises(ValueError):
        summarize([x], before_date="2026-11-04")


def test_inconsistent_finish_refused():
    r = raw(head=3, second=3)
    with pytest.raises(ValueError):
        label(r)
    r = raw()
    r["1着_艇番"] = "7"
    with pytest.raises(ValueError):
        label(r)
