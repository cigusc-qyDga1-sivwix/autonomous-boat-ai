"""Prospective two/three-head challenger: zero formal mutation and no hindsight."""
from copy import deepcopy
from itertools import permutations

from scripts.inner_23_head_challenger_shadow import evaluate, VERSION
from boat_ai.statistical import allocate


def fixture():
    racers = [
        {"lane": i, "course": i, "national_win_rate": 5.0,
         "motor_top_2_percent": 30.0, "average_start_timing": .17,
         "average_start_timing_imputed": False, "exhibition_time": 6.85,
         "exhibition_st": .15}
        for i in range(1, 7)
    ]
    racers[0].update(average_start_timing=.19, exhibition_st=.17,
                     exhibition_time=6.85)
    ranked = [{"combination": "-".join(map(str, p)), "score": 1/120}
              for p in permutations(range(1,7),3)]
    ranked.sort(key=lambda x: (-x["score"], x["combination"]))
    formal = allocate(ranked, 12, max_points=20)
    snapshot = {
        "venue": "徳山", "race": 1, "phase": "exhibition",
        "frozen_at_utc": "2026-11-19T01:00:00+00:00",
        "cutoff_iso_jst": "2026-11-19T10:30:00+09:00",
        "exhibition_origin": {"captured_before_cutoff": True},
        "exhibition_input_check": {"verified_before_freeze": True,
                                   "six_boats_matched": 6},
        "racers": racers,
    }
    return snapshot, ranked, formal


def test_lane_two_head_competes_only_with_independent_evidence():
    s, ranked, main = fixture()
    s["racers"][1].update(
        average_start_timing=.12, exhibition_st=.09, exhibition_time=6.75,
        motor_top_2_percent=43.0)
    untouched = deepcopy((s, ranked, main))
    result = evaluate(s, ranked, main)
    assert result["status"] == "QUALIFIED_FORWARD_SHADOW"
    assert result["version"] == VERSION
    assert result["qualified"][0]["lane"] == 2
    assert result["formal_top_head"] == 1
    assert result["trial_top_head"] == 2
    assert len(result["trial_bets"]) == len(main)
    assert sum(x["virtual_yen"] for x in result["trial_bets"]) == 50000
    assert result["trial_head_mass"]["2"] > result["before_head_mass"]["2"]
    assert result["formal_tickets_changed"] is False
    assert result["result_data_used"] is False
    assert (s, ranked, main) == untouched


def test_lane_three_and_actual_course_restriction():
    s, ranked, main = fixture()
    s["racers"][2].update(
        average_start_timing=.11, exhibition_st=.07, exhibition_time=6.72)
    out = evaluate(s, ranked, main)
    assert out["qualified"][0]["lane"] == 3
    assert out["trial_top_head"] == 3
    s["racers"][2]["course"], s["racers"][3]["course"] = 4, 3
    assert evaluate(s, ranked, main)["status"] == "NO_QUALIFIED_2_3_HEAD_CHALLENGER"


def test_no_unconditional_reweighting_or_missing_source():
    s, ranked, main = fixture()
    assert evaluate(s, ranked, main)["status"] == "NO_QUALIFIED_2_3_HEAD_CHALLENGER"
    s["exhibition_origin"]["captured_before_cutoff"] = False
    assert evaluate(s, ranked, main)["status"] == "SIX_BOAT_SOURCE_NOT_VERIFIED"
    s["exhibition_origin"]["captured_before_cutoff"] = True
    s["frozen_at_utc"] = "2026-11-19T01:29:00+00:00"
    assert evaluate(s, ranked, main)["status"] == "NOT_SAFELY_FROZEN"


def test_no_postrace_label_leakage():
    s, ranked, main = fixture()
    s["racers"][1].update(average_start_timing=.11, exhibition_st=.07,
                          exhibition_time=6.7)
    before = evaluate(s, ranked, main)
    s.update(result={"finish": "2-1-3"}, payout=999999,
             actual_start={"1": 0.55}, odds={"2-1-3": 1000})
    assert evaluate(s, ranked, main) == before


def test_strong_inside_is_not_forcibly_replaced():
    s, ranked, main = fixture()
    s["racers"][1].update(average_start_timing=.11, exhibition_st=.07,
                          exhibition_time=6.7)
    adjusted = [
        {"combination": r["combination"],
         "score": 80.0 if r["combination"].startswith("1-") else 1.0}
        for r in ranked
    ]
    norm = sum(x["score"] for x in adjusted)
    adjusted = sorted(
        [{"combination": r["combination"], "score": r["score"] / norm}
         for r in adjusted],
        key=lambda x: (-x["score"], x["combination"]))
    old = allocate(adjusted, 12, max_points=20)
    out = evaluate(s, adjusted, old)
    assert out["status"] == "QUALIFIED_FORWARD_SHADOW"
    assert out["trial_top_head"] == 1


def test_builder_recomputes_only_after_proof_and_parent_sha():
    from boat_ai.statistical import SCHEMA, FEATURES, digest
    from scripts.inner_23_head_challenger_shadow import build
    s, _, main = fixture()
    s["racers"][1].update(average_start_timing=.10, exhibition_st=.08,
                          exhibition_time=6.70, motor_top_2_percent=45.0)
    model = {"schema": SCHEMA, "features": FEATURES,
             "weights": [[0.0]*len(FEATURES) for _ in range(3)]}
    model["model_sha256"] = digest(model)
    s["bets"] = main
    s["learned_formal"] = {"model_sha256": model["model_sha256"]}
    out = build(s, model)
    assert out["status"] == "QUALIFIED_FORWARD_SHADOW"
    assert out["parent_model_sha256"] == model["model_sha256"]
    assert out["source_formal_bets_sha256"] == digest(main)
    assert out["trial_top_head"] == 2
    assert build(s, dict(model, model_sha256="0"*64))["status"] == "MODEL_SHA_MISMATCH"
