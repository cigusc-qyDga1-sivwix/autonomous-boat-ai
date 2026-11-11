"""Forward-only official reconciliation for hidden 1M alternative tickets."""
from copy import deepcopy
from scripts.hidden_path_shadow import analyze as detect
from scripts.forecast_audit import _hidden_path_forward_report
from tests.test_hidden_path_shadow import source, FROZEN, CUTOFF

DAY = "2026-11-12"

def setup():
    bets, scores, racers = source()
    hidden = detect(bets, scores, racers, phase="exhibition",
                    exhibition_verified=True, frozen_at_utc=FROZEN,
                    cutoff_at_utc=CUTOFF)
    assert hidden["status"] == "PRE_CUTOFF_SHADOW_SWAP_ONLY"
    hidden["formal_bets_sha256"] = "b"*64
    hidden["ranked_source_sha256"] = "c"*64
    snapshot = {"venue": "三国", "race": 4, "phase": "exhibition",
                "ticket_status": "formal", "cutoff_jst": "10:30",
                "frozen_at_utc": FROZEN, "sha256": "a"*64,
                "model_version": "four-factor-v2.5-evidence-head-switch-untrained",
                "bets": bets, "hidden_path_shadow": hidden}
    official = {f"{DAY}|三国|4": {
        "verified": True, "source": "boatrace_official_pay",
        "snapshot_sha256": snapshot["sha256"], "virtual_stake": 50000,
        "finish": hidden["replacement_candidate"], "payout_per_100": 20000}}
    return snapshot, official

def test_matched_hidden_candidate_recovers_missed_head_and_hit():
    snap, paid = setup()
    report = _hidden_path_forward_report([snap], paid, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 1
    assert report["formal"]["hits"] == 0
    assert report["research_shadow"]["hits"] == 1
    assert report["head_misses_recovered"] == 1
    assert report["new_head_misses"] == 0
    assert report["research_shadow"]["virtual_stake_yen"] == 50000
    assert report["not_formal_performance"]
    assert report["by_scenario"]["OUTER_ATTACK_FOLLOWER"]["research_shadow"]["hits"] == 1

def test_rejects_retrospective_or_unmatched_controls():
    snap, paid = setup()
    late = deepcopy(snap)
    late["hidden_path_shadow"]["frozen_at_utc"] = "2026-11-12T03:00:00Z"
    report = _hidden_path_forward_report([late], paid, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["exclusions"]["invalid_or_unmatched_pre_cutoff_control"] == 1
    changed = deepcopy(snap)
    changed["hidden_path_shadow"]["formal_control_bets"][0]["combination"] = "4-5-1"
    report = _hidden_path_forward_report([changed], paid, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["exclusions"]["invalid_or_unmatched_pre_cutoff_control"] == 1

def test_unverified_and_conflicted_not_losses():
    snap, paid = setup()
    unverified = deepcopy(paid)
    unverified[f"{DAY}|三国|4"]["verified"] = False
    report = _hidden_path_forward_report([snap], unverified, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["formal"]["verified_races"] == 0
    report = _hidden_path_forward_report([snap], paid, {f"{DAY}|三国|4": "review"}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["exclusions"]["official_refund_or_conflict"] == 1
