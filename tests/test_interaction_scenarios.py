"""Offline, deterministic contracts for the isolated interaction research model."""
import pytest
from scripts.interaction_scenarios import evaluate

CAPTURE = "2026-11-04T00:01:00+00:00"
CUTOFF = "2026-11-04T01:00:00+00:00"


def entrants():
    return [{"lane": i, "strength": 10 + i, "start_mean": .15,
             "exhibition_time": 6.8} for i in range(1, 7)]


def run(rows=None, **kwargs):
    return evaluate(entrants() if rows is None else rows,
                    captured_at_utc=kwargs.get("capture", CAPTURE),
                    cutoff_at_utc=kwargs.get("cutoff", CUTOFF))


def test_deterministic_and_normalized():
    a = run()
    assert a == run()
    assert a["status"] == "SHADOW_UNCALIBRATED"
    assert a["eligible_for_formal_forecast"] is False
    assert a["bets_generated"] == 0
    assert abs(a["relative_score_sum"] - 1) < 1e-6
    assert len(a["scenario_assumptions"]) == 5
    assert len(a["top_combinations"]) == 120
    assert all(len(set(x["combination"].split("-"))) == 3
               for x in a["top_combinations"])


def test_outcome_fields_rejected():
    for field in ("result", "payout", "actual_start", "odds", "finish"):
        rows = entrants()
        rows[0][field] = 1
        with pytest.raises(ValueError):
            run(rows)


def test_duplicate_missing_and_invalid_inputs_rejected():
    rows = entrants()
    rows[5]["lane"] = 1
    with pytest.raises(ValueError):
        run(rows)
    with pytest.raises(ValueError):
        run(entrants()[:5])
    rows = entrants()
    rows[0]["strength"] = float("nan")
    with pytest.raises(ValueError):
        run(rows)


def test_cutoff_and_naive_time_rejected():
    with pytest.raises(ValueError):
        run(capture=CUTOFF)
    with pytest.raises(ValueError):
        run(capture="2026-11-04T08:00:00")
    with pytest.raises(ValueError):
        run(capture="2026-11-04T02:00:00+00:00")


def test_contested_vs_success_path_changes_followers():
    x = run()
    successful = next(s for s in x["scenario_assumptions"]
                      if s["scenario"] == "outer_attack_succeeds")
    contested = next(s for s in x["scenario_assumptions"]
                     if s["scenario"] == "attack_contested")
    assert successful["attack_lane"] == contested["attack_lane"]
    assert successful["top_3"] != contested["top_3"]

def test_inside_failure_is_possible_but_not_assumed_certain():
    x = run()
    assert 0 < x["course1_outside_top3_relative_mass"] < 1
    assert x["course1_outside_top3_by_path"]["inside_displaced"] > 0
    assert x["course1_outside_top3_by_path"]["inside_displaced"] > x["course1_outside_top3_by_path"]["no_major_attack"]
    assert any("1" not in ticket["combination"].split("-") for ticket in x["top_combinations"])


def test_upstream_course_strength_is_not_applied_twice():
    rows = [{"lane": i, "strength": 20, "start_mean": None,
             "exhibition_time": None} for i in range(1, 7)]
    x = run(rows)
    calm = next(p for p in x["scenario_assumptions"] if p["scenario"] == "no_major_attack")
    # With equal upstream inputs there is no *additional* lane premium.
    assert calm["top_3"][0][1] == pytest.approx(1 / 120, rel=1e-6)

def test_start_and_exhibition_are_not_scored_twice():
    rows = [{"lane": i, "strength": 20, "start_mean": .11 + i*.02,
             "exhibition_time": 6.65 + i*.05} for i in range(1, 7)]
    a = run(rows)
    # After upstream feature calculation the scenario layer must not apply
    # another ST/exhibition premium on the same six relative strengths.
    for row in rows:
        row["start_mean"] = .16
        row["exhibition_time"] = 6.8
    b = run(rows)
    assert a["top_combinations"] == b["top_combinations"]
    assert a["course1_outside_top3_relative_mass"] == b["course1_outside_top3_relative_mass"]
