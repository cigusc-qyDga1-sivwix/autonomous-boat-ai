"""Same-run WEATHER LAB -> BOAT LAB pre-cutoff weather bridge.

Fetches today's independently sourced on-site *wave only* CSV and JMA regional
model forecasts alongside existing Open-Meteo grid weather. Rejects stale
timestamps. No results, payout, odds, or historical observed readings are used.
The bridge never writes weather values into earlier immutable forecasts.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weather_lab.monitor import download as download_sui, build as build_sui
from weather_lab.regional_jma import fetch as fetch_jma, SCHEMA as JMA_SCHEMA

try:
    from .venue_weather import fetch_weather as fetch_grid
except ImportError:
    from venue_weather import fetch_weather as fetch_grid

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")
MAX_JMA_ACQUISITION_AGE = timedelta(minutes=6)
MAX_WAVE_CAPTURE_AGE = timedelta(minutes=15)
MAX_WAVE_OBSERVATION_AGE = timedelta(minutes=20)
WAVE_SOURCE = "weather_lab_boatracecsv_previews_sui"


def _timestamp(raw):
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value if value.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def jma_as_nearby(document, active_codes, at):
    """Convert verified JMA *grid model forecasts*, never station observations."""
    if not isinstance(document, dict) or document.get("schema") != JMA_SCHEMA:
        return {}
    if at.tzinfo is None or document.get("event_date") != at.astimezone(JST).date().isoformat():
        return {}
    provider = document.get("provider") or {}
    acquired = _timestamp(document.get("retrieved_at_utc"))
    if (provider.get("fetch_status") != "ok" or
            provider.get("data_type") != "grid_model_forecast_not_ground_observation" or
            acquired is None or not timedelta(0) <= at-acquired <= MAX_JMA_ACQUISITION_AGE):
        return {}
    active = {str(int(x)) for x in active_codes if str(x).isdigit()}
    venues = document.get("venues") or []
    if not isinstance(venues, list):
        return {}
    result = {}
    for venue in venues:
        if not isinstance(venue, dict) or not str(venue.get("code", "")).isdigit():
            continue
        code = str(int(venue["code"]))
        if code not in active or code == "3" or venue.get("boat_lab_prediction_in_scope") is not True:
            continue
        hourly = {}
        for hour in venue.get("hourly") or []:
            when = _timestamp(hour.get("valid_at_jst")) if isinstance(hour, dict) else None
            speed = hour.get("wind_mps") if isinstance(hour, dict) else None
            if (when is None or when.astimezone(JST).date() != at.astimezone(JST).date()
                    or type(speed) not in (int, float) or not 0 <= speed <= 80):
                continue
            hourly[when.astimezone(JST).strftime("%Y-%m-%dT%H:%M")] = {
                "wind_speed": float(speed),
                "wind_direction_degrees": hour.get("wind_direction_degrees"),
                "air_temperature": hour.get("air_c"),
                "precipitation_mm": hour.get("precipitation_mm"),
            }
        if hourly:
            result[code] = {
                "source": "open-meteo-jma",
                "source_label": "気象庁モデルによる近隣格子予報（場内実測ではない）",
                "source_url": provider.get("api_url"),
                "credit": provider.get("credit"),
                "licence": provider.get("licence"),
                "retrieved_at_utc": acquired.isoformat(),
                "grid_reference": "会場近隣の概算地点・気象庁MSM/GSM格子予報",
                "hours_jst": hourly,
            }
    return result


def collect_today(active_codes, at):
    """Concurrent provider calls; failure never blocks the old base model.

    Wave source is collected *now*, not read from the retrospective/weather-lab
    data branch. No end-of-day snapshot can be backdated into a formal ticket.
    """
    if at.tzinfo is None:
        raise ValueError("Aware real time required")
    active = [str(int(c)) for c in active_codes if str(c).isdigit() and 1 <= int(c) <= 24]
    if not active:
        return {}, None, {"status": "no_active_venues"}
    day = at.astimezone(JST).date()

    def wave_task():
        source, url, error = download_sui(day)
        return build_sui(source, datetime.now(UTC), day, source_url=url, fetch_error=error)

    def jma_task():
        document = fetch_jma(datetime.now(UTC))
        # The model's returned stamp refers to request start, not completion.
        # Record the actual *completed* fetch clock for downstream provenance.
        document["retrieved_at_utc"] = datetime.now(UTC).isoformat()
        return document

    def grid_task():
        return fetch_grid(active, datetime.now(UTC))

    errors = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {
            "jma": pool.submit(jma_task),
            "wave": pool.submit(wave_task),
            "grid_fallback": pool.submit(grid_task),
        }
        output = {}
        for name, future in tasks.items():
            try:
                output[name] = future.result()
            except Exception as exc:
                errors[name] = type(exc).__name__
    checked = datetime.now(UTC)
    regional = jma_as_nearby(output.get("jma"), active, checked)
    grid = output.get("grid_fallback") or {}
    forecasts = {code: regional.get(code) or grid.get(code)
                 for code in active if regional.get(code) or grid.get(code)}
    wave = output.get("wave")
    status = {
        "status": "ok" if forecasts or (wave and wave.get("races")) else "unavailable",
        "jma_grid_venues": len(regional),
        "grid_fallback_venues": len([c for c in forecasts if c not in regional]),
        "onsite_wave_snapshots_collected": len((wave or {}).get("races") or []),
        "onsite_wave_provider": (wave or {}).get("provider", {}).get("fetch_status", "unavailable"),
        "collection_completed_at_utc": checked.isoformat(),
        "errors": errors, "tide_current_applied": False,
        "all_sources_are_prediction_inputs_not_observed_race_outcomes": True,
    }
    return forecasts, wave, status


def wave_for_race(snapshot, venue_code, race_number, cutoff, at):
    """Accept only truly live, time-matched wave evidence with 3-min cutoff room."""
    if not isinstance(snapshot, dict) or not isinstance(venue_code, str):
        return None
    if at.tzinfo is None or cutoff.tzinfo is None:
        return None
    now = at.astimezone(UTC)
    event_date = cutoff.astimezone(JST).strftime("%Y-%m-%d")
    if (snapshot.get("schema") != "weather_lab.water_surface_monitor.v1"
            or snapshot.get("event_date") != event_date
            or (snapshot.get("provider") or {}).get("fetch_status") != "ok"
            or now >= cutoff.astimezone(UTC)-timedelta(minutes=3)):
        return None
    collected = _timestamp(snapshot.get("collected_at_utc"))
    if (collected is None or not timedelta(0) <= now-collected <= timedelta(minutes=6)
            or collected >= cutoff.astimezone(UTC)-timedelta(minutes=3)):
        return None
    race_key = event_date.replace("-", "") + f"{int(venue_code):02d}{race_number:02d}"
    expected_cutoff = cutoff.astimezone(JST).strftime("%H:%M")
    for row in snapshot.get("races") or []:
        if (not isinstance(row, dict) or row.get("race_code") != race_key
                or row.get("venue_code") != f"{int(venue_code):02d}"
                or row.get("race") != race_number
                or row.get("cutoff_jst") != expected_cutoff
                or row.get("freshness_status") != "fresh_snapshot"):
            continue
        capture = _timestamp(row.get("source_captured_at_jst"))
        observed = _timestamp(row.get("weather_observed_at_jst"))
        wave = (row.get("weather") or {}).get("wave_cm")
        if (capture is None or observed is None
                or type(wave) not in (int, float) or not 0 <= wave <= 150
                or not timedelta(0) <= now-capture <= MAX_WAVE_CAPTURE_AGE
                or not timedelta(0) <= now-observed <= MAX_WAVE_OBSERVATION_AGE
                or observed > capture + timedelta(minutes=2)
                or capture > collected + timedelta(seconds=30)
                or capture >= cutoff.astimezone(UTC)-timedelta(minutes=3)):
            return None
        return {
            "wave_height": float(wave),
            "wave_source": WAVE_SOURCE,
            "wave_site_observed": True,
            "wave_source_url": (snapshot.get("provider") or {}).get("url"),
            "wave_source_captured_at_jst": capture.astimezone(JST).isoformat(),
            "wave_observed_at_jst": observed.astimezone(JST).isoformat(),
            "wave_collected_at_utc": collected.isoformat(),
            "wave_evidence_quality": "fresh_pre_cutoff_onsite_snapshot",
            "tide_current_integrated": False,
        }
    return None
