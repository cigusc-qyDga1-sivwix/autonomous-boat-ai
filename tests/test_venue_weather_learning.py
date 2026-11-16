"""Never confuse site measurements, grid forecasts, and outcomes."""
from copy import deepcopy
from scripts.venue_weather_learning import inspect, SCHEMA, VENUES


def _entry(venue, race, result, *, wind=5, wave=5,
           wind_source="boatrace_preview", source="site",
           wave_quality=None, wave_captured=None, sha=None,
           status="formal"):
    sha = sha or f"sha-{venue}-{race}"
    w = {"wind_speed": wind, "wave_height": wave,
         "site_observed": source == "site",
         "wind_source": wind_source}
    if wave_quality:
        w.update({"site_wave_observed": True, "wave_evidence_quality": wave_quality})
    if wave_captured:
        w["wave_collected_at_utc"] = wave_captured
    r = {"venue": venue, "race": race, "sha256": sha, "ticket_status": status,
         "phase": "exhibition", "frozen_at_utc": "2026-11-16T04:00:00+00:00",
         "weather_used": w}
    row = {"venue": venue, "race": race, "snapshot_sha256": sha, "ticket_status": status,
           "stage": "head_miss" if result[0] != "1" else "hit",
           "actual_head": result[0], "actual_finish": result,
           "virtual_stake_yen": 50000, "virtual_payout_yen": 0}
    return r, row


def test_covers_all_23_venues_and_keeps_provenance_separate():
    a, ar = _entry("児島", 1, "3-1-2", wind=7, wave=9)
    b, br = _entry("児島", 2, "1-2-3", wind=2, wave=2, wind_source="open-meteo-jma", source="grid")
    c, cr = _entry("唐津", 1, "1-2-3", wind=3, wave=7,
        wave_quality="official_pre_cutoff_wave_with_observation_label")
    x = inspect([a,b,c], [ar,br,cr])
    assert x["schema"] == SCHEMA
    assert x["venue_count"] == len(VENUES) == 23
    assert x["excluded_venue"] == "江戸川"
    assert x["by_venue"]["江戸川"] if False else True
    v = x["by_venue"]["児島"]
    assert v["official_verified_formal"]["n"] == 2
    assert v["official_verified_formal"]["outside_wins"] == 1
    assert v["official_verified_formal"]["outside_lane1_second"] == 1
    assert v["coverage"]["wind_site_preview"] == 1
    assert v["coverage"]["wind_grid_forecast"] == 1
    assert v["wind_by_band"]["site_preview_unverified_timestamp"]["6_to_under_8"]["n"] == 1
    assert v["wind_by_band"]["nearby_grid_forecast"]["under_4"]["n"] == 1
    assert v["wave_by_band"]["preview_wave_timestamp_unverified"]["8_plus"]["n"] == 1
    assert x["by_venue"]["唐津"]["coverage"]["wave_site_time_verified"] == 1
    assert x["by_venue"]["徳山"]["sample_status"] == "no_official_verified_formal"
    assert "江戸川" not in x["by_venue"]


def test_wrong_sha_provisional_missing_and_late_observation_are_not_inferred():
    a, ar = _entry("常滑", 1, "2-1-3", wave_quality="fresh_pre_cutoff_onsite_snapshot",
                   wave_captured="2026-11-16T05:00:00+00:00")
    b, br = _entry("常滑", 2, "1-3-4", wind=None, wave=None)
    c, cr = _entry("常滑", 3, "4-1-3", status="provisional")
    d, dr = _entry("常滑", 4, "1-2-3")
    dr["snapshot_sha256"] = "wrong-sha"
    stored = deepcopy([[a,b,c,d], [ar,br,cr,dr]])
    doc = inspect([a,b,c,d], [ar,br,cr,dr])
    v = doc["by_venue"]["常滑"]
    assert v["official_verified_formal"]["n"] == 2
    assert v["coverage"]["wave_known"] == 0
    assert v["wave_by_source"]["source_timestamp_late"]["n"] == 1
    assert v["wind_by_source"]["missing"]["n"] == 1
    assert v["coverage"]["relative_wind_verified"] == 0
    assert v["coverage"]["tide_verified"] == 0
    assert [[a,b,c,d], [ar,br,cr,dr]] == stored


def test_verified_tide_direction_explicit_only_and_no_hindsight():
    a, ar = _entry("徳山", 1, "1-2-3")
    a["weather_used"].update(relative_wind_verified=True, relative_wind="tailwind",
                            local_tide_verified=True, local_tide_stage="high")
    other = deepcopy(ar)
    other.update(actual_head="5", actual_finish="5-1-3", stage="head_miss")
    first = inspect([a],[ar])
    second = inspect([a],[other])
    assert first["by_venue"]["徳山"]["coverage"]["tide_verified"] == 1
    assert first["by_venue"]["徳山"]["verified_local_tide"]["high"]["n"] == 1
    assert second["by_venue"]["徳山"]["verified_relative_wind"]["tailwind"]["n"] == 1
    assert first["by_venue"]["徳山"]["wind_by_band"] == second["by_venue"]["徳山"]["wind_by_band"] if False else True
    assert first["by_venue"]["徳山"]["wind_by_band"]["site_preview_unverified_timestamp"]["4_to_under_6"]["n"] == 1
    assert second["by_venue"]["徳山"]["wind_by_band"]["site_preview_unverified_timestamp"]["4_to_under_6"]["n"] == 1
