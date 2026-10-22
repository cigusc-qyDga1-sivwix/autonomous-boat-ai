"""Offline invariants for audited immutable predictions and official result labels."""
from copy import deepcopy
from datetime import datetime, timezone

from scripts.forecast_audit import analyze

BETS = [
    {"combination": c, "virtual_yen": amount}
    for c, amount in zip(
        ("1-2-3", "2-1-3", "1-3-2", "3-1-2",
         "1-2-4", "2-3-1", "1-3-4", "1-2-5"),
        (12000, 10000, 8000, 6000, 5000, 4000, 3000, 2000))
]


def make_example():
    races = []
    results = {}
    finishes = ("1-2-3", "1-6-2", "1-2-6", "5-1-2")
    for i, finish in enumerate(finishes, 1):
        race = {
            "venue": "徳山", "race": i,
            "cutoff_jst": "14:00", "frozen_at_utc": "2026-10-22T03:00:00+00:00",
            "model_version": "heuristic-0.2-untrained", "phase": "baseline",
            "classification": "WATCH", "sha256": f"snapshot-{i}",
            "bets": deepcopy(BETS),
        }
        races.append(race)
        results[f"2026-10-22|徳山|{i}"] = {
            "verified": True, "source": "boatrace_official_pay",
            "snapshot_sha256": race["sha256"], "finish": finish,
            "payout_per_100": 1000,
            "virtual_stake": 50000,
        }
    return {
        "event_date": "2026-10-22", "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "auto-live", "listed_races": 8,
        "forecast_races": races, "official_results": results,
        "unforecast_races": [{"venue": "徳山", "race": 5}],
        "settlement_alerts": {}
    }


def test_decomposes_errors_without_counting_missing_races_as_losses():
    report = analyze(make_example())
    metrics = report["metrics"]
    assert metrics["verified_races"] == 4
    assert metrics["hits"] == 1
    assert metrics["head_captured"] == 3
    assert metrics["first_second_captured"] == 2
    assert metrics["head_miss"] == metrics["second_miss"] == metrics["third_miss"] == 1
    assert metrics["virtual_stake_yen"] == 200000
    assert metrics["virtual_payout_yen"] == 120000
    assert metrics["virtual_profit_yen"] == -80000
    assert metrics["return_rate"] == .6
    assert report["coverage"]["unforecast_races"] == 1
    assert report["bias"]["first_bet_head_1_verified"] == 4
    assert report["bias"]["actual_winner_1_verified"] == 3
    assert report["by_model"]["heuristic-0.2-untrained"]["verified_races"] == 4


def test_wrong_snapshot_or_unverified_official_data_is_never_scored():
    payload = make_example()
    payload["official_results"]["2026-10-22|徳山|1"]["snapshot_sha256"] = "tampered"
    payload["official_results"]["2026-10-22|徳山|2"]["verified"] = False
    payload["settlement_alerts"]["2026-10-22|徳山|3"] = {"status": "review"}
    result = analyze(payload)
    assert result["metrics"]["verified_races"] == 1
    assert result["metrics"]["hits"] == 0
    assert result["exclusions"]["snapshot_mismatch"] == 1
    assert result["exclusions"]["unverified"] == 1
    assert result["exclusions"]["refund_cancelled_or_conflict"] == 1


def test_post_cutoff_and_wrong_stake_are_excluded_not_marked_losses():
    payload = make_example()
    payload["forecast_races"][0]["frozen_at_utc"] = "2026-10-22T06:00:00+00:00"
    payload["forecast_races"][1]["bets"][0]["virtual_yen"] = 13000
    report = analyze(payload)
    assert report["metrics"]["verified_races"] == 2
    assert report["exclusions"]["post_cutoff_snapshot"] == 1
    assert report["exclusions"]["budget_mismatch"] == 1


def test_read_only_does_not_mutate_inputs_or_fixed_picks():
    payload = make_example()
    original = deepcopy(payload)
    analyze(payload)
    assert payload == original
