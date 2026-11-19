"""Pro-style portfolio structure is a strictly forward-only research shadow."""
from copy import deepcopy
from itertools import permutations

import pytest

from boat_ai.statistical import SCHEMA, FEATURES, digest
from scripts.expert_scenario_portfolio_shadow import build
from scripts.learned_formal import apply as learned_apply

FROZEN = "2026-11-20T01:45:00+00:00"
CUTOFF = "2026-11-20T12:00:00+09:00"


def racers():
    return [{
        "lane": i, "course": i, "name": "選手" + str(i),
        "national_win_rate": 5.0, "motor_top_2_percent": 30,
        "average_start_timing": .16, "average_start_timing_imputed": False,
        "exhibition_time": 6.85, "exhibition_st": .16,
    } for i in range(1, 7)]


def model():
    m = {
        "schema": SCHEMA, "features": FEATURES,
        "role": "research_shadow", "calibrated": False,
        "weights": [[0.0] * len(FEATURES) for _ in range(3)],
        "created_at_utc": "2026-11-19T02:00:00+00:00",
        "trained_through": "2026-11-18", "training_n": 3928,
    }
    m["model_sha256"] = digest(m)
    return m


def source():
    combos = ["-".join(map(str, x)) for x in permutations(range(1, 7), 3)]
    mass = {1: .50, 2: .23, 3: .14, 4: .07, 5: .04, 6: .02}
    ranked = [{"combination": c, "score": mass[int(c[0])] / 20}
              for c in combos]
    ranked.sort(key=lambda x: (-x["score"], x["combination"]))
    bets = [
        {"combination": x["combination"], "virtual_yen": 6000} for x in ranked[:7]
    ] + [{"combination": ranked[7]["combination"], "virtual_yen": 8000}]
    assert sum(x["virtual_yen"] for x in bets) == 50000
    snap = {
        "phase": "exhibition", "frozen_at_utc": FROZEN,
        "cutoff_iso_jst": CUTOFF, "cutoff_jst": "12:00",
        "venue": "徳山", "race": 1,
        "exhibition_origin": {"captured_before_cutoff": True},
        "racers": racers(), "bets": bets,
    }
    return snap, ranked


def test_true_two_path_structure_and_control_is_unchanged():
    snap, ranked = source()
    old = deepcopy((snap, ranked))
    trial = build(snap, ranked)
    assert trial["status"] == "PRE_CUTOFF_COUNTER_PATH_FROZEN"
    assert trial["main_head_lane"] == 1
    assert trial["counter_head_lane"] == 2
    assert trial["main_head_actual_course"] == 1
    assert trial["counter_head_actual_course"] == 2
    heads = {b["combination"][0] for b in trial["alternative_bets"]}
    assert heads == {"1", "2"}
    assert trial["main_ticket_count"] + trial["counter_ticket_count"] == 8
    assert sum(x["virtual_yen"] for x in trial["alternative_bets"]) == 50000
    assert len(trial["alternative_bets"]) == len(snap["bets"])
    assert trial["ticket_or_allocation_changed"]
    assert trial["head_set_changed"] is True
    assert trial["not_formal"] and trial["bets_modified"] is False
    assert trial["no_odds_used"] and trial["no_results_used"]
    assert trial["control_bets_sha256"] == digest(snap["bets"])
    assert trial["alternative_bets_sha256"] == digest(trial["alternative_bets"])
    assert (snap, ranked) == old


def test_actual_course_mapped_and_no_evidence_falls_closed():
    snap, ranked = source()
    snap["racers"][0]["course"], snap["racers"][1]["course"] = 2, 1
    assert build(snap, ranked)["counter_head_actual_course"] == 1
    snap["exhibition_origin"]["captured_before_cutoff"] = False
    assert build(snap, ranked) is None
    snap["exhibition_origin"]["captured_before_cutoff"] = True
    snap["racers"][3]["course"] = 1
    with pytest.raises(ValueError, match="duplicate"):
        build(snap, ranked)


def test_postrace_and_late_inputs_rejected():
    snap, ranked = source()
    snap["actual_finish"] = "1-2-3"
    with pytest.raises(ValueError, match="outcome"):
        build(snap, ranked)
    snap, ranked = source()
    snap["frozen_at_utc"] = "2026-11-20T02:59:00+00:00"
    with pytest.raises(ValueError, match="postcutoff"):
        build(snap, ranked)
    snap, ranked = source()
    snap["cutoff_iso_jst"] = "2026-11-19T12:00:00+09:00"
    assert build(snap, ranked) is None


def test_suppressed_if_counter_head_has_tiny_mass():
    snap, ranked = source()
    scores = {1: .99, 2: .004, 3: .003, 4: .0015, 5: .001, 6: .0005}
    for row in ranked:
        row["score"] = scores[int(row["combination"][0])] / 20
    assert build(snap, ranked)["status"] == "COUNTER_HEAD_UNSUPPORTED"


def test_learned_primary_preserves_formal_when_research_study_created():
    snap, _ = source()
    snap.update({
        "model_version": "four-factor-v2.6-evidence-conditional-pairs-untrained",
        "classification": "WATCH", "model_role": "main",
        "weather_used": {"wind_speed": 1, "wave_height": 2},
        "point_count": 8,
    })
    before = deepcopy(snap)
    out = learned_apply(snap, model())
    trial = out["expert_scenario_portfolio_shadow"]
    assert trial["not_formal"]
    assert trial["control_bets"] == out["bets"]
    assert trial["bets_modified"] is False
    assert out["model_role"] == "main"
    assert out["classification"] == "WATCH"
    assert sum(x["virtual_yen"] for x in out["bets"]) == 50000
    assert snap == before


def test_study_audit_official_only_and_sha_bound():
    from scripts.forecast_audit import _expert_scenario_portfolio_report
    snap, ranked = source()
    snap["expert_scenario_portfolio_shadow"] = build(snap, ranked)
    snap.update({
        "model_version": "four-factor-learned-v1-conditional-choice-trained",
        "ticket_status": "formal",
        "exhibition_input_check": {"verified_before_freeze": True, "six_boats_matched": 6},
    })
    snap["sha256"] = digest({k: v for k, v in snap.items() if k != "sha256"})
    key = "2026-11-20|徳山|1"
    found = snap["expert_scenario_portfolio_shadow"]["alternative_bets"][-1]["combination"]
    official = {key: {
        "verified": True, "source": "boatrace_official_pay",
        "virtual_stake": 50000, "snapshot_sha256": snap["sha256"],
        "finish": found, "payout_per_100": 5000,
    }}
    report = _expert_scenario_portfolio_report([snap], official, {}, "2026-11-20")
    assert report["matched_races"] == 1
    assert report["changed_ticket_or_stake_pairs"] == 1
    assert report["expert_style_research"]["hits"] == 1
    assert report["existing_formal"]["hits"] == 0
    assert report["expert_style_research"]["virtual_stake_yen"] == 50000
    assert report["existing_formal"]["virtual_stake_yen"] == 50000
    official[key]["snapshot_sha256"] = "wrong"
    assert _expert_scenario_portfolio_report([snap], official, {}, "2026-11-20")["matched_races"] == 0
