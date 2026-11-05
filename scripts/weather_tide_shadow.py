"""Read-only weather / wave / tide evidence audit for BOAT LAB.

This module NEVER imports prediction functions, changes weights, or rewrites
pre-cutoff forecasts. The output is retrospective research evidence only.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
STALE_WEATHER_MINUTES = 20  # Research alert threshold, NOT calibrated.
TIDE_MAX_AGE_MINUTES = 90
SOURCE_STATUS = "research_only_not_formal_forecast"


def _number(value, minimum, maximum):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(value)
    except (ValueError, TypeError):
        return None
    return n if math.isfinite(n) and minimum <= n <= maximum else None


def _timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(JST) if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _race_cutoff(record):
    day = record.get("race_code", "")[:8]
    clock = record.get("cutoff_jst")
    if not re.fullmatch(r"\d{8}", day) or not isinstance(clock, str):
        return None
    try:
        return datetime.strptime(day + clock, "%Y%m%d%H:%M").replace(tzinfo=JST)
    except ValueError:
        return None


def _weather_timestamp(record):
    weather = record.get("weather") or {}
    clock = weather.get("observed_time_jst")
    cutoff = _race_cutoff(record)
    if not cutoff:
        return None
    # BoatraceCSV currently supplies HHMM, without timezone or calendar date.
    if isinstance(clock, str) and re.fullmatch(r"(?:[01]\d|2[0-3])[0-5]\d", clock):
        return cutoff.replace(hour=int(clock[:2]), minute=int(clock[2:]), second=0)
    # Full timestamps may also be supplied by an independently validated source.
    return _timestamp(clock)


def _freshness(record):
    obs, src, cutoff = (_weather_timestamp(record),
                        _timestamp(record.get("source_observed_jst")),
                        _race_cutoff(record))
    result = {"status": "unknown", "observed_at_jst": obs.isoformat() if obs else None,
              "source_observed_jst": src.isoformat() if src else None,
              "age_at_source_minutes": None, "age_at_cutoff_minutes": None,
              "alert_threshold_minutes": STALE_WEATHER_MINUTES}
    if not obs or not src or not cutoff or src > cutoff or obs > src:
        return result
    age = (src - obs).total_seconds() / 60.0
    result.update(status="stale" if age > STALE_WEATHER_MINUTES else "fresh",
                  age_at_source_minutes=round(age, 1),
                  age_at_cutoff_minutes=round((cutoff-obs).total_seconds()/60, 1))
    return result


def _wind_orientation(record):
    """Never decode an unverified provider direction code as true bearing."""
    weather = record.get("weather") or {}
    source_code = weather.get("wind_direction_number")
    raw = record.get("research_verified_geometry") or {}
    if (raw.get("wind_bearing_verified") is not True or
            raw.get("start_to_first_mark_bearing_verified") is not True):
        return {"status": "unverified_geometry", "raw_provider_code": source_code,
                "wind_relative_to_start": None, "headwind_component_mps": None}
    wind_from = _number(raw.get("wind_from_true_degrees"), 0, 360)
    direction = _number(raw.get("start_to_first_mark_true_degrees"), 0, 360)
    speed = _number(weather.get("wind_mps"), 0, 70)
    if wind_from is None or direction is None or speed is None:
        return {"status": "invalid_verified_values", "raw_provider_code": source_code,
                "wind_relative_to_start": None, "headwind_component_mps": None}
    delta = ((wind_from-direction+180) % 360)-180
    component = speed * math.cos(math.radians(delta))
    kind = "headwind" if abs(delta) <= 45 else "tailwind" if abs(delta) >= 135 else "crosswind"
    return {"status": "geometry_verified", "raw_provider_code": source_code,
            "wind_relative_to_start": kind,
            "headwind_component_mps": round(component, 2),
            "crosswind_component_abs_mps": round(abs(speed*math.sin(math.radians(delta))), 2),
            "note": "Geometric components only; no inferred lane advantage."}


def _tide_trend(sample, cutoff):
    """Tide stage only, never infer water current from tide height."""
    missing = {"status": "unavailable", "stage": None, "change_cm_per_hour": None,
               "current_direction": "unknown"}
    if not sample or not cutoff:
        return missing
    if (sample.get("venue_station_mapping_verified") is not True or
            not sample.get("station_id") or not sample.get("source_url") or
            sample.get("kind") not in ("observed", "astronomical_prediction") or
            not sample.get("datum")):
        return {**missing, "status": "unverified_station_or_datum"}
    captured = _timestamp(sample.get("captured_at_utc"))
    if not captured or captured > cutoff:
        return {**missing, "status": "capture_time_unverified_or_late"}
    points = []
    for point in sample.get("points", []):
        when = _timestamp(point.get("time_jst")) if isinstance(point, dict) else None
        level = _number(point.get("level_cm"), -2000, 2000) if isinstance(point, dict) else None
        if when is not None and level is not None and when <= cutoff:
            points.append((when, level))
    points.sort()
    if len(points) < 2:
        return {**missing, "status": "insufficient_pre_cutoff_points"}
    (a, av), (b, bv) = points[-2], points[-1]
    minutes = (b-a).total_seconds()/60
    age = (cutoff-b).total_seconds()/60
    if minutes < 5 or minutes > 120 or age > TIDE_MAX_AGE_MINUTES:
        return {**missing, "status": "stale_or_invalid_interval"}
    rate = (bv-av)*60/minutes
    stage = "rising" if rate > 0.5 else "falling" if rate < -0.5 else "near_level"
    return {"status": "research_valid_not_current", "stage": stage,
            "change_cm_per_hour": round(rate, 2),
            "latest_level_cm": bv, "station_id": sample["station_id"],
            "datum": sample["datum"], "kind": sample["kind"],
            "captured_at_utc": sample["captured_at_utc"],
            "latest_sample_age_minutes": round(age, 1),
            "source_url": sample["source_url"], "current_direction": "unknown"}


def analyze(record, tide_sample=None):
    """Return explanatory features without any bets, scores, or win probabilities."""
    weather = record.get("weather") or {}
    wind = _number(weather.get("wind_mps"), 0, 70)
    wave = _number(weather.get("wave_cm"), 0, 150)
    freshness = _freshness(record)
    return {
        "race_code": record.get("race_code"),
        "venue": record.get("venue"),
        "race": record.get("race"),
        "cutoff_jst": record.get("cutoff_jst"),
        "source_status": SOURCE_STATUS,
        "weather": {"wind_mps": wind, "wave_cm": wave,
                    "wind_direction_code_unmapped": weather.get("wind_direction_number"),
                    "freshness": freshness,
                    "wind_orientation": _wind_orientation(record),
                    "wind_band_uncalibrated": ("missing" if wind is None else
                        "strong" if wind >= 8 else "moderate" if wind >= 4 else "low"),
                    "wave_band_uncalibrated": ("missing" if wave is None else
                        "high" if wave >= 8 else "moderate" if wave >= 4 else "low")},
        "tide": _tide_trend(tide_sample, _race_cutoff(record)),
        "forecast_integration": "none",
        "warning": "No betting recommendation: observation timing and waterbody effects require validation."
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only weather/wave/tide retrospective audit")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--archive", help="Optional research JSON location")
    parser.add_argument("--tide-samples", help="Optional race_code keyed, independently verified tide JSON")
    parser.add_argument("--output", help="Optional research report path; never app/data/live")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("invalid ISO day")
    archive = Path(args.archive or f"app/data/exhibition/{args.date}.json")
    source = json.loads(archive.read_text(encoding="utf-8"))
    if source.get("event_date") != args.date or not isinstance(source.get("records"), list):
        parser.error("archive date or records mismatch")
    tide = json.loads(Path(args.tide_samples).read_text(encoding="utf-8")) if args.tide_samples else {}
    if not isinstance(tide, dict):
        parser.error("tide samples must be keyed by race_code")
    rows = [analyze(r, tide.get(r.get("race_code"))) for r in source["records"]]
    result = {"schema": "boatlabs.weather_tide_research.v0.1",
              "event_date": args.date, "source_path": str(archive),
              "source_status": SOURCE_STATUS, "formal_predictions_changed": False,
              "records": rows,
              "summary": {"races": len(rows),
                          "stale_weather": sum(r["weather"]["freshness"]["status"] == "stale" for r in rows),
                          "unknown_wind_geometry": sum(r["weather"]["wind_orientation"]["status"] != "geometry_verified" for r in rows),
                          "tide_unavailable": sum(r["tide"]["status"] != "research_valid_not_current" for r in rows)}}
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output).resolve()
        forbidden_root = Path("app/data").resolve()
        if target == archive.resolve() or target.is_relative_to(forbidden_root):
            parser.error("cannot overwrite source archives or anything under app/data")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return result


if __name__ == "__main__":
    main()
