"""Forward-only venue motor/exhibition shadow: immutable formal main."""
from copy import deepcopy
from datetime import datetime
from scripts import autonomous_daily as A

def test_shadow_is_recorded_but_never_changes_main_bets_or_sha():
    now = datetime.fromisoformat("2026-11-02T08:30:00+09:00")
    r = {
        "closed_at": "2026-11-02 10:00:00",
        "racers": {str(i): {
            "name": "選手"+str(i), "number": 4000+i,
            "national_win_rate": 6.4-i*.12,
            "average_start_timing": .15+i*.005,
            "motor_top_2_percent": 54-i*5
        } for i in range(1, 7)},
        "preview": {"wind_speed": 2, "wave_height": 1,
            "racers": {str(i): {"course_number": i,
                "exhibition_time": 6.70+i*.03,
                "start_timing": .11+i*.01,
                "tilt_adjustment": 0
            } for i in range(1, 7)}},
    }
    src = {"programs": {"stadiums": {"16": {"races": {"1": r}}}}}
    ledger, ui, _ = A.build(None, src, now, "fixture")
    versions = ledger["race_records"]["16-1"]["versions"]
    assert versions
    formal = versions[-1]
    shadow = formal["venue_motor_exhibition_shadow"]
    assert formal["model_version"] == A.VENUE_TACTICS_MODEL
    assert shadow["status"] == "ready"
    assert shadow["same_inputs_except_shadow"] is True
    assert shadow["not_formal"] is True
    assert shadow["control_bets"] == formal["bets"]
    assert sum(b["virtual_yen"] for b in shadow["trial_bets"]) == 50000
    assert sum(b["virtual_yen"] for b in formal["bets"]) == 50000
    assert ui["forecast_races"][0]["venue_motor_exhibition_shadow"] == shadow
    before = deepcopy(versions)
    after, _, _ = A.build(ledger, src,
        datetime.fromisoformat("2026-11-02T10:10:00+09:00"), "fixture")
    assert after["race_records"]["16-1"]["versions"] == before

def test_shadow_not_backfilled_into_historical_or_baseline_records():
    # The experiment does not manufacture retroactive trials for earlier dates.
    r = {
        "closed_at": "2026-11-01 10:00:00",
        "racers": {str(i): {"name": str(i), "number": 4000+i,
            "national_win_rate": 5.8, "average_start_timing": .15,
            "motor_top_2_percent": 35} for i in range(1, 7)},
        "preview": {"racers": {str(i): {
            "course_number": i, "start_timing": .15,
            "exhibition_time": 6.8, "tilt_adjustment": 0
        } for i in range(1, 7)}}}
    old = A.prediction(r, "児島", 1, "exhibition",
        datetime.fromisoformat("2026-11-01T08:30:00+09:00"), "fixture")
    assert "venue_motor_exhibition_shadow" not in old
