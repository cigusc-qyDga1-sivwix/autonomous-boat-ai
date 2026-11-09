"""Only pre-cutoff frozen v2.2 controls may be compared to v2.3 formal picks."""
from copy import deepcopy

from scripts.forecast_audit import analyze, _v22_control_bets
from tests.test_forecast_audit import BETS, make_example

MODEL = "four-factor-v2.3-conditional-second-primary-untrained"


def fixture():
    p = make_example()
    p["event_date"] = "2026-11-09"
    p["official_results"] = {
        k.replace("2026-10-22", "2026-11-09"): v
        for k, v in p["official_results"].items()
    }
    for race in p["forecast_races"]:
        race["frozen_at_utc"] = "2026-11-09T03:00:00+00:00"
        race["model_version"] = MODEL
        race["ticket_status"] = "formal"
        race["phase"] = "exhibition"
        race["interaction_primary"] = {
            "conditional_second_primary": {
                "enabled": True, "same_point_count": True,
                "historical_results_used": False,
            },
            "same_race_v22_control_bets": deepcopy(BETS),
        }
    return p


def test_v23_v22_matched_control_does_not_change_formal_performance():
    p = fixture()
    # The independent v2.2 baseline would win 1-2-3; the main v2.3 does not.
    v23_bets = p["forecast_races"][0]["bets"]
    v23_bets[0]["combination"] = "4-2-3"
    before = deepcopy(p)
    audit = analyze(p)
    comparison = audit["same_race_v23_v22_control"]
    assert comparison["matched_races"] == 4
    assert comparison["invalid_or_missing_frozen_controls"] == 0
    assert comparison["formal_v23"]["hits"] == 0
    assert comparison["frozen_v22_control"]["hits"] == 1
    assert comparison["changed_ticket_or_allocation_races"] == 1
    assert audit["metrics"]["hits"] == 0
    assert comparison["not_formal_performance"]
    assert p == before


def test_no_reconstruction_for_missing_control_or_unverified_official():
    p = fixture()
    del p["forecast_races"][0]["interaction_primary"]["same_race_v22_control_bets"]
    p["official_results"]["2026-11-09|徳山|2"]["verified"] = False
    result = analyze(p)
    assert result["same_race_v23_v22_control"]["matched_races"] == 2
    assert result["same_race_v23_v22_control"]["invalid_or_missing_frozen_controls"] == 1
    assert result["exclusions"]["unverified"] == 1


def test_control_fail_closed_for_wrong_stake_or_data_leak():
    p = fixture()
    row = p["forecast_races"][0]
    row["interaction_primary"]["same_race_v22_control_bets"][0]["virtual_yen"] += 1000
    assert _v22_control_bets(row) is None
    row["interaction_primary"]["same_race_v22_control_bets"] = deepcopy(BETS)
    row["interaction_primary"]["conditional_second_primary"]["historical_results_used"] = True
    assert _v22_control_bets(row) is None
    row["interaction_primary"]["conditional_second_primary"]["historical_results_used"] = False
    row["interaction_primary"]["same_race_v22_control_bets"][0]["combination"] = "1-1-3"
    assert _v22_control_bets(row) is None
