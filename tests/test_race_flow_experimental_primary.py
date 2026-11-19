"""20 Nov forward-only aggressive race-flow experiment contract."""
from copy import deepcopy
from datetime import datetime
from itertools import permutations

import pytest

from boat_ai.statistical import SCHEMA, FEATURES, digest
from scripts.race_flow_experimental_primary import rescore, POLICY_SHA256
from scripts.learned_formal import apply as learned_apply

FROZEN = "2026-11-20T01:45:00+00:00"
CUTOFF = "2026-11-20T12:00:00+09:00"


def boats():
    rows = [{
        "lane": i, "course": i, "name": f"選手{i}",
        "average_start_timing": .19, "average_start_timing_imputed": False,
        "exhibition_st": .16, "exhibition_time": 6.85,
        "motor_top_2_percent": 30.0, "national_win_rate": 5.0,
    } for i in range(1, 7)]
    attack = rows[1]  # actual course 2, first head should move away from 1
    attack.update(average_start_timing=.14, exhibition_st=.10,
                  exhibition_time=6.75, motor_top_2_percent=47.0,
                  national_win_rate=6.5)
    return rows


def canonical():
    keys = ["-".join(map(str, x)) for x in permutations(range(1, 7), 3)]
    return [{"combination": key, "score": 1 / 120} for key in keys]


def run(racers=None, rows=None, verified=True, frozen=FROZEN, cutoff=CUTOFF):
    return rescore(
        canonical() if rows is None else rows,
        boats() if racers is None else racers,
        frozen_at_utc=frozen, cutoff_iso_jst=cutoff,
        exhibition_verified=verified,
    )


def test_aggressive_head_switch_with_two_independent_signals():
    original = canonical()
    before = deepcopy(original)
    changed, audit = run(rows=original)
    assert audit["status"] == "APPLIED_EXPERIMENTAL_UNCALIBRATED"
    assert changed[0]["combination"][0] == "2"
    assert audit["first_head_after"]["2"] > audit["first_head_before"]["2"]
    assert audit["first_head_after"]["1"] < audit["first_head_before"]["1"]
    assert len(changed) == 120 and abs(sum(x["score"] for x in changed) - 1) < 1e-8
    assert {r["combination"] for r in changed} == {r["combination"] for r in original}
    assert not audit["calibrated"] and not audit["results_used"] and not audit["odds_used"]
    assert original == before


def test_no_blanket_lane_one_penalty_and_false_start():
    neutral = boats()
    for row in neutral:
        row.update(average_start_timing=.16, exhibition_st=.16,
                   exhibition_time=6.85, motor_top_2_percent=30.0,
                   national_win_rate=5.0)
    ranked, audit = run(racers=neutral)
    assert audit["status"] == "NO_TWO_INDEPENDENT_ATTACK_SIGNALS"
    assert ranked == canonical()
    assert run(verified=False)[1]["status"] == "UNVERIFIED_EXHIBITION"
    bad = boats()
    bad[1]["exhibition_st"] = -.01
    assert run(racers=bad)[1]["status"] == "INCOMPLETE_EXHIBITION"


def test_actual_courses_not_lane_and_no_postrace_repair():
    racers = boats()
    racers[0]["lane"], racers[1]["lane"] = 2, 1
    changed, audit = run(racers=racers)
    assert audit["challenging_courses"]["2"]["lane"] == 1
    assert changed[0]["combination"][0] == "1"
    bad = boats()
    bad[0]["actual_finish"] = "1-2-3"
    with pytest.raises(ValueError, match="postrace"):
        run(racers=bad)
    bad = boats()
    bad[3]["course"] = 2
    with pytest.raises(ValueError, match="duplicate"):
        run(racers=bad)
    with pytest.raises(ValueError, match="late"):
        run(frozen="2026-11-20T02:59:00+00:00")


def future_model():
    m = {"schema": SCHEMA, "features": FEATURES,
         "weights": [[0.0] * len(FEATURES) for _ in range(3)],
         "role": "research_shadow", "calibrated": False,
         "created_at_utc": "2026-11-19T01:30:00+00:00",
         "trained_through": "2026-11-18", "training_n": 3928}
    m["model_sha256"] = digest(m)
    return m


