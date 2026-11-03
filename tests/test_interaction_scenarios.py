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
    assert len(a["scenario_assumptions"]) == 4
    assert len(a["top_combinations"]) == 12
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
