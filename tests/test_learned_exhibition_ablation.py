"""Same-time learned exhibition ablation: frozen main unchanged."""
from copy import deepcopy
from datetime import datetime, timezone
from urllib.error import HTTPError
from io import BytesIO

import pytest
from boat_ai.statistical import FEATURES, SCHEMA, digest
from scripts.learned_formal import apply
from scripts.learned_exhibition_ablation import build, VERSION
from scripts import ingest_boatracecsv_exhibition as csv_source


def model():
    weights = [[0.] * len(FEATURES) for _ in range(3)]
    weights[0][FEATURES.index("exhibition_relative")] = 6.
    x = {"schema": SCHEMA, "features": FEATURES, "weights": weights,
         "role": "research_shadow", "calibrated": False,
         "created_at_utc": "2026-11-12T23:30:00+00:00",
         "trained_through": "2026-11-12", "training_n": 200}
    x["model_sha256"] = digest(x)
    return x


def main_snapshot():
    from itertools import permutations
    all_bets = ["-".join(map(str, p)) for p in permutations(range(1, 7), 3)]
    bets = [{"combination": b, "virtual_yen": 1000} for b in all_bets[:12]]
    bets[0]["virtual_yen"] += 50000 - 12000
    raw = {
        "phase": "exhibition",
        "model_version": "four-factor-v2.6-evidence-conditional-pairs-untrained",
        "model_role": "main",
        "classification": "WATCH",
        "frozen_at_utc": "2026-11-13T01:00:00+00:00",
        "cutoff_iso_jst": "2026-11-13T12:00:00+09:00",
        "racers": [
            {"lane": lane, "course": lane, "national_win_rate": 5.0,
             "motor_top_2_percent": 32., "average_start_timing": .16,
             "exhibition_time": (6.20 if lane == 4 else 6.88),
             "exhibition_st": (.09 if lane == 4 else .15),
             "original_exhibition": {"turn_time": 5.5}}
            for lane in range(1, 7)
        ],
        "bets": bets, "weather_used": {"wind_speed": 3, "wave_height": 2},
    }
    learned = apply(raw, model())
    learned["exhibition_input_check"] = {
        "verified_before_freeze": True, "six_boats_matched": 6,
        "original_metrics_matched": ["turn_time"]
    }
    return learned


def test_same_model_pre_cutoff_ablation_really_changes_tickets():
    snap = main_snapshot()
    original = deepcopy(snap)
    trial = build(snap, model())
    assert trial["version"] == VERSION
    assert trial["same_model_same_time"] is True
    assert trial["model_role"] == "research_shadow"
    assert trial["actual_ticket_or_stake_changed"]
    assert trial["formal_tickets_changed"] is False
    assert trial["formal_bets"] == snap["bets"]
    assert trial["no_exhibition_bets"] != snap["bets"]
    assert len(trial["no_exhibition_bets"]) == len(snap["bets"])
    assert sum(x["virtual_yen"] for x in trial["no_exhibition_bets"]) == 50000
    assert trial["factual_input_sha256"] != trial["no_exhibition_input_sha256"]
    assert (snap == original)


def test_reject_unverified_late_or_inconsistent_model():
    x = main_snapshot()
    x["exhibition_input_check"]["verified_before_freeze"] = False
    with pytest.raises(ValueError, match="not_eligible"):
        build(x, model())
    x = main_snapshot()
    x["frozen_at_utc"] = "2026-11-13T02:59:00+00:00"
    with pytest.raises(ValueError, match="not_eligible"):
        build(x, model())
    x = main_snapshot()
    x["bets"][0]["combination"] = "6-5-4"
    with pytest.raises(ValueError, match="main_model_not_reproducible"):
        build(x, model())
    x = main_snapshot()
    x["learned_formal"]["model_sha256"] = "corrupt"
    with pytest.raises(ValueError, match="not_eligible"):
        build(x, model())


