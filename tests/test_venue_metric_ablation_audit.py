"""Official-verified, fixed-before-cutoff, equal-point venue shadow A/B only."""
from copy import deepcopy

from scripts.forecast_audit import analyze
from test_forecast_audit import BETS, make_example


def prospect():
    payload = make_example()
    row = payload["forecast_races"][0]
    row["phase"] = "exhibition"
    row["ticket_status"] = "formal"
    trial = deepcopy(BETS)
    # Remove the true winning ticket, preserving same point count / virtual 50k.
    without = deepcopy(trial)
    without[0]["combination"] = "4-2-3"
    shadow = {
        "status": "ready",
        "not_formal": True,
        "result_data_used": False,
        "frozen_at_utc": row["frozen_at_utc"],
        "metric_ablation_protocol": "venue-shadow-v0.2-one-metric-removed",
        "metric_coverage": ["lap_time", "turn_time"],
        "trial_bets": trial,
        "metric_ablations": [{
            "metric": "lap_time", "status": "ready", "bets": without,
            "same_point_count": True, "same_virtual_budget": True,
            "frozen_at_utc": row["frozen_at_utc"],
            "not_formal": True, "actual_results_used": False,
        }]
    }
    row["venue_motor_exhibition_shadow"] = shadow
    return payload


def test_official_one_pair_scores_only_shadow_variants():
    sample = prospect()
    original = deepcopy(sample)
    report = analyze(sample)
    assert sample == original
    a = report["venue_metric_ablation"]
    assert a["generated_races_in_latest_snapshot"] == 1
    assert a["verified_full_shadow_races"] == 1
    assert a["shadow_only_not_formal"] is True
    metric = a["per_metric"]["lap_time"]
    assert metric["matched_verified_races"] == 1
    assert metric["with_metric"]["hits"] == 1
    assert metric["without_metric"]["hits"] == 0
    assert metric["with_metric"]["virtual_payout_yen"] == 120000
    assert metric["without_metric"]["virtual_payout_yen"] == 0
    assert metric["by_venue"]["徳山"]["matched_verified_races"] == 1
    assert report["metrics"]["hits"] == 1  # formal comparison unaffected


def test_no_official_result_or_wrong_sha_is_never_counted():
    for change in ("unverified", "sha", "refund", "late"):
        sample = prospect()
        daykey = "2026-10-22|徳山|1"
        if change == "unverified":
            sample["official_results"][daykey]["verified"] = False
        elif change == "sha":
            sample["official_results"][daykey]["snapshot_sha256"] = "other"
        elif change == "refund":
            sample["settlement_alerts"][daykey] = {"status": "review"}
        else:
            sample["forecast_races"][0]["frozen_at_utc"] = "2026-10-22T06:00:00+00:00"
        audit = analyze(sample)["venue_metric_ablation"]
        assert audit["per_metric"] == {}, change


def test_point_mismatch_and_missing_metrics_excluded_not_losses():
    sample = prospect()
    row = sample["forecast_races"][0]
    pair = row["venue_motor_exhibition_shadow"]["metric_ablations"][0]
    pair["same_point_count"] = False
    result = analyze(sample)["venue_metric_ablation"]
    assert result["per_metric"] == {}
    assert result["exclusions"]["point_count_mismatch"] == 1
    pair["same_point_count"] = True
    pair["metric"] = "straight_time"  # Not measured in this frozen cohort
    result = analyze(sample)["venue_metric_ablation"]
    assert result["per_metric"] == {}
    assert result["exclusions"]["invalid_or_duplicate_metric"] == 1


def test_tampered_or_late_counterfactual_rejected():
    for key, value in (
        ("actual_results_used", True),
        ("frozen_at_utc", "2026-10-23T03:00:00+00:00"),
        ("same_virtual_budget", False),
    ):
        payload = prospect()
        payload["forecast_races"][0]["venue_motor_exhibition_shadow"]["metric_ablations"][0][key] = value
        result = analyze(payload)["venue_metric_ablation"]
        assert result["per_metric"] == {}
        assert result["exclusions"]["invalid_or_unavailable_variant"] == 1