def future_snapshot(verified=True):
    from boat_ai.statistical import allocate
    prior = allocate(canonical(), 8, max_points=20)
    return {
        "phase": "exhibition", "model_version": "four-factor-v2.3-conditional-second-primary-untrained",
        "classification": "WATCH", "model_role": "main",
        "venue": "徳山", "race": 1,
        "frozen_at_utc": FROZEN, "cutoff_iso_jst": CUTOFF,
        "racers": boats(), "bets": prior,
        "exhibition_origin": {"captured_before_cutoff": verified},
        "weather_used": {"wind_speed": 2, "wave_height": 1}
    }


def test_learned_app_saves_same_time_control_and_50000_budget():
    base = future_snapshot()
    original = deepcopy(base)
    out = learned_apply(base, future_model())
    evidence = out["experimental_race_flow"]
    assert evidence["status"] == "APPLIED_EXPERIMENTAL_UNCALIBRATED"
    assert evidence["formal_component"] is True
    assert evidence["first_ticket_head_changed"] is True
    assert evidence["formal_bets_changed"] is True
    assert out["bets"][0]["combination"][0] == "2"
    assert evidence["control_bets_sha256"] == digest(evidence["same_time_control_bets"])
    assert sum(b["virtual_yen"] for b in evidence["same_time_control_bets"]) == 50000
    assert sum(b["virtual_yen"] for b in out["bets"]) == 50000
    assert len(out["bets"]) == len(evidence["same_time_control_bets"]) == 8
    assert out["classification"] == "WATCH"
    assert "展開実験" in out["scenario"]
    assert evidence["policy_sha256"] == POLICY_SHA256
    assert base == original
    withheld = learned_apply(future_snapshot(verified=False), future_model())
    assert withheld["experimental_race_flow"]["formal_component"] is False
    assert withheld["experimental_race_flow"]["formal_bets_changed"] is False


def test_baseline_and_pre_activation_never_experiment():
    snap = future_snapshot()
    snap["phase"] = "baseline"
    assert "experimental_race_flow" not in learned_apply(snap, future_model())
    # Use an eligible model trained before the snapshot's day.
    snap = future_snapshot()
    snap["frozen_at_utc"] = "2026-11-19T01:45:00+00:00"
    snap["cutoff_iso_jst"] = "2026-11-19T12:00:00+09:00"
    assert "experimental_race_flow" not in learned_apply(snap, future_model())


def test_official_audit_compares_both_pre_frozen_versions():
    from scripts.forecast_audit import _experimental_race_flow_report
    snap = learned_apply(future_snapshot(), future_model())
    snap["cutoff_jst"] = "12:00"
    snap["ticket_status"] = "formal"
    snap["exhibition_input_check"] = {
        "verified_before_freeze": True, "six_boats_matched": 6}
    snap["sha256"] = digest({k: v for k, v in snap.items() if k != "sha256"})
    key = "2026-11-20|徳山|1"
    official = {key: {
        "verified": True, "source": "boatrace_official_pay",
        "virtual_stake": 50000, "snapshot_sha256": snap["sha256"],
        "finish": snap["bets"][0]["combination"], "payout_per_100": 1500,
    }}
    report = _experimental_race_flow_report([snap], official, {}, "2026-11-20")
    assert report["matched_races"] == 1
    assert report["verified_formal_ticket_change_races"] == 1
    assert report["verified_formal_first_head_change_races"] == 1
    assert report["experimental_formal"]["hits"] == 1
    assert report["same_time_learned_control"]["hits"] == 0
    assert report["head_misses_recovered"] == 1
    assert report["experimental_formal"]["virtual_stake_yen"] == 50000
    assert report["same_time_learned_control"]["virtual_stake_yen"] == 50000
    official[key]["verified"] = False
    report = _experimental_race_flow_report([snap], official, {}, "2026-11-20")
    assert report["matched_races"] == 0
    assert report["exclusions"]["unverified"] == 1
