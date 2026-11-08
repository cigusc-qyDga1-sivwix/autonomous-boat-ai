"""Formal v2.3 activates only prospectively; v2.2 old archives immutable."""
from copy import deepcopy
from datetime import datetime
from itertools import permutations

import pytest
from scripts import autonomous_daily as A
from scripts.conditional_second_primary import diversify
from tests.test_four_factor_main import race

VERSION = A.CONDITIONAL_SECOND_MAIN_MODEL
DAY = "2026-11-09"
NOW = datetime.fromisoformat(DAY + "T09:20:00+09:00")


def candidate_rows():
    names = ["-".join(map(str, p)) for p in permutations(range(1, 7), 3)]
    chosen = ["1-2-3", "1-2-4", "1-2-5", "1-2-6", "1-3-2", "1-3-4",
              "2-1-3", "3-1-2"]
    strength = dict(zip(chosen, (1.0, .99, .98, .97, .96, .95, .92, .91)))
    return [{"combination": x, "relative_score": strength.get(x, .001)}
            for x in names]


def test_evidence_supported_second_pair_diversity_without_point_expansion():
    rows = candidate_rows()
    original = sorted(rows, key=lambda x: (-x["relative_score"], x["combination"]))[:6]
    reasons = {x["combination"]: {
        "basis": ("MINIMUM_MODEL_RANK_ONLY_NOT_OBSERVED_EVIDENCE" if i < 4
                  else "VERIFIED_EXHIBITION_AND_SUPPORTED_PAIR"),
        "path_labels": [], "relative_score_vs_top": round(x["relative_score"], 4)}
        for i, x in enumerate(original)}
    paths = [{"scenario": "head2_path", "top_3": [
        ["2-1-3", .1], ["2-1-4", .1], ["2-1-5", .1]]}]
    selected, new_reasons, metadata = diversify(original, rows, {
        "ticket_reasons": reasons}, paths)
    assert len(selected) == len(original) == 6
    assert {x["combination"] for x in selected[:4]} == {
        x["combination"] for x in original[:4]}
    assert "2-1-3" in {x["combination"] for x in selected}
    assert metadata["pair_coverage_after"] > metadata["pair_coverage_before"]
    assert metadata["formal_tickets_changed"]
    assert set(new_reasons) == {x["combination"] for x in selected}
    assert metadata["same_point_count"] and not metadata["historical_results_used"]


def test_no_unsupported_pair_or_score_spreading():
    rows = candidate_rows()
    original = sorted(rows, key=lambda x: (-x["relative_score"], x["combination"]))[:6]
    reasons = {x["combination"]: {
        "basis": ("MINIMUM_MODEL_RANK_ONLY_NOT_OBSERVED_EVIDENCE" if i < 4
                  else "VERIFIED_EXHIBITION_AND_SUPPORTED_PAIR")}
        for i, x in enumerate(original)}
    selected, _, meta = diversify(original, rows, {"ticket_reasons": reasons}, [])
    assert selected == original
    assert meta["status"] == "NO_ELIGIBLE_SWAP"
    with pytest.raises(ValueError, match="missing_v22_ticket_reasons"):
        diversify(original, rows, {"ticket_reasons": {}}, [])


def test_v23_is_real_main_and_v22_remains_before_activation():
    test_input = race(DAY)
    old = A.prediction(race("2026-11-08"), "徳山", 1, "exhibition",
                       datetime.fromisoformat("2026-11-08T09:20:00+09:00"), "fixture")
    latest = A.prediction(test_input, "徳山", 1, "exhibition", NOW, "fixture")
    assert old["model_version"] == A.LINKED_MAIN_MODEL
    assert "conditional_second_primary" not in old["interaction_primary"]
    assert latest["model_version"] == VERSION
    assert latest["model_role"] == "main"
    meta = latest["interaction_primary"]
    assert meta["conditional_second_primary"]["enabled"] is True
    assert meta["conditional_second_primary"]["same_point_count"]
    assert len(meta["same_race_v22_control_bets"]) == len(latest["bets"])
    assert sum(x["virtual_yen"] for x in latest["bets"]) == 50000
    assert sum(x["virtual_yen"] for x in meta["same_race_v22_control_bets"]) == 50000
    assert set(meta["point_policy"]["ticket_reasons"]) == {
        b["combination"] for b in latest["bets"]}
    assert latest["sha256"] == A.stable_hash({
        k: v for k, v in latest.items() if k != "sha256"})
    unchanged = deepcopy(test_input)
    unchanged["result"] = {"finish": "6-5-4", "payout_per_100": 999999}
    assert A.prediction(unchanged, "徳山", 1, "exhibition", NOW, "fixture")["bets"] == latest["bets"]


def test_v23_pre_cutoff_upgrade_is_append_only_and_no_late_prediction():
    r = race(DAY)
    src = {"programs": {"stadiums": {"18": {"races": {"1": r}}}}}
    before = datetime.fromisoformat("2026-11-09T00:00:00+09:00")
    ledger, _, _ = A.build(None, src, before, "fixture")
    already = deepcopy(ledger["race_records"]["18-1"]["versions"])
    assert all(x["model_version"] == A.CONDITIONAL_SECOND_MAIN_MODEL for x in already)
    again, view, _ = A.build(ledger, src, NOW, "fixture")
    assert again["race_records"]["18-1"]["versions"][:len(already)] == already
    assert view["forecast_races"][0]["model_version"] == VERSION
    closed, _, _ = A.build(again, src,
                           datetime.fromisoformat("2026-11-09T10:10:00+09:00"), "fixture")
    assert closed["race_records"]["18-1"]["versions"] == again["race_records"]["18-1"]["versions"]
