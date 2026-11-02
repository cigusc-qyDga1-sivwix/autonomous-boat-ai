"""Guard against nationwide Node bridge work finishing after a race cutoff."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from scripts import autonomous_daily as daily

JST = ZoneInfo("Asia/Tokyo")


def test_completion_clock_rejects_late_append_despite_early_frozen_timestamp():
    cutoff = datetime(2026, 11, 2, 12, 43, tzinfo=JST)
    early = cutoff - timedelta(minutes=4)
    just_before = cutoff - timedelta(minutes=3)
    late = cutoff - timedelta(minutes=1)
    snapshot = {"frozen_at_utc": early.isoformat()}
    assert daily.safe_to_append_pre_cutoff(snapshot, cutoff, 120, just_before)
    assert not daily.safe_to_append_pre_cutoff(snapshot, cutoff, 120, late)
    assert not daily.safe_to_append_pre_cutoff(
        {"frozen_at_utc": late.isoformat()}, cutoff, 120, early
    )
    assert not daily.safe_to_append_pre_cutoff(
        {"frozen_at_utc": "2026-11-02T12:30:00"}, cutoff, 120, just_before
    )


def _program(with_preview=False):
    racers = {
        str(i): {
            "name": f"選手{i}", "national_win_rate": 5.2,
            "motor_top_2_percent": 32.0, "average_start_timing": .16,
        } for i in range(1, 7)
    }
    r = {"closed_at": "2026-10-22 10:00:00", "racers": racers}
    if with_preview:
        r["preview"] = {
            "wind_speed": 3, "wave_height": 2, "wind_direction_number": 5,
            "racers": {
                str(i): {
                    "course_number": i, "start_timing": .1 + i*.01,
                    "exhibition_time": 6.8 - i*.01, "tilt_adjustment": -.5
                } for i in range(1, 7)
            }
        }
    return {"programs": {"stadiums": {"18": {"races": {"1": r}}}}}


def test_late_prediction_completion_never_creates_new_baseline(monkeypatch):
    def late_prediction(*args, **kwargs):
        return {"frozen_at_utc": "2026-10-22T02:00:00+00:00"}

    monkeypatch.setattr(daily, "prediction", late_prediction)
    ledger, view, status = daily.build(
        None, _program(), datetime(2026, 10, 22, 8, 30, tzinfo=JST), "fixture"
    )
    assert ledger["race_records"]["18-1"]["versions"] == []
    assert status["new_baseline"] == 0
    assert view["forecast_races"] == []
    assert len(view["unforecast_races"]) == 1


def test_late_exhibition_does_not_replace_valid_baseline(monkeypatch):
    early, _, _ = daily.build(
        None, _program(), datetime(2026, 10, 22, 8, 30, tzinfo=JST), "fixture"
    )
    baseline = early["race_records"]["18-1"]["versions"][0].copy()

    def late_prediction(*args, **kwargs):
        return {"frozen_at_utc": "2026-10-22T02:00:00+00:00"}

    monkeypatch.setattr(daily, "prediction", late_prediction)
    ledger, view, status = daily.build(
        early, _program(with_preview=True),
        datetime(2026, 10, 22, 9, 30, tzinfo=JST), "fixture"
    )
    assert ledger["race_records"]["18-1"]["versions"] == [baseline]
    assert status["new_exhibition"] == 0
    assert view["forecast_races"][0]["phase"] == "baseline"
