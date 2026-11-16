"""Evidence-first regression tests: frozen baseline vs final exhibition similarity."""
from copy import deepcopy

from scripts.autonomous_daily import exhibition_similarity_audit, LEARNED_MAIN_MODEL

def bet(combo, yen=50000):
    return [{"combination": combo, "virtual_yen": yen}]

def row(venue, race, model, new_combo, *, formal=True, metrics=("turn_time", "lap_time", "straight_time")):
    return {
        "venue": venue, "race": race, "phase": "exhibition",
        "ticket_status": "formal" if formal else "provisional",
        "model_version": model, "bets": bet(new_combo),
        "learned_formal": {"model_sha256": "frozen-model-sha"},
        "exhibition_input_check": {
            "verified_before_freeze": True, "six_boats_matched": 6,
            "original_metrics_matched": list(metrics),
        },
    }

def record(venue, race, model, base, *, old_model=None):
    return {"venue":venue, "race":race,
            "versions": [{"phase":"baseline", "model_version":old_model or model,
                          "learned_formal": {"model_sha256": "frozen-model-sha"},
                          "bets":bet(base)}]}

def test_true_frozen_same_model_comparison_and_coverage():
    records={
      "a":record("徳山",1,LEARNED_MAIN_MODEL,"1-2-3"),
      "b":record("児島",2,LEARNED_MAIN_MODEL,"1-2-3"),
      "c":record("唐津",3,LEARNED_MAIN_MODEL,"1-2-3",
                 old_model="old-heuristic"),
      "d":record("丸亀",4,LEARNED_MAIN_MODEL,"1-2-3"),
    }
    views=[
      row("徳山",1,LEARNED_MAIN_MODEL,"1-2-3"),
      row("児島",2,LEARNED_MAIN_MODEL,"1-3-2",metrics=("turn_time",)),
      row("唐津",3,LEARNED_MAIN_MODEL,"4-2-1"),
      row("丸亀",4,LEARNED_MAIN_MODEL,"4-2-1",formal=False),
    ]
    before=deepcopy((records,views))
    s=exhibition_similarity_audit(records,views)
    assert s["formal_exhibition_races"] == 3
    assert s["same_model_baseline_pairs"] == 2
    assert s["different_model_baseline_pairs"] == 1
    assert s["same_model_identical_tickets_and_stakes"] == 1
    assert s["same_model_different_tickets_or_stakes"] == 1
    assert s["same_model_unchanged_ticket_share"] == .5
    assert s["same_model_identical_first_head"] == 2
    assert s["six_boat_turn_metric_available"] == 3
    assert s["six_boat_lap_metric_available"] == 2
    assert s["six_boat_straight_metric_available"] == 2
    assert s["same_model_learned_pairs"] == 2
    assert s["learned_primary_uses_original_turn_lap_straight_features"] is False
    assert (records,views) == before

def test_missing_baseline_or_invalid_bets_not_mislabeled_identical():
    rows=[row("徳山",1,LEARNED_MAIN_MODEL,"1-2-3")]
    records={"1":{"venue":"徳山", "race":1,"versions":[{"phase":"exhibition"}]}}
    s=exhibition_similarity_audit(records,rows)
    assert s["formal_exhibition_races"] == 1
    assert s["with_baseline_snapshot"] == 0
    assert s["same_model_unchanged_ticket_share"] is None
    assert s["sampled_frozen_pairs"] == []
    records={"1":record("徳山",1,LEARNED_MAIN_MODEL,"1-2-3")}
    records["1"]["versions"][0]["bets"][0]["virtual_yen"] = "invalid"
    s=exhibition_similarity_audit(records,rows)
    assert s["same_model_baseline_pairs"] == 0
    assert s["same_model_identical_tickets_and_stakes"] == 0

def test_report_emitted_in_compact_forecast_sync_and_not_result_inputs():
    from pathlib import Path
    code=Path("scripts/autonomous_daily.py").read_text(encoding="utf-8")
    assert 'similarity = exhibition_similarity_audit(records, latest_races)' in code
    assert '"exhibition_similarity_audit": similarity' in code
    assert '"exhibition_similarity_audit": webapp["exhibition_similarity_audit"]' in code
    assert 'learned_primary_uses_original_turn_lap_straight_features' in code

def test_changed_learning_weights_not_attributed_to_exhibition():
    r = record("徳山", 1, LEARNED_MAIN_MODEL, "1-2-3")
    r["versions"][0]["learned_formal"]["model_sha256"] = "previous-model"
    snap = row("徳山", 1, LEARNED_MAIN_MODEL, "1-4-5")
    audit = exhibition_similarity_audit({"18-1": r}, [snap])
    assert audit["with_baseline_snapshot"] == 1
    assert audit["different_model_baseline_pairs"] == 1
    assert audit["same_model_baseline_pairs"] == 0
    assert audit["same_model_unchanged_ticket_share"] is None
