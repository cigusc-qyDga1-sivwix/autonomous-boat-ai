"""Forward-only learned formal inference must not rewrite history."""
from datetime import datetime
from zoneinfo import ZoneInfo

from boat_ai.statistical import SCHEMA, FEATURES, digest
from scripts.learned_formal import VERSION, verify_model, apply
import scripts.autonomous_daily as primary

JST = ZoneInfo("Asia/Tokyo")


def model():
    d = {
        "schema": SCHEMA, "features": FEATURES,
        "weights": [[0.0] * len(FEATURES) for _ in range(3)],
        "role": "research_shadow", "calibrated": False,
        "created_at_utc": "2026-11-12T23:30:00+00:00",
        "trained_through": "2026-11-12", "training_n": 200
    }
    d["model_sha256"] = digest(d)
    return d


def fixture(phase="baseline", count=12):
    from itertools import permutations
    combos = ['-'.join(map(str, x)) for x in permutations(range(1, 7), 3)]
    bets = [{"combination": x, "virtual_yen": 1000} for x in combos[:count]]
    bets[0]["virtual_yen"] += 50000 - count * 1000
    return {
        "phase": phase, "model_version": "four-factor-v2.6-evidence-conditional-pairs-untrained",
        "classification": "SKIP", "model_role": "main",
        "frozen_at_utc": "2026-11-13T01:00:00+00:00",
        "cutoff_iso_jst": "2026-11-13T12:00:00+09:00",
        "venue": "徳山", "race": 1,
        "racers": [{"lane": i, "course": i,
                    "national_win_rate": 4.5, "motor_top_2_percent": 30.0,
                    "average_start_timing": .16, "exhibition_st": .14,
                    "exhibition_time": 6.85} for i in range(1, 7)],
        "weather_used": {"wind_speed": 4, "wave_height": 2},
        "bets": bets,
        "interaction_primary": {"original_main": True},
        "strong_field_diagnostic": {"heuristic_only": True},
        "point_count": count
    }


def test_fresh_verifiable_model_only():
    m = model()
    assert verify_model(m, datetime(2026, 11, 13, 10, 0, tzinfo=JST))
    bad = {**m, "training_n": 1}
    assert not verify_model(bad, datetime(2026, 11, 13, 10, 0, tzinfo=JST))
    assert not verify_model(m, datetime(2026, 11, 19, 10, 0, tzinfo=JST))
    assert not verify_model(m, datetime(2026, 11, 12, 10, 0, tzinfo=JST))


def test_learned_main_preserves_old_control_and_50000():
    snapshot = fixture(count=20)
    prior = [dict(x) for x in snapshot["bets"]]
    actual = apply(snapshot, model())
    assert actual["model_version"] == VERSION
    assert actual["model_role"] == "main"
    assert actual["classification"] == "WATCH"
    assert actual["point_count"] == len(actual["bets"]) == 20
    assert sum(x["virtual_yen"] for x in actual["bets"]) == 50000
    assert all(x["virtual_yen"] >= 1000 and x["virtual_yen"] % 1000 == 0 for x in actual["bets"])
    assert actual["learned_formal"]["control_bets"] == prior
    assert actual["learned_formal"]["model_sha256"] == model()["model_sha256"]
    assert actual["learned_formal"]["result_data_used"] is False
    assert "interaction_primary" not in actual
    assert "strong_field_diagnostic" not in actual
    assert snapshot["bets"] == prior
    assert snapshot["model_version"] != VERSION


def test_no_outcome_leakage_or_post_cutoff_reforecast():
    import pytest
    raw = fixture()
    raw.update(result={"finish": "6-5-4"}, odds=100, payout=999999)
    other = fixture()
    assert apply(raw, model())["bets"] == apply(other, model())["bets"]
    raw["frozen_at_utc"] = "2026-11-13T02:59:00+00:00"
    with pytest.raises(ValueError, match="pre-cutoff"):
        apply(raw, model())


def test_daily_builder_freezes_learned_versions_without_overwriting(monkeypatch):
    monkeypatch.setattr(primary, "ACTIVE_LEARNED_MODEL", model())
    race = {"closed_at": "2026-11-13 12:00:00",
            "racers": {str(i): {"name": f"選手{i}", "national_win_rate": 5.2,
                               "motor_top_2_percent": 32.0,
                               "average_start_timing": .16} for i in range(1, 7)}}
    payload = {"programs": {"stadiums": {"18": {"races": {"1": race}}}}}
    now = datetime(2026, 11, 13, 10, 0, tzinfo=JST)
    ledger, view, _ = primary.build(None, payload, now, "fixture")
    first = ledger["race_records"]["18-1"]["versions"][0]
    assert first["model_version"] == VERSION
    assert first["sha256"] == primary.stable_hash({k:v for k,v in first.items() if k!="sha256"})
    assert view["forecast_races"][0]["learned_formal"]["training_n"] == 200
    old_hash=first["sha256"]
    again, _, status = primary.build(
        ledger, payload, datetime(2026, 11, 13, 10, 5, tzinfo=JST), "fixture")
    assert status["new_baseline"] == 0
    assert len(again["race_records"]["18-1"]["versions"]) == 1
    assert again["race_records"]["18-1"]["versions"][0]["sha256"] == old_hash


def test_learned_formal_growth_audit_counts_only_actual_frozen_formal():
    from scripts.forecast_audit import _learned_formal_comparison
    snap = apply(fixture("exhibition"), model())
    snap.update({"cutoff_jst": "12:00", "ticket_status": "formal"})
    snap["sha256"] = digest({k:v for k,v in snap.items() if k!="sha256"})
    pay = {"verified": True, "source": "boatrace_official_pay",
           "virtual_stake": 50000,
           "finish": snap["bets"][0]["combination"],
           "payout_per_100": 1200}
    key = "2026-11-13|徳山|1"
    report = _learned_formal_comparison([snap], {key:pay}, {}, "2026-11-13")
    assert report["matched_verified_races"] == 1
    assert report["learned_formal"]["hits"] == 1
    assert report["learned_formal"]["virtual_stake_yen"] == 50000
    assert model()["model_sha256"] in report["by_model_sha"]
    assert report["by_model_sha"][model()["model_sha256"]]["trained_through"] == "2026-11-12"
    snap["ticket_status"] = "provisional"
    report2 = _learned_formal_comparison([snap], {key:pay}, {}, "2026-11-13")
    assert report2["matched_verified_races"] == 0
    assert report2["exclusions"]["not_proven_paired_formal"] == 1
