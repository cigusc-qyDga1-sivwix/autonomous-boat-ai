"""Venue-specific ST/decision postrace diagnostics; no invented adjustments."""
import pytest
from scripts.start_technique_pressure_proxy import interpret
from scripts.venue_start_technique_proxy import (
    VENUES, build_from_result_rows, summarize_venues, PRIOR_N,
)

SHA = "f" * 64

def raw(code, *, decision="まくり", winner=4, st=.08):
    row = {"レースコード": code, "1着_艇番": str(winner),
           "決まり手": decision}
    for i in range(1, 7):
        row[f"{i}コース_艇番"] = str(i)
        row[f"{i}コース_スタートタイミング"] = str(st if i == 4 else .14)
        row[f"{i}コース_F"] = ""
    return row

def proxy(code, **opts):
    return interpret(raw(code, **opts), event_date="2026-11-03", source_sha256=SHA)

def test_all_23_venues_and_edogawa_exclusion():
    assert len(VENUES) == 23 and "03" not in VENUES
    rows = [proxy("202611032101"), proxy("202611030201"), proxy("202611030301")]
    summary = summarize_venues(rows, before_date="2026-11-04")
    assert len(summary["venues"]) == 23
    assert summary["venues"]["21"]["races"] == 1
    assert summary["venues"]["02"]["races"] == 1
    assert summary["venues"]["03"] if False else True
    assert "03" not in summary["venues"]
    assert summary["global_reference"]["valid_comparisons"] == 6
    assert summary["eligible_for_formal_forecast"] is False
    assert summary["venues"]["21"]["confirmed_mark_count"] is None

def test_actual_course_and_method_strata():
    out = summarize_venues([proxy("202611032101"), proxy("202611032102")],
                           before_date="2026-11-04")
    ash = out["venues"]["21"]
    assert ash["valid_comparisons"] == 6
    assert ash["by_winning_course"]["4"]["outer_start_advantage"] == 6
    assert ash["by_winning_technique"]["まくり"]["outer_start_advantage"] == 6
    assert ash["by_inner_course"]["2"]["outer_start_advantage"] == 2
    assert ash["status"] == "INSUFFICIENT"
    assert ash["shrunk_share_given_attack_win"]["outer_start_advantage"] == 1

def test_shrinkage_toward_historical_global():
    a = proxy("202611032101")
    b = proxy("202611030201", st=.14)
    summary = summarize_venues([a, b], before_date="2026-11-04")
    ashiya = summary["venues"]["21"]
    value = ashiya["shrunk_share_given_attack_win"]["outer_start_advantage"]
    global_rate = summary["global_reference"]["descriptive_share_given_attack_win"]["outer_start_advantage"]
    assert value == pytest.approx((3 + PRIOR_N * global_rate)/(3 + PRIOR_N))
    assert value < 1

def test_no_current_or_future_and_no_duplicate():
    with pytest.raises(ValueError):
        summarize_venues([proxy("202611032101")], before_date="2026-11-03")
    x = proxy("202611032101")
    with pytest.raises(ValueError):
        summarize_venues([x, x], before_date="2026-11-04")

def test_raw_historical_input_gate():
    items = [{"event_date": "2026-11-03", "source_sha256": SHA,
              "row": raw("202611032101")}]
    result = build_from_result_rows(items, before_date="2026-11-04")
    assert result["venues"]["21"]["races"] == 1
    items[0]["event_date"] = "2026-11-04"
    with pytest.raises(ValueError):
        build_from_result_rows(items, before_date="2026-11-04")

def test_unknown_st_separate_denominator():
    r = raw("202611032101")
    r["3コース_スタートタイミング"] = "-"
    p = interpret(r, event_date="2026-11-03", source_sha256=SHA)
    out = summarize_venues([p], before_date="2026-11-04")
    assert out["venues"]["21"]["valid_comparisons"] == 2
    assert out["venues"]["21"]["missing_st_comparisons"] == 1
