"""Forward-only v2.4: cautious real-entry/1M and venue exhibition balance."""
from copy import deepcopy
from datetime import datetime

from scripts import autonomous_daily as A
from scripts.forecast_audit import analyze
from tests.test_four_factor_main import race


def fixture(day="2026-11-11"):
    r = race(day)
    r["racers"]["1"]["average_start_timing"] = .185
    r["racers"]["3"]["average_start_timing"] = .133
    for i in range(1, 7):
        r["racers"][str(i)]["national_win_rate"] = 5.6 + .08 * i
        r["preview"]["racers"][str(i)]["exhibition_time"] = 6.80 - .008 * i
    r["_exhibition_original"] = {
        "lap_time": {str(i): 36.9 - .03*i for i in range(1, 7)},
        "turn_time": {str(i): 5.70 - .02*i for i in range(1, 7)},
        "straight_time": {str(i): 7.45 - .02*i for i in range(1, 7)},
    }
    r["_exhibition_original"]["turn_time"]["3"] = 5.36
    return r


def test_v24_forward_formal_and_same_time_v23_control():
    now = datetime.fromisoformat("2026-11-11T09:46:00+09:00")
    src = fixture()
    frozen = A.prediction(src, "福岡", 1, "exhibition", now, "fixture")
    assert frozen["model_version"] == A.FORMAL_INSIGHT_V24_MODEL
    assert frozen["interaction_primary"]["result_data_used"] is False
    meta = frozen["formal_insight_v24"]
    assert meta["formal_component"] is True
    assert meta["pre_cutoff_only"] is True
    assert meta["frozen_at_utc"] == frozen["frozen_at_utc"]
    assert meta["exhibition_balance"]["requested"] is True
    assert meta["exhibition_balance"]["applied"] is True
    assert meta["exhibition_balance"]["metric_mix"]["time"] == .18
    assert meta["inside_pressure"]["applied"] is True
    assert meta["inside_pressure"]["attacking_course"] == 3
    assert sum(b["virtual_yen"] for b in frozen["bets"]) == 50000
    assert sum(b["virtual_yen"] for b in meta["control_bets"]) == 50000
    assert frozen["sha256"] == A.stable_hash({k: v for k, v in frozen.items()
                                                 if k != "sha256"})
    poisoned = deepcopy(src)
    poisoned["result"] = {"finish": "6-5-4", "payout_per_100": 999999}
    assert A.prediction(poisoned, "福岡", 1, "exhibition", now, "fixture") == frozen
    prior = A.prediction(fixture(), "福岡", 1, "exhibition",
                         datetime.fromisoformat("2026-11-11T09:40:00+09:00"),
                         "fixture")
    assert prior["model_version"] == A.CONDITIONAL_SECOND_MAIN_MODEL
    assert "formal_insight_v24" not in prior


def test_v24_missing_original_metrics_stays_neutral_without_fake_times():
    r = fixture()
    r["_exhibition_original"]["turn_time"].pop("5")
    frozen = A.prediction(r, "福岡", 1, "exhibition",
                          datetime.fromisoformat("2026-11-11T09:46:00+09:00"),
                          "fixture")
    assert frozen["model_version"] == A.FORMAL_INSIGHT_V24_MODEL
    assert frozen["formal_insight_v24"]["exhibition_balance"]["applied"] is False
    assert frozen["formal_insight_v24"]["inside_pressure"]["applied"] is False
    assert all(b["virtual_yen"] % 1000 == 0 for b in frozen["bets"])


def test_audit_only_counts_pre_cutoff_matched_equal_point_v24():
    now = datetime.fromisoformat("2026-11-11T09:46:00+09:00")
    frozen = A.prediction(fixture(), "福岡", 1, "exhibition", now, "fixture")
    frozen["ticket_status"] = "formal"
    report = {
        "event_date": "2026-11-11",
        "forecast_races": [frozen],
        "listed_races": 1,
        "official_results": {"2026-11-11|福岡|1": {
            "verified": True, "source": "boatrace_official_pay",
            "snapshot_sha256": frozen["sha256"],
            "finish": "3-1-5", "payout_per_100": 2500,
            "virtual_stake": 50000}},
        "settlement_alerts": {},
    }
    a = analyze(deepcopy(report))["formal_v24_forward_comparison"]
    expected = 1 if frozen["formal_insight_v24"]["same_point_count"] else 0
    assert a["official_verified_equal_point_pairs"] == expected
    assert a["historical_forecasts_immutable"] is True
    report["official_results"]["2026-11-11|福岡|1"]["verified"] = False
    b = analyze(report)["formal_v24_forward_comparison"]
    assert b["official_verified_equal_point_pairs"] == 0
