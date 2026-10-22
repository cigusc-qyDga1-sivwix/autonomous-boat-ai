"""Offline invariants for the nationwide autonomous pipeline."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.autonomous_daily import (build, prediction, preview_complete, valid_entrants,
                                     point_count, combinations, allocate_stakes)

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
    assert 4 <= len(old["bets"]) <= 12
    assert sum(b["virtual_yen"] for b in old["bets"]) == 50000
    assert old["point_count"] == len(old["bets"])
    assert old["point_reason"]
    assert all(b["virtual_yen"] >= 1000 and b["virtual_yen"] % 1000 == 0 for b in old["bets"])
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



def test_point_count_changes_with_relative_head_uncertainty():
    confident = [20.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    unclear = [1.0] * 6
    n4, reason4, *_ = point_count(confident)
    n12, reason12, *_ = point_count(unclear)
    assert n4 == 4
    assert n12 == 12
    assert "相対重み" in reason4 and "分岐" in reason12
    for weights, desired in ((confident, 4), (unclear, 12)):
        combos = combinations(weights)
        assert len(combos) == desired
        assert len({c for c, _ in combos}) == desired
        bets = allocate_stakes(combos)
        assert len(bets) == desired
        assert sum(b["virtual_yen"] for b in bets) == 50_000
        assert all(b["virtual_yen"] >= 1000 and b["virtual_yen"] % 1000 == 0 for b in bets)


def test_sizing_thresholds_cover_middle_counts():
    # These synthetic profiles deliberately target different certainty bands.
    examples = [
        [2.0, 1.5, 1.4, 1.3, 1.2, 1.1],
        [3.0, 1.5, 1.4, 1.3, 1.2, 1.1],
        [4.0, 1.5, 1.4, 1.3, 1.2, 1.1],
        [6.0, 1.5, 1.4, 1.3, 1.2, 1.1],
    ]
    counts = [point_count(w)[0] for w in examples]
    assert all(4 <= n <= 12 for n in counts)
    assert len(set(counts)) >= 2


def test_existing_8_point_snapshot_is_never_rewritten():
    now = datetime(2026, 10, 22, 8, 30, tzinfo=JST)
    ledger, _, _ = build(None, data(race()), now, "fixture")
    snap = ledger["race_records"]["18-1"]["versions"][0]
    # An earlier pre-v0.3 8-point snapshot remains historically immutable.
    legacy = dict(snap)
    legacy.pop("point_count", None)
    legacy.pop("point_reason", None)
    legacy.pop("head_weight_concentration", None)
    legacy.pop("head_weight_gap", None)
    legacy["model_version"] = "heuristic-0.2-untrained"
    legacy["bets"] = [{"combination": c, "virtual_yen": v}
                      for c, v in zip(
                          ["1-2-3", "2-1-3", "1-3-2", "3-1-2", "1-2-4", "2-3-1", "4-1-2", "1-4-2"],
                          [12000, 10000, 8000, 6000, 5000, 4000, 3000, 2000])]
    ledger["race_records"]["18-1"]["versions"] = [legacy]
    persisted, view, status = build(ledger, data(race()), datetime(2026,10,22,8,40,tzinfo=JST), "fixture")
    assert persisted["race_records"]["18-1"]["versions"] == [legacy]
    assert view["forecast_races"][0]["bets"] == legacy["bets"]
    assert len(view["forecast_races"][0]["bets"]) == 8
    assert status["new_baseline"] == 0