def test_no_after_result_or_odds_in_shadow():
    x = main_snapshot()
    clean = build(x, model())
    x.update({"result": {"finish": "6-5-4"}, "payout": 95000, "odds": 1000})
    assert build(x, model()) == clean


def test_source_fetch_diagnostics_available_without_changing_default(monkeypatch):
    def raw(request, timeout):
        return BytesIO("レースコード,取得日時\n202611161501,2026-11-16T10:00:00+09:00\n".encode())
    monkeypatch.setattr(csv_source, "urlopen", raw)
    from datetime import date
    data = csv_source.fetch("original", date(2026, 11, 16))
    assert len(data) == 1
    new, detail = csv_source.fetch("original", date(2026, 11, 16),
                                  with_diagnostics=True)
    assert new == data
    assert detail["source"] == "github_raw"
    assert detail["status"] == "AVAILABLE"
    assert detail["rows"] == 1


def test_fetch_source_fallback_and_outage_are_explicit(monkeypatch):
    from datetime import date
    def fallback(request, timeout):
        if "raw.githubusercontent.com" in request.full_url:
            raise HTTPError(request.full_url, 404, "not found", {}, None)
        return BytesIO("レースコード,取得日時\n202611161501,2026-11-16T10:00:00+09:00\n".encode())
    monkeypatch.setattr(csv_source, "urlopen", fallback)
    data, detail = csv_source.fetch("stt", date(2026, 11, 16),
                                    with_diagnostics=True)
    assert len(data) == 1
    assert detail["source"] == "github_pages"
    assert detail["attempts"] == ["github_raw:HTTP 404"]

    def offline(request, timeout):
        raise HTTPError(request.full_url, 404, "not found", {}, None)
    monkeypatch.setattr(csv_source, "urlopen", offline)
    rows, detail = csv_source.fetch("original", date(2026, 11, 16),
                                    with_diagnostics=True)
    assert rows == []
    assert detail["status"] == "SOURCE_UNAVAILABLE"
    assert detail["attempts"] == ["github_raw:HTTP 404", "github_pages:HTTP 404"]


def test_production_attachment_after_live_six_boat_checks():
    from pathlib import Path
    code = Path("scripts/autonomous_daily.py").read_text(encoding="utf-8")
    assert code.count("build_learned_exhibition_ablation(") == 2
    assert '"learned_exhibition_ablation"' in code
    assert '"same_time_learned_ablation_frozen"' in code
    assert 'new["exhibition_input_check"] = {' in code
    assert 'upgrade["exhibition_input_check"] = {' in code


def test_official_comparison_uses_only_same_time_frozen_sha():
    from scripts.forecast_audit import _learned_exhibition_effect_report
    saved=main_snapshot()
    saved["venue"]="徳山"
    saved["race"]=2
    saved["cutoff_jst"]="12:00"
    saved["ticket_status"]="formal"
    saved["learned_exhibition_ablation"]=build(saved, model())
    day="2026-11-13"
    key=f"{day}|徳山|2"
    pay={"verified":True, "source":"boatrace_official_pay", "finish":"4-2-5",
         "payout_per_100":8900, "virtual_stake":50000}
    report=_learned_exhibition_effect_report([saved], {key:pay}, set(), day)
    assert report["matched_races"]==1
    assert report["official_matched_ticket_change_races"]==1
    assert report["historical_formal_forecasts_modified"] is False
    assert report["with_exhibition_formal"]["verified_races"]==1
    assert report["without_exhibition_research"]["verified_races"]==1

    tampered=deepcopy(saved)
    tampered["learned_exhibition_ablation"]["no_exhibition_bets"][0]["virtual_yen"]+=1000
    invalid=_learned_exhibition_effect_report([tampered],{key:pay},set(),day)
    assert invalid["matched_races"]==0
    assert invalid["exclusions"]["unproven_or_modified_ablation"]==1
    conflict=_learned_exhibition_effect_report([saved],{key:pay},{key},day)
    assert conflict["matched_races"]==0
    assert conflict["exclusions"]["official_conflict_or_refund"]==1
