"""Guardrails for the forward-only, third-place research shadow."""
import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from boat_ai.statistical import FEATURES, SCHEMA, digest, prepare, distributions
from scripts.learned_formal import apply, VERSION as MAIN_VERSION
from scripts.third_place_pilot import (
    EXTRA_FEATURES, THIRD_FEATURES, PILOT_SCHEMA, PILOT_VERSION,
    conditional_ranked, frozen_shadow, third_features, verify_pilot, train,
)
import scripts.learned_formal as learned
import scripts.third_place_pilot as third
from scripts.forecast_audit import _third_place_pilot_report


def primary():
    model = {
        "schema": SCHEMA, "features": FEATURES,
        "weights": [[0.0]*len(FEATURES) for _ in range(3)],
        "created_at_utc": "2026-11-12T23:30:00+00:00",
        "trained_through": "2026-11-12", "training_n": 200,
        "role": "research_shadow", "calibrated": False,
    }
    model["model_sha256"] = digest(model)
    return model


def third_model(m=None):
    m = m or primary()
    model = {
        "schema": PILOT_SCHEMA, "version": PILOT_VERSION,
        "features": THIRD_FEATURES, "weights": [0.0]*len(THIRD_FEATURES),
        "created_at_utc": "2026-11-13T00:00:00+00:00",
        "trained_through": "2026-11-12", "training_n": 200,
        "parent_schema": SCHEMA, "parent_model_sha256": m["model_sha256"],
        "role": "research_shadow", "not_formal": True, "calibrated": False,
    }
    # Nonzero pre-race course-neighbor signal so the shadow differs from
    # the zero-coefficient formal control in deterministic tests.
    model["weights"][THIRD_FEATURES.index("third_adjacent_to_second")] = 2.0
    model["model_sha256"] = digest(model)
    return model


def snapshot():
    return {
        "phase": "exhibition",
        "model_version": "four-factor-v2.6-evidence-conditional-pairs-untrained",
        "model_role": "main", "classification": "WATCH",
        "venue": "徳山", "race": 1,
        "frozen_at_utc": "2026-11-13T01:00:00+00:00",
        "cutoff_jst": "12:00",
        "cutoff_iso_jst": "2026-11-13T12:00:00+09:00",
        "racers": [
            {"lane": i, "course": i, "national_win_rate": 5.0+(i%3)/2,
             "motor_top_2_percent": 30.0+i,
             "average_start_timing": .15+i*.005,
             "exhibition_time": 6.85-i*.01,
             "exhibition_st": .12+i*.01}
            for i in range(1, 7)
        ],
        "weather_used": {"wind_speed": 4, "wave_height": 3},
        "bets": [
            {"combination": combo, "virtual_yen": yen}
            for combo, yen in [
                ("1-2-3", 20000), ("2-1-3", 15000),
                ("3-2-1", 10000), ("4-1-2", 5000),
            ]
        ],
    }


def test_third_features_context_distinct_and_result_agnostic():
    s = snapshot()
    p = prepare(s)
    assert len(EXTRA_FEATURES) == 15
    a = third_features(p, 2, 0, 1)
    b = third_features(p, 2, 1, 0)
    assert len(a) == len(THIRD_FEATURES)
    assert a != b
    with pytest.raises(ValueError):
        third_features(p, 0, 0, 1)
    m, pilot = primary(), third_model()
    ranked = conditional_ranked(s, m, pilot)
    assert len(ranked) == len({x["combination"] for x in ranked}) == 120
    assert sum(x["score"] for x in ranked) == pytest.approx(1)
    # First+second pair mass must remain EXACTLY the same as the formal model.
    before = distributions(s, m)
    for pair in ("1-2-", "2-1-", "6-5-"):
        assert sum(x["score"] for x in ranked if x["combination"].startswith(pair)) == pytest.approx(
            sum(x["score"] for x in before if x["combination"].startswith(pair))
        )
    mutated = copy.deepcopy(s)
    mutated.update(result={"finish": "6-5-4"}, payout=9_999_999, odds=9_999)
    assert conditional_ranked(mutated, m, pilot) == ranked


def test_stale_parent_mismatch_and_future_training_all_rejected():
    m = primary()
    pilot = third_model(m)
    frozen = datetime.fromisoformat(snapshot()["frozen_at_utc"])
    assert verify_pilot(pilot, m, frozen)
    bad = dict(pilot, training_n=201)
    assert not verify_pilot(bad, m, frozen)
    wrong = copy.deepcopy(m)
    wrong["model_sha256"] = "0"*64
    assert not verify_pilot(pilot, wrong, frozen)
    assert not verify_pilot(pilot, m, datetime.fromisoformat("2026-11-15T10:00:00+00:00"))
    assert not verify_pilot(pilot, m, datetime.fromisoformat("2026-11-12T23:00:00+00:00"))


