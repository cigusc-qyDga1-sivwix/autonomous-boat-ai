"""Offline invariants for the nationwide autonomous pipeline."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.autonomous_daily import build, prediction, preview_complete, valid_entrants

JST = ZoneInfo("Asia/Tokyo")


def race(cutoff="2026-10-22 10:00:00", show_preview=False, finished=False):
    r = {"closed_at": cutoff,
         "racers": {str(i): {"name": f"選手{i}", "national_win_rate": 5.2,
                              "motor_top_2_percent": 32.0,
                              "average_start_timing": .16} for i in range(1, 7)}}
    if show_preview:
        r["preview"] = {"wind_speed": 3, "wave_height": 2, "wind_direction_number": 5,
                        "racers": {str(i): {"course_number": i, "start_timing": .1 + i*.01,
                                             "exhibition_time": 6.8 - i*.01,
                                             "tilt_adjustment": -.5} for i in range(1, 7)}}
    if finished:
        r["result"] = {"payouts": {"trifecta": [{"combination": "2-1-3", "amount": 2460}]}}
    return r


def data(r):
    return {"programs": {"stadiums": {"18": {"races": {"1": r}}}}}


def test_before_cutoff_baseline_and_immutability():
    now = datetime(2026, 10, 22, 8, 30, tzinfo=JST)
    original, ui, summary = build(None, data(race()), now, "fixture")
    assert summary["new_baseline"] == 1
    assert summary["new_exhibition"] == 0
    assert len(ui["forecast_races"]) == 1
    old = original["race_records"]["18-1"]["versions"][0]
    assert len(old["bets"]) == 8
    assert sum(b["virtual_yen"] for b in old["bets"]) == 50000
    assert old["phase"] == "baseline"
    assert old["frozen_at_utc"] < "2026-10-22T10:00:00"
    assert old["sha256"]
    repeat, _, summary2 = build(original, data(race()), datetime(2026,10,22,8,40,tzinfo=JST), "fixture")
    assert summary2["new_baseline"] == 0
    assert repeat["race_records"]["18-1"]["versions"][0] == old


def test_exhibition_creates_new_version_but_preserves_baseline():
    now = datetime(2026, 10, 22, 8, 30, tzinfo=JST)
    old, _, _ = build(None, data(race()), now, "fixture")
    prior = old["race_records"]["18-1"]["versions"][0]
    newer, ui, summary = build(old, data(race(show_preview=True)),
                               datetime(2026,10,22,9,30,tzinfo=JST), "fixture")
    assert summary["new_exhibition"] == 1
    assert newer["race_records"]["18-1"]["versions"][0] == prior
    final = newer["race_records"]["18-1"]["versions"][1]
    assert final["phase"] == "exhibition"
    assert final["weather_observed"]["wind_speed"] == 3
    assert ui["forecast_races"][0]["phase"] == "exhibition"
    _, _, same = build(newer, data(race(show_preview=True)),
                       datetime(2026,10,22,9,40,tzinfo=JST), "fixture")
    assert same["new_exhibition"] == 0


def test_no_post_cutoff_backfill_even_if_result_exists():
    late = datetime(2026, 10, 22, 11, 0, tzinfo=JST)
    ledger, ui, metrics = build(None, data(race(show_preview=True, finished=True)),
                                late, "fixture")
    assert metrics["forecast_races"] == 0
    assert ledger["race_records"]["18-1"]["versions"] == []
    assert ui["official_results"] == {}
    assert ui["unforecast_races"][0]["race"] == 1
    with pytest.raises(ValueError):
        prediction(race(), "徳山", 1, "baseline", late, "fixture")


def test_results_added_only_to_existing_pre_cutoff_prediction():
    early = datetime(2026,10,22,9,10,tzinfo=JST)
    original, _, _ = build(None, data(race()), early, "fixture")
    frozen = original["race_records"]["18-1"]["versions"][0]
    past, ui, _ = build(original, data(race(finished=True)),
                        datetime(2026,10,22,11,0,tzinfo=JST), "fixture")
    assert past["race_records"]["18-1"]["versions"][0] == frozen
    # An unofficial result can be present in the daily feed, but must never
    # count toward official confirmed settlements.
    assert ui["official_results"] == {}


def test_incomplete_exhibition_rejected():
    r = race(show_preview=True)
    del r["preview"]["racers"]["6"]["exhibition_time"]
    assert valid_entrants(r)
    assert not preview_complete(r)
    ledger, ui, stats = build(None, data(r), datetime(2026,10,22,9,0,tzinfo=JST), "fixture")
    assert stats["new_exhibition"] == 0
    assert ui["forecast_races"][0]["phase"] == "baseline"
