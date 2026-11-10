"""True formal-v2.3 prospective 3-leg comparison: official results only."""
from copy import deepcopy
from scripts.forecast_audit import analyze
from test_forecast_audit import make_example, BETS

def fixture():
    payload=make_example()
    row=payload["forecast_races"][0]
    row.update(model_version="four-factor-v2.3-conditional-second-primary-untrained",
               phase="exhibition",ticket_status="formal")
    prior=deepcopy(BETS)
    prior[0]["combination"]="4-2-3"
    row["three_leg_primary"]={
        "version":"three-leg-formal-redistribution-v0.1-untrained",
        "status":"applied", "applied":True, "formal_component":True,
        "result_data_used":False, "pre_cutoff_only":True,
        "source_exhibition_weight_unchanged":True,
        "same_input_prior_v23_control":True,
        "control_no_postrace_data":True,
        "no_additional_stake":True,
        "control_frozen_at_utc":row["frozen_at_utc"],
        "frozen_at_utc":row["frozen_at_utc"],
        "same_point_count":True,
        "actual_ticket_or_allocation_changed":True,
        "control_bets":prior,
    }
    return payload

def test_matched_verification_scored_from_immutable_control():
    payload=fixture()
    original=deepcopy(payload)
    report=analyze(payload)
    audit=report["three_leg_primary_comparison"]
    assert payload==original
    assert audit["generated_pre_cutoff_latest_snapshots"]==1
    assert audit["formal_adjusted_races"]==1
    assert audit["official_verified_equal_point_pairs"]==1
    assert audit["formal_three_leg"]["hits"]==1
    assert audit["same_input_unmodified_v23"]["hits"]==0
    assert audit["formal_three_leg"]["virtual_payout_yen"]==120000
    assert audit["same_input_unmodified_v23"]["virtual_payout_yen"]==0
    assert audit["by_venue"]["徳山"]["formal_three_leg"]["hits"]==1
    assert audit["formal_three_leg"]["virtual_stake_yen"]==50000
    assert report["metrics"]["virtual_stake_yen"]==4*50000 # A/B not formal stake.

def test_missing_official_result_wrong_source_and_refund_all_excluded():
    for issue in ("missing_result","wrong_sha","refund","late","future_control",
                  "wrong_points","tamper_control"):
        payload=fixture()
        row=payload["forecast_races"][0]
        key="2026-10-22|徳山|1"
        if issue=="missing_result":payload["official_results"][key]["verified"]=False
        if issue=="wrong_sha":payload["official_results"][key]["snapshot_sha256"]="wrong"
        if issue=="refund":payload["settlement_alerts"][key]={"status":"review"}
        if issue=="late":row["frozen_at_utc"]="2026-10-22T07:00:00+00:00"
        if issue=="future_control":row["three_leg_primary"]["control_frozen_at_utc"]="2026-10-23T01:00:00+00:00"
        if issue=="wrong_points":row["three_leg_primary"]["same_point_count"]=False
        if issue=="tamper_control":row["three_leg_primary"]["control_bets"][0]["virtual_yen"]=13000
        audit=analyze(payload)["three_leg_primary_comparison"]
        assert audit["official_verified_equal_point_pairs"]==0,issue
        assert audit["formal_three_leg"]["hits"]==0,issue
        assert audit["exclusions"],issue
