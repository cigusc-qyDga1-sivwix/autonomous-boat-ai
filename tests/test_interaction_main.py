"""Forward-only main promotion checks with same-time old-main control."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from scripts.autonomous_daily import (
    prediction, build, INTERACTION_MAIN_MODEL, stable_hash,
)

JST = ZoneInfo("Asia/Tokyo")


def entry(cutoff="2026-11-04 11:00:00", preview=False):
    racers = {str(i): {"name": f"racer{i}", "national_win_rate": 5.1 + .1*i,
                       "motor_top_2_percent": 30 + i,
                       "average_start_timing": .15 + i*.001} for i in range(1, 7)}
    result = {"closed_at": cutoff, "racers": racers}
    if preview:
        result["preview"] = {
            "wind_speed": 2, "wave_height": 1, "wind_direction_number": 5,
            "racers": {str(i): {"course_number": i, "start_timing": .1 + i*.01,
                               "exhibition_time": 6.8 + i*.005} for i in range(1, 7)}
        }
    return result


def test_promoted_baseline_is_primary_and_control_is_preserved():
    now = datetime(2026, 11, 4, 9, 30, tzinfo=JST)
    result = prediction(entry(), "徳山", 1, "baseline", now, "fixture")
    assert result["model_version"] == INTERACTION_MAIN_MODEL
    assert result["model_role"] == "main"
    assert result["interaction_primary"]["uncalibrated"] is True
    assert result["interaction_primary"]["old_main_model_version"] != result["model_version"]
    assert result["interaction_primary"]["old_main_bets"]
    assert len(result["bets"]) == len(result["interaction_primary"]["old_main_bets"])
    assert sum(b["virtual_yen"] for b in result["bets"]) == 50000
    assert sum(b["virtual_yen"] for b in result["interaction_primary"]["old_main_bets"]) == 50000
    assert result["sha256"] == stable_hash({k: v for k, v in result.items() if k != "sha256"})


def test_exhibition_stays_main_and_uses_frozen_input():
    result = prediction(entry(preview=True), "徳山", 1, "exhibition",
                        datetime(2026, 11, 4, 9, 30, tzinfo=JST), "fixture")
    assert result["model_version"] == INTERACTION_MAIN_MODEL
    assert result["phase"] == "exhibition"
    assert len(result["bets"]) == len(result["interaction_primary"]["old_main_bets"])


def test_old_snapshot_is_not_rewritten_during_forward_upgrade():
    now = datetime(2026, 11, 4, 9, 30, tzinfo=JST)
    race = entry()
    source = {"programs": {"stadiums": {"18": {"races": {"1": race}}}}}
    ledger, app, _ = build(None, source, now, "fixture")
    snap = ledger["race_records"]["18-1"]["versions"][0]
    assert snap["model_version"] == INTERACTION_MAIN_MODEL
    ledger2, app2, summary = build(ledger, source, now, "fixture")
    assert ledger2["race_records"]["18-1"]["versions"][0] == snap
    assert summary["new_baseline"] == 0


def test_no_backdated_main_creation():
    with pytest.raises(ValueError):
        prediction(entry(), "徳山", 1, "baseline",
                   datetime(2026, 11, 4, 11, 0, tzinfo=JST), "fixture")