def test_pilot_is_only_a_shadow_and_formal_bets_never_change(monkeypatch):
    m, pilot = primary(), third_model()
    monkeypatch.setattr(learned, "load_pilot", lambda _m, _f: pilot)
    source = snapshot()
    before = copy.deepcopy(source)
    result = apply(source, m)
    shadow = result["third_place_pilot"]
    assert result["model_version"] == MAIN_VERSION
    assert result["bets"] != [] and result["bets"] != shadow["bets"]
    assert result["model_role"] == "main"
    assert shadow["not_formal"] is True and shadow["no_additional_stake"] is True
    assert shadow["source_main_bets_sha256"] == digest({"bets": result["bets"]})
    assert shadow["parent_model_sha256"] == m["model_sha256"]
    assert len(shadow["bets"]) == len(result["bets"]) == 4
    assert sum(x["virtual_yen"] for x in shadow["bets"]) == 50000
    assert all(x["virtual_yen"] >= 1000 for x in shadow["bets"])
    assert source == before
    # A model with a wrong parent SHA can never be attached or alter tickets.
    monkeypatch.setattr(learned, "load_pilot", lambda _m, _f: third_model(
        {**m, "model_sha256": "0"*64}))
    no_trial = apply(source, m)
    assert "third_place_pilot" not in no_trial
    assert no_trial["bets"] == result["bets"]


def test_third_audit_counts_only_official_verified_formal(monkeypatch):
    monkeypatch.setattr(learned, "load_pilot", lambda _m, _f: third_model())
    result = apply(snapshot(), primary())
    result["ticket_status"] = "formal"
    result["exhibition_input_check"] = {"verified_before_freeze": True}
    result["sha256"] = digest(result)
    pay = {"verified": True, "source": "boatrace_official_pay",
           "virtual_stake": 50000,
           "finish": result["bets"][0]["combination"],
           "payout_per_100": 1200,
           "snapshot_sha256": result["sha256"]}
    key = "2026-11-13|徳山|1"
    report = _third_place_pilot_report([result], {key: pay}, {}, "2026-11-13")
    assert report["paired_verified_races"] == 1
    assert report["learned_formal"]["verified_races"] == 1
    assert report["third_place_trial"]["verified_races"] == 1
    assert report["learned_formal"]["virtual_stake_yen"] == 50000
    assert report["third_place_trial"]["virtual_stake_yen"] == 50000
    result["ticket_status"] = "provisional"
    excluded = _third_place_pilot_report([result], {key: pay}, {}, "2026-11-13")
    assert excluded["paired_verified_races"] == 0
    assert excluded["exclusions"]["invalid_unmatched_or_unverified_shadow"] == 1
    result["ticket_status"] = "formal"
    unverified = _third_place_pilot_report([result], {}, {}, "2026-11-13")
    assert unverified["paired_verified_races"] == 0
    assert unverified["exclusions"]["unverified"] == 1


def test_training_cutoff_is_previous_day_not_same_day(monkeypatch, tmp_path):
    m = primary()
    path = tmp_path/"main-model.json"
    path.write_text(json.dumps(m))
    old = snapshot()
    old["phase"] = "baseline"
    old["frozen_at_utc"] = "2026-11-12T01:00:00+00:00"
    rows = [
        {"day": "2026-11-12", "race_key": f"18-{i}",
         "snapshot": {**old, "sha256": str(i)}, "label": [0,1,2],
         "official": {"verified": True, "finish": "1-2-3"}}
        for i in range(120)
    ]
    monkeypatch.setattr(third, "dataset", lambda _p, day: (rows, {}))
    monkeypatch.setattr(third, "fit_third", lambda data: {
        "weights": [0.0]*len(THIRD_FEATURES), "l2": .08,
        "optimization": {"success": True, "iterations": 0,
                         "penalized_loss": 0.0},
    })
    now = datetime.fromisoformat("2026-11-13T01:00:00+00:00")
    saved = train(tmp_path, tmp_path, now, path)
    assert saved["trained_through"] == "2026-11-12"
    assert saved["training_n"] == 120
    assert saved["role"] == "research_shadow"
    assert verify_pilot(saved, m, now)
    assert (tmp_path/"third-place-pilot-latest.json").exists()
    too_old = copy.deepcopy(rows)
    for r in too_old:
        r["day"] = "2026-11-11"
    monkeypatch.setattr(third, "dataset", lambda _p, day: (too_old, {}))
    with pytest.raises(ValueError, match="same training cutoff"):
        train(tmp_path, tmp_path, now, path)
