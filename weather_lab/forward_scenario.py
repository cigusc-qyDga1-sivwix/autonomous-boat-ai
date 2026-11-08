"""Pre-cutoff weather scenario *research cues*, not a prediction model.

Consumes WEATHER LAB's independently timestamped on-site wave snapshot and
nearby JMA grid model forecast. No BOAT LAB imports, results, odds or tickets.
The first qualifying record per race is immutable and time-provenance checked.
No unverified head/tailwind, tide/current or lane advantages are inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "weather_lab.forward_weather_scenario.v1"
WAVE_SCHEMA = "weather_lab.water_surface_monitor.v1"
REGIONAL_SCHEMA = "weather_lab.regional_jma_forecast.v1"
JST = timezone(timedelta(hours=9))
MARGIN = timedelta(minutes=3)
WAVE_AGE = timedelta(minutes=20)
SOURCE_AGE = timedelta(minutes=15)
MODEL_AGE = timedelta(minutes=90)
VENUES = ("桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑",
          "津", "三国", "びわこ", "住之江", "尼崎", "鳴門", "丸亀", "児島",
          "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村")


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None


def number(value, lo, hi):
    return (float(value) if type(value) in (int, float) and
            math.isfinite(value) and lo <= value <= hi else None)


def build(wave: dict, regional: dict | None, now: datetime,
          previous: dict | None = None) -> tuple[dict, int]:
    if now.tzinfo is None:
        raise ValueError("Time must be timezone aware")
    at = now.astimezone(timezone.utc)
    if wave.get("schema") != WAVE_SCHEMA:
        raise ValueError("Invalid wave source")
    day = wave.get("event_date")
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Invalid event date")
    if now.astimezone(JST).date().isoformat() != day:
        raise ValueError("Do not backdate collection")
    collected = timestamp(wave.get("collected_at_utc"))
    if collected is None or not timedelta(0) <= at - collected <= SOURCE_AGE:
        raise ValueError("On-site collection heartbeat is stale")
    if previous is not None:
        if previous.get("schema") != SCHEMA or previous.get("event_date") != day or not isinstance(previous.get("records"), list):
            raise ValueError("Old scenario archive does not match today's data")
        records = list(previous["records"])
    else:
        records = []
    seen = {x.get("race_code") for x in records}
    # NEVER treat missing/unverified models as 0m/s, or use a later forecast.
    model_ok = (isinstance(regional, dict) and regional.get("schema") == REGIONAL_SCHEMA and
                regional.get("event_date") == day and
                regional.get("provider", {}).get("fetch_status") == "ok" and
                isinstance(regional.get("venues"), list) and len(regional["venues"]) == 24)
    retrieved = timestamp(regional.get("retrieved_at_utc")) if model_ok else None
    model_ok = bool(model_ok and retrieved is not None and
                    timedelta(0) <= at - retrieved <= MODEL_AGE)
    by_code = {v.get("code"): v for v in regional["venues"] if isinstance(v, dict)} if model_ok else {}
    new = 0
    if wave.get("provider", {}).get("fetch_status") not in ("ok", "ok_empty"):
        model_ok = False
    for row in wave.get("races", []) if isinstance(wave.get("races"), list) else []:
        if not model_ok or not isinstance(row, dict) or row.get("freshness_status") != "fresh_snapshot":
            continue
        code = row.get("race_code")
        if not isinstance(code, str) or not re.fullmatch(r"\d{12}", code) or not code.startswith(day.replace("-", "")) or code in seen:
            continue
        venue_code, race_no = code[8:10], int(code[10:12])
        if not (1 <= int(venue_code) <= 24 and 1 <= race_no <= 12 and venue_code != "03"):
            continue
        if row.get("venue_code") != venue_code or row.get("race") != race_no or row.get("venue") != VENUES[int(venue_code)-1]:
            continue
        clock = row.get("cutoff_jst")
        if not isinstance(clock, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
            continue
        cutoff = datetime.fromisoformat(day + "T" + clock + ":00+09:00").astimezone(timezone.utc)
        if at > cutoff - MARGIN:
            continue
        capture = timestamp(row.get("source_captured_at_jst"))
        observed = timestamp(row.get("weather_observed_at_jst"))
        wave_cm = number((row.get("weather") or {}).get("wave_cm"), 0, 150)
        if (capture is None or observed is None or wave_cm is None or
                not timedelta(0) <= at - capture <= SOURCE_AGE or
                not timedelta(0) <= at - observed <= WAVE_AGE or
                observed > capture + timedelta(minutes=2)):
            continue
        site = by_code.get(venue_code)
        options = []
        for hour in (site.get("hourly", []) if isinstance(site, dict) else []):
            dt = timestamp(hour.get("valid_at_jst")) if isinstance(hour, dict) else None
            speed = number(hour.get("wind_mps"), 0, 80) if isinstance(hour, dict) else None
            if dt is not None and speed is not None:
                diff = abs((dt-cutoff).total_seconds())
                if diff <= 3600:
                    options.append((diff, dt, speed))
        if not options:
            continue
        _, hour, wind = min(options, key=lambda item: (item[0], item[1]))
        # These are UNCALIBRATED alert thresholds, not probabilities or bets.
        flags = []
        if wind >= 6:
            flags.append("nearby_model_wind_ge_6mps")
        if wave_cm >= 5:
            flags.append("on_course_wave_ge_5cm")
        if len(flags) == 2:
            flags.append("wind_wave_joint_attention")
        attention = bool(flags)
        evidence = {
            "race_code": code, "venue_code": venue_code, "venue": row["venue"],
            "race": race_no, "cutoff_jst": clock, "recorded_at_utc": at.isoformat(),
            "regional_retrieved_at_utc": retrieved.isoformat(),
            "regional_valid_at_jst": hour.astimezone(JST).isoformat(),
            "nearby_model_wind_mps": wind,
            "regional_wind_is_observation": False,
            "wave_source_captured_at_jst": row["source_captured_at_jst"],
            "wave_observed_at_jst": row["weather_observed_at_jst"],
            "on_course_wave_cm": wave_cm,
            "wave_is_on_site_snapshot": True,
            "status": "research_attention" if attention else "research_baseline",
            "signals": flags,
            "scenarios_to_reconsider": (
                ["1コース逃げ切りの確実性", "センター・外の攻めが成立する条件",
                 "1Mでの差し・まくりと2・3着残存"] if attention else []),
            "headwind_tailwind": "unverified_not_inferred",
            "local_tide_current": "unavailable_not_inferred",
            "weather_probabilities_calibrated": False,
            "formal_prediction_modified": False,
            "bets_changed": False,
        }
        raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        evidence["evidence_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        records.append(evidence)
        seen.add(code)
        new += 1
    if previous and new == 0:
        return previous, 0
    records.sort(key=lambda x: x["race_code"])
    return ({
        "schema": SCHEMA, "event_date": day,
        "updated_at_utc": at.isoformat(),
        "rules": {
            "first_pre_cutoff_context_only": True,
            "cutoff_safety_margin_minutes": 3,
            "wave_age_minutes": 20, "source_age_minutes": 15,
            "regional_age_minutes": 90,
            "no_course_direction_or_tide_inference": True,
            "research_only_no_bet_changes": True,
            "thresholds_not_calibrated": True,
        },
        "records": records,
    }, new)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--regional", type=Path, required=True)
    p.add_argument("--previous", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    wave = json.loads(args.snapshot.read_text(encoding="utf-8"))
    region = json.loads(args.regional.read_text(encoding="utf-8")) if args.regional.is_file() else None
    prev = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous and args.previous.is_file() else None
    doc, count = build(wave, region, datetime.now(timezone.utc), prev)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"new_pre_cutoff_scenarios": count, "total_scenarios": len(doc["records"]),
                      "formal_prediction_modified": False}))


if __name__ == "__main__":
    main()
