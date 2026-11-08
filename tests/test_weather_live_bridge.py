"""Weather LAB live bridge: freshness, provenance, and formal-forecast safety."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from scripts import autonomous_daily as A
from scripts.venue_weather import weather_at
from scripts.weather_live_bridge import jma_as_nearby, wave_for_race, WAVE_SOURCE
from tests.test_four_factor_main import race

UTC = timezone.utc
NOW = datetime.fromisoformat("2026-11-09T09:20:00+09:00")
CUTOFF = datetime.fromisoformat("2026-11-09T10:00:00+09:00")


def wave_doc():
    day = "2026-11-09"
    return {
        "schema": "weather_lab.water_surface_monitor.v1",
        "event_date": day,
        "collected_at_utc": "2026-11-09T00:18:00+00:00",
        "provider": {
            "fetch_status": "ok",
            "url": "https://boatracecsv.github.io/data/previews/sui/2026/11/09.csv"
        },
        "races": [{
            "race_code": "202611091801", "venue_code": "18", "race": 1,
            "cutoff_jst": "10:00", "freshness_status": "fresh_snapshot",
            "source_captured_at_jst": "2026-11-09T09:17:00+09:00",
            "weather_observed_at_jst": "2026-11-09T09:15:00+09:00",
            "weather": {"wave_cm": 9},
        }],
    }


def regional_doc():
    return {
        "schema": "weather_lab.regional_jma_forecast.v1",
        "event_date": "2026-11-09",
        "retrieved_at_utc": "2026-11-09T00:18:00+00:00",
        "provider": {
            "fetch_status": "ok",
            "data_type": "grid_model_forecast_not_ground_observation",
            "api_url": "https://api.open-meteo.com/v1/jma",
            "credit": "Open-Meteo forecast JMA MSM/GSM"
        },
        "venues": [{
            "code": "18", "name": "徳山", "boat_lab_prediction_in_scope": True,
            "hourly": [{
                "valid_at_jst": "2026-11-09T10:00:00+09:00",
                "wind_mps": 7.1, "wind_direction_degrees": 250,
                "air_c": 20, "precipitation_mm": 0,
            }],
        }],
    }


def test_weather_lab_wave_is_precutoff_observed_with_separate_wind_source():
    site = wave_for_race(wave_doc(), "18", 1, CUTOFF, NOW)
    assert site["wave_height"] == 9
    assert site["wave_source"] == WAVE_SOURCE
    assert site["wave_site_observed"]
    jma = jma_as_nearby(regional_doc(), ["18"], NOW)
    nearest = weather_at(jma["18"], CUTOFF)
    assert nearest["source"] == "open-meteo-jma"
    assert nearest["site_observed"] is False
    obs, selected = A.weather_for_prediction(
        {"preview": {"wave_height": 1}}, nearest, site)
    assert selected["wave_height"] == 9
    assert selected["wave_source"] == WAVE_SOURCE
    assert selected["wind_speed"] == 7.1
    assert selected["wind_source"] == "open-meteo-jma"
    assert selected["site_wave_observed"] is True
    assert selected["site_observed"] is False
    assert selected["wind_direction_degrees"] == 250
    assert selected["relative_wind_verified"] if "relative_wind_verified" in selected else True


def test_source_stale_wrong_race_future_and_cutoff_are_rejected():
    doc = wave_doc()
    assert wave_for_race(doc, "18", 2, CUTOFF, NOW) is None
    changed = deepcopy(doc)
    changed["event_date"] = "2026-11-08"
    assert wave_for_race(changed, "18", 1, CUTOFF, NOW) is None
    changed = deepcopy(doc)
    changed["races"][0]["weather_observed_at_jst"] = "2026-11-09T08:00:00+09:00"
    assert wave_for_race(changed, "18", 1, CUTOFF, NOW) is None
    changed = deepcopy(doc)
    changed["races"][0]["source_captured_at_jst"] = "2026-11-09T10:01:00+09:00"
    assert wave_for_race(changed, "18", 1, CUTOFF, NOW) is None
    changed = deepcopy(doc)
    changed["races"][0]["cutoff_jst"] = "10:01"
    assert wave_for_race(changed, "18", 1, CUTOFF, NOW) is None
    assert wave_for_race(doc, "18", 1, CUTOFF,
                         datetime.fromisoformat("2026-11-09T09:58:01+09:00")) is None
    assert wave_for_race(doc, "18", 1, CUTOFF,
                         datetime.fromisoformat("2026-11-09T09:30:00+09:00")) is None


def test_regional_grid_is_forecast_not_station_wind_and_must_be_recent():
    r = jma_as_nearby(regional_doc(), ["18"], NOW)
    assert r["18"]["source"] == "open-meteo-jma"
    assert "wave_height" not in next(iter(r["18"]["hours_jst"].values()))
    stale = regional_doc()
    stale["retrieved_at_utc"] = "2026-11-08T00:00:00+00:00"
    assert not jma_as_nearby(stale, ["18"], NOW)
    wrong_source = regional_doc()
    wrong_source["provider"]["data_type"] = "on_site_observation"
    assert not jma_as_nearby(wrong_source, ["18"], NOW)
    assert not jma_as_nearby(regional_doc(), ["3"], NOW)


def test_formal_v23_consumes_wave_and_keeps_same_budget_and_historical_sha():
    rr = race("2026-11-09")
    rr["preview"]["wind_speed"] = None
    rr["preview"]["wave_height"] = None
    source = {"programs": {"stadiums": {"18": {"races": {"1": rr}}}}}
    prev, _, _ = A.build(None, deepcopy(source), NOW, "fixture",
                          weather_by_venue={"18": jma_as_nearby(regional_doc(), ["18"], NOW)["18"]})
    old_version = deepcopy(prev["race_records"]["18-1"]["versions"])
    ledger, ui, _ = A.build(None, deepcopy(source), NOW, "fixture",
                             weather_by_venue={"18": jma_as_nearby(regional_doc(), ["18"], NOW)["18"]},
                             site_wave_snapshot=wave_doc())
    last = ledger["race_records"]["18-1"]["versions"][-1]
    assert last["model_version"] == A.CONDITIONAL_SECOND_MAIN_MODEL
    assert last["weather_used"]["wave_height"] == 9
    assert last["weather_used"]["wave_site_observed"] is True
    assert last["weather_lab_integration"]["site_wave_applied"] is True
    assert last["weather_lab_integration"]["wind_source"] == "open-meteo-jma"
    assert ui["forecast_races"][0]["weather_lab_integration"] == last["weather_lab_integration"]
    assert sum(b["virtual_yen"] for b in last["bets"]) == 50000
    assert last["sha256"] == A.stable_hash({k: v for k, v in last.items() if k != "sha256"})
    # A same-race forecast with a valid new wave is a different prediction
    # snapshot, never an overwrite of a previously immutable version.
    assert old_version[0]["sha256"] != last["sha256"]
    rr["result"] = {"finish": "6-2-1", "payout_per_100": 30000}
    post = A.prediction(rr, "徳山", 1, "exhibition", NOW, "fixture",
                        weather_at(jma_as_nearby(regional_doc(), ["18"], NOW)["18"], CUTOFF),
                        wave_for_race(wave_doc(), "18", 1, CUTOFF, NOW))
    assert post["bets"] == last["bets"]
    assert not post["weather_lab_integration"]["result_data_used"]


def test_stale_wave_never_changes_formal_pre_cutoff_selection():
    rr = race("2026-11-09")
    rr["preview"]["wind_speed"] = None
    rr["preview"]["wave_height"] = None
    source = {"programs": {"stadiums": {"18": {"races": {"1": rr}}}}}
    prior, _, _ = A.build(None, source, NOW, "fixture")
    bad = wave_doc()
    bad["races"][0]["weather_observed_at_jst"] = "2026-11-09T07:00:00+09:00"
    other, _, _ = A.build(None, source, NOW, "fixture", site_wave_snapshot=bad)
    assert other["race_records"]["18-1"]["versions"] == prior["race_records"]["18-1"]["versions"]
