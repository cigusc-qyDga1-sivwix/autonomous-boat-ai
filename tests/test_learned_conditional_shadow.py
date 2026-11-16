"""Forward-only source-verified conditional pair shadow integration tests."""
from copy import deepcopy

import pytest

from boat_ai.statistical import FEATURES, SCHEMA, digest
from scripts.learned_conditional_shadow import build, VERSION
from scripts.learned_formal import apply

def model():
    obj = {
        "schema": SCHEMA, "features": FEATURES,
        "weights": [[0.0] * len(FEATURES) for _ in range(3)],
        "role": "research_shadow", "calibrated": False,
        "created_at_utc": "2026-11-12T23:30:00+00:00",
        "trained_through": "2026-11-12", "training_n": 200,
    }
    obj["model_sha256"] = digest(obj)
    return obj


def snapshot():
    original = ["-".join(map(str, x)) for x in __import__("itertools").permutations(range(1, 7), 3)]
    bets = [{"combination": x, "virtual_yen": 1000} for x in original[:12]]
    bets[0]["virtual_yen"] += 50000 - 12 * 1000
    racers = [
        {"lane": i, "course": i, "national_win_rate": 5.5,
         "motor_top_2_percent": 35.0,
         "average_start_timing": .19 if i == 1 else (.10 if i == 4 else .17),
         "exhibition_st": .14, "exhibition_time": 6.84,
         "original_exhibition": {"turn_time": 5.8 if i != 4 else 5.3}}
        for i in range(1, 7)
    ]
    raw = {
        "phase": "exhibition",
        "model_version": "four-factor-v2.6-evidence-conditional-pairs-untrained",
        "classification": "WATCH",
        "model_role": "main", "frozen_at_utc": "2026-11-13T01:00:00+00:00",
        "cutoff_iso_jst": "2026-11-13T12:00:00+09:00",
        "racers": racers, "weather_used": {"wind_speed": 2, "wave_height": 1},
        "bets": bets,
    }
    learned = apply(raw, model())
    learned["exhibition_input_check"] = {"verified_before_freeze": True, "six_boats_matched": 6}
    return learned


def test_head_preserving_shadow_changes_pair_not_formal():
    main = snapshot()
    untouched = deepcopy(main)
    result = build(main, model())
    assert result["version"] == VERSION
    assert result["model_role"] == "research_shadow"
    assert result["conditional_status"] == "APPLIED_UNCALIBRATED"
    assert result["head_marginals_preserved"]
    assert result["head_marginal_max_error"] < 1e-8
    assert result["ticket_changed_in_shadow"]
    assert result["status"] == "CHANGED_SHADOW_ONLY"
    assert not result["formal_tickets_changed"]
    assert result["control_bets"] == main["bets"]
    assert len(result["shadow_bets"]) == len(main["bets"])
    assert sum(x["virtual_yen"] for x in result["shadow_bets"]) == 50000
    assert main == untouched


def test_fail_closed_without_verified_or_valid_source():
    main = snapshot()
    main["exhibition_input_check"]["verified_before_freeze"] = False
    with pytest.raises(ValueError, match="no_verified_learned_exhibition"):
        build(main, model())
    main = snapshot()
    main["racers"][3]["original_exhibition"] = {}
    result = build(main, model())
    assert result["conditional_status"] == "NO_COMPLETE_PRE_CUTOFF_SIX_BOAT_EVIDENCE"
    assert not result["ticket_changed_in_shadow"]
    assert result["shadow_bets"] == result["control_bets"]


def test_late_or_other_model_rejected_and_no_hindsight():
    main = snapshot()
    main["frozen_at_utc"] = "2026-11-13T02:59:00+00:00"
    with pytest.raises(ValueError, match="late_or_non_timezone_frozen_forecast"):
        build(main, model())
    main = snapshot()
    main["learned_formal"]["model_sha256"] = "different"
    with pytest.raises(ValueError, match="no_verified_learned_exhibition"):
        build(main, model())
    main = snapshot()
    same = build(main, model())
    main.update({"result": {"finish": "6-5-4"}, "odds": 100, "payout": 1000000})
    after = build(main, model())
    assert same == after


def test_only_after_live_source_match_and_exposed_read_only():
    from pathlib import Path
    code = Path("scripts/autonomous_daily.py").read_text(encoding="utf-8")
    assert code.count("build_learned_conditional_shadow(") == 2
    assert 'new["exhibition_input_check"] = {' in code
    assert 'upgrade["exhibition_input_check"] = {' in code
    assert '"inside_survival_research", "learned_conditional_shadow"' in code
    assert 'formal_tickets_changed": False' in Path(
        "scripts/learned_conditional_shadow.py").read_text(encoding="utf-8")
