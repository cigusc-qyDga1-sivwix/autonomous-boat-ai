"""Official-only matched evaluation of new immutable research shadow."""
from copy import deepcopy

from scripts import autonomous_daily as A
from scripts.coverage_reselection_shadow import review
from scripts.forecast_audit import analyze
from tests.test_coverage_reselection_shadow import fixture


def dataset():
    bets, ranked, diagnostic, scenarios, policy = fixture()
    shadow = review(bets, ranked, diagnostic, scenarios, policy,
                    phase="exhibition", exhibition_verified=True)
    freeze = "2026-11-11T00:30:00+00:00"
    shadow["frozen_at_utc"] = freeze
    shadow["formal_bets_sha256"] = A.stable_hash({"bets": bets})
    forecast = {
        "venue": "徳山", "race": 1, "classification": "WATCH",
        "ticket_status": "formal", "phase": "exhibition",
        "cutoff_jst": "10:00", "frozen_at_utc": freeze,
        "sha256": "frozen-11-11-1",
        "model_version": A.CONDITIONAL_SECOND_MAIN_MODEL,
        "bets": bets, "coverage_reselection_shadow": shadow,
        "interaction_primary": {
            "ranked_outcomes": ranked, "scenario_assumptions": scenarios,
        }
    }
    return {
        "event_date": "2026-11-11",
        "forecast_races": [forecast], "listed_races": 1,
        "official_results": {"2026-11-11|徳山|1": {
            "verified": True, "source": "boatrace_official_pay",
            "snapshot_sha256": forecast["sha256"], "finish": "5-3-1",
            "payout_per_100": 5000, "virtual_stake": 50000,
        }},
        "settlement_alerts": {},
    }


def test_future_official_matched_pair_compares_without_changing_formal():
    source = dataset()
    original = deepcopy(source)
    audit = analyze(source)["coverage_reselection_forward_comparison"]
    assert audit["frozen_proposals"] == 1
    assert audit["official_verified_sha_matched_pairs"] == 1
    assert audit["formal_v23"]["hits"] == 0
    assert audit["research_shadow"]["hits"] == 1
    assert audit["research_shadow"]["virtual_stake_yen"] == 50000
    assert audit["formal_v23"]["virtual_stake_yen"] == 50000
    assert audit["by_venue"]["徳山"]["research_shadow"]["hits"] == 1
    assert audit["by_coverage_kind"]["uncovered_second_pair"]["formal"]["hits"] == 0
    assert audit["not_formal_performance"]
    assert source == original


def test_unverified_official_and_pre_cutoff_input_mismatch_do_not_count():
    source = dataset()
    source["official_results"]["2026-11-11|徳山|1"]["verified"] = False
    trial = analyze(source)["coverage_reselection_forward_comparison"]
    assert trial["official_verified_sha_matched_pairs"] == 0
    assert trial["exclusions"]["official_unverified"] == 1
    source = dataset()
    source["forecast_races"][0]["interaction_primary"]["ranked_outcomes"][0]["relative_score"] *= 2
    trial = analyze(source)["coverage_reselection_forward_comparison"]
    assert trial["official_verified_sha_matched_pairs"] == 0
    assert trial["exclusions"]["input_sha_mismatch"] == 1
    source = dataset()
    source["forecast_races"][0]["coverage_reselection_shadow"]["frozen_at_utc"] = "2026-11-11T03:30:00+00:00"
    trial = analyze(source)["coverage_reselection_forward_comparison"]
    assert trial["official_verified_sha_matched_pairs"] == 0
    assert trial["exclusions"]["invalid_pre_cutoff_provenance"] == 1
