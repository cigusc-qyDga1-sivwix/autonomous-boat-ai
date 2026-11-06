"""Freeze weather evidence *as observed before cutoff* for future comparison.

This module NEVER writes or imports BOAT LAB's model, bets, payout or app/data.
Only data collected while an actual race has not passed the 3-minute production
margin may enter the forward archive. Later passes must preserve first witness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
SCHEMA = "weather_lab.forward_weather_evidence.v1"
MONITOR_SCHEMA = "weather_lab.water_surface_monitor.v1"
SAFE_MARGIN = timedelta(seconds=180)
SOURCE_AGE = timedelta(minutes=15)
OBSERVATION_AGE = timedelta(minutes=20)


def _dt(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else None


def _good_measurement(row, collection):
    if row.get("freshness_status") != "fresh_snapshot":
        return False
    w = row.get("weather") or {}
    for key in ("wave_cm",):
        value = w.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0 <= value < 1000):
            return False
    capture = _dt(row.get("source_captured_at_jst"))
    observed = _dt(row.get("weather_observed_at_jst"))
    if not capture or not observed:
        return False
    # Validate the stored freshness decision again; do not trust a text flag.
    if not (timedelta(0) <= collection - capture <= SOURCE_AGE):
        return False
    if not (timedelta(0) <= collection - observed <= OBSERVATION_AGE):
        return False
    if observed > capture + timedelta(minutes=2):
        return False
    return True


def freeze(snapshot: dict, previous: dict | None = None) -> tuple[dict, int]:
    if snapshot.get("schema") != MONITOR_SCHEMA:
        raise ValueError("Unexpected weather monitoring schema")
    day = snapshot.get("event_date")
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Invalid day")
    collection = _dt(snapshot.get("collected_at_utc"))
    if collection is None or collection.astimezone(JST).strftime("%Y-%m-%d") != day:
        raise ValueError("Collection clock does not belong to race day (JST)")
    if snapshot.get("provider", {}).get("fetch_status") not in ("ok", "ok_empty", "unavailable"):
        raise ValueError("Unknown provider status")
    if previous:
        if previous.get("schema") != SCHEMA or previous.get("event_date") != day or not isinstance(previous.get("records"), list):
            raise ValueError("Mismatched forward archive; do not overwrite")
        records = list(previous["records"])
    else:
        records = []
    seen = {r["race_code"] for r in records}
    new = 0
    for row in snapshot.get("races", []):
        if not isinstance(row, dict):
            continue
        code = row.get("race_code")
        if not isinstance(code, str) or not re.fullmatch(r"\d{12}", code) or code[:8] != day.replace("-", ""):
            continue
        if code in seen or row.get("venue_code") != code[8:10] or row.get("race") != int(code[10:12]):
            continue
        clock = row.get("cutoff_jst")
        if not isinstance(clock, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
            continue
        cutoff = datetime.fromisoformat(day + "T" + clock + ":00+09:00")
        if collection > cutoff - SAFE_MARGIN or not _good_measurement(row, collection):
            continue
        w = row["weather"]
        captured = {
            "race_code": code, "venue_code": row["venue_code"],
            "venue": row.get("venue"), "race": row["race"],
            "cutoff_jst": clock,
            "collector_received_at_utc": collection.astimezone(timezone.utc).isoformat(),
            "source_captured_at_jst": row["source_captured_at_jst"],
            "weather_observed_at_jst": row["weather_observed_at_jst"],
            "weather": {"wave_cm": w["wave_cm"]},
            "advisory_signals": ((row.get("weather_advisory") or {}).get("signals") or []),
            "onsite_measurement_scope": "wave_height_only",
            "forecast_available_at_collection": False,
            "prediction_sha": None,
            "weather_effect_on_predictions": "not_applied",
        }
        raw = json.dumps(captured, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        captured["weather_evidence_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        records.append(captured)
        seen.add(code)
        new += 1
    if previous and new == 0:
        return previous, 0
    records.sort(key=lambda r: r["race_code"])
    return {
        "schema": SCHEMA,
        "event_date": day,
        "created_at_utc": (previous or {}).get("created_at_utc", collection.astimezone(timezone.utc).isoformat()),
        "updated_at_utc": collection.astimezone(timezone.utc).isoformat(),
        "rules": {
            "collection_before_cutoff_seconds": int(SAFE_MARGIN.total_seconds()),
            "max_source_age_minutes": int(SOURCE_AGE.total_seconds() // 60),
            "max_weather_age_minutes": int(OBSERVATION_AGE.total_seconds() // 60),
            "first_pre_cutoff_observation_only": True,
            "historical_predictions_immutable": True,
            "prediction_recalculation": False,
            "weather_from_official_venue_observation_not_regional_forecast": True,
            "new_records_on_site_wave_only": True,
            "previous_legacy_records_preserved_unchanged": True,
        },
        "records": records,
    }, new


def main(argv=None):
    parser = argparse.ArgumentParser(description="Freeze truly pre-cutoff weather witnesses only")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    current = json.loads(args.snapshot.read_text(encoding="utf-8"))
    old = None
    if args.previous and args.previous.exists() and args.previous.stat().st_size:
        old = json.loads(args.previous.read_text(encoding="utf-8"))
    doc, added = freeze(current, old)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"event_date": doc["event_date"], "frozen": len(doc["records"]),
                      "newly_frozen": added, "formal_forecast_modified": False}))
    return doc


if __name__ == "__main__":
    main()
