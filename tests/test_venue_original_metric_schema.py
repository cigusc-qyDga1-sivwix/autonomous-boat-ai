"""Per-venue exhibition measurement contracts (forward-only, no network)."""
from copy import deepcopy
from datetime import datetime

from scripts.autonomous_daily import features, select_exhibition_source
from scripts.exhibition_bridge import verified_original_for_openapi
from scripts.ingest_boatracecsv_exhibition import original_exhibition_signature

NOW = datetime.fromisoformat("2026-11-10T08:35:00+09:00")

def example(venue, names):
    race = {
        "closed_at": "2026-11-10 08:50:00",
        "racers": {str(i): {
            "name": f"Racer{i}", "national_win_rate": 6.2-i*.1,
            "motor_top_2_percent": 35+i, "average_start_timing": .15
        } for i in range(1,7)},
        "preview": {"racers": {str(i): {
            "course_number": i, "start_timing": round(.10+i*.01,3),
            "exhibition_time": round(6.65+i*.01,3), "tilt_adjustment": 0
        } for i in range(1,7)}}
    }
    values = {
        "半周ラップ": lambda i: round(17.8+i*.1, 2),
        "一周": lambda i: round(35.8+i*.1, 2),
        "まわり足": lambda i: round(5.2+i*.05, 2),
        "直線": lambda i: round(7.4+i*.03, 2)
    }
    row = {
        "race_code": "20261110"+venue+"01", "venue_code": venue,
        "race": 1, "source_status": "historical_research_only_not_frozen_forecast",
        "original_exhibition_observed_jst": "2026-11-10T08:25:00+09:00",
        "original_exhibition_captured_at_utc": "2026-11-09T23:26:00+00:00",
        "boats": [{
            "lane": i, "course": i, "name": f"Racer{i}",
            "exhibition_st": round(.10+i*.01,3),
            "exhibition_time": round(6.65+i*.01,3),
            "tilt": 0, "original_exhibition": [
                {"metric": name, "value": values[name](i)} for name in names
            ],
        } for i in range(1,7)]
    }
    row["original_exhibition_sha256"] = original_exhibition_signature(row)
    return race, row

def test_kiryu_half_lap_captured_and_not_interpreted_as_full_lap():
    race, row = example("01", ["半周ラップ","まわり足","直線"])
    assert row["original_exhibition_sha256"]
    extras, evidence = verified_original_for_openapi(race,row,NOW,"01",1)
    assert set(extras) == {"half_lap_time","turn_time","straight_time"}
    assert "lap_time" not in extras
    assert evidence["six_boat_preview_matched"] is True
    selected, _, source = select_exhibition_source(race,row,NOW,"01",1)
    assert source == "openapi"
    assert "half_lap_time" in selected["_exhibition_original"]
    with_metrics, details = features(selected,"exhibition")
    no_half = deepcopy(selected)
    no_half["_exhibition_original"].pop("half_lap_time")
    control, _ = features(no_half,"exhibition")
    assert with_metrics == control, "Half-lap should be evidence only until calibrated"
    assert all("half_lap_time" in racer["original_exhibition"] for racer in details)

def test_two_metric_venue_does_not_require_straight():
    race,row = example("12", ["一周","まわり足"])
    extras, evidence = verified_original_for_openapi(race,row,NOW,"12",1)
    assert set(extras) == {"lap_time","turn_time"}
    assert evidence is not None

def test_original_metrics_reject_six_boat_mismatch():
    race,row = example("01", ["半周ラップ","まわり足","直線"])
    wrong = deepcopy(row)
    wrong["boats"][5]["course"] = 5
    assert verified_original_for_openapi(race,wrong,NOW,"01",1) == ({},None)
    wrong2 = deepcopy(row)
    wrong2["boats"][5]["original_exhibition"][0]["value"] = 99
    assert verified_original_for_openapi(race,wrong2,NOW,"01",1) == ({},None)
