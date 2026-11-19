"""Guard rails for research-only pre-cutoff race-flow signals."""
from copy import deepcopy
import pytest

from scripts.race_flow_cues import inspect

CAPTURE = "2026-11-19T02:00:00+00:00"
CUTOFF = "2026-11-19T11:00:00+09:00"


def racers():
    out = []
    for course in range(1, 7):
        avg, st, exhibit, turn = .19, .14, 6.80, 5.70
        if course == 4:
            avg, st, exhibit, turn = .14, .09, 6.75, 5.60
        elif course == 5:
            avg, st, exhibit, turn = .155, .10, 6.77, 5.64
        out.append({
            "course": course, "lane": course,
            "average_start_timing": avg, "exhibition_st": st,
            "exhibition_time": exhibit,
            "original_exhibition": {"turn_time": turn},
        })
    return out


def run(rows=None, verified=True, capture=CAPTURE, cutoff=CUTOFF):
    return inspect(
        racers() if rows is None else rows,
        captured_at_utc=capture, cutoff_at_utc=cutoff,
        exhibition_verified=verified,
    )


def test_supported_corner_and_follower_are_possibilities_only():
    rows = racers()
    original = deepcopy(rows)
    report = run(rows)
    assert report["status"] == "SUPPORTED_PRE_CUTOFF_CUES"
    assert "FOUR_COURSE_CORNER_ATTACK_POSSIBLE" in report["scenarios"]
    assert "FIVE_COURSE_FOLLOWER_OPPORTUNITY" in report["scenarios"]
    assert "INSIDE_SURVIVAL_OR_COUNTER_PATH" in report["scenarios"]
    assert report["role"] == "research_shadow"
    assert report["not_formal"] and not report["bets_modified"]
    assert not report["results_used"] and not report["odds_used"]
    assert not report["calibrated"]
    assert rows == original


def test_actual_course_not_lane_and_no_blanket_inner_penalty():
    rows = racers()
    rows[0]["lane"], rows[3]["lane"] = 4, 1
    report = run(rows)
    assert report["evidence"]["actual_course_to_lane"]["4"] == 1
    assert report["evidence"]["actual_course_to_lane"]["1"] == 4
    assert report["not_formal"] and not report["bets_modified"]
    for row in rows:
        row["average_start_timing"] = .19
        row["original_exhibition"]["turn_time"] = 5.70
    assert run(rows)["status"] == "NO_INDEPENDENT_CORNER_SIGNAL"


def test_requires_verified_fresh_six_boat_evidence():
    assert run(verified=False)["status"] == "UNVERIFIED_EXHIBITION"
    for field, value in [("exhibition_st", -.01), ("exhibition_time", None)]:
        rows = racers()
        rows[3][field] = value
        assert run(rows)["status"] == "INCOMPLETE_PRE_CUTOFF_FEATURES"
    rows = racers()
    rows[3]["average_start_timing_imputed"] = True
    assert run(rows)["status"] == "INCOMPLETE_PRE_CUTOFF_FEATURES"
    rows = racers()
    rows[4]["original_exhibition"] = None
    assert run(rows)["status"] == "INCOMPLETE_PRE_CUTOFF_FEATURES"


def test_fail_closed_on_postrace_and_duplicate_actual_entry():
    rows = racers()
    rows[1]["actual_finish"] = 1
    with pytest.raises(ValueError, match="outcome_data"):
        run(rows)
    rows = racers()
    rows[1]["original_exhibition"]["payout"] = 1000
    with pytest.raises(ValueError, match="outcome_data"):
        run(rows)
    rows = racers()
    rows[4]["course"] = 4
    with pytest.raises(ValueError, match="duplicate"):
        run(rows)


def test_no_late_capture():
    with pytest.raises(ValueError, match="late"):
        run(capture="2026-11-19T01:59:00+00:00",
            cutoff="2026-11-19T02:00:00+00:00")
