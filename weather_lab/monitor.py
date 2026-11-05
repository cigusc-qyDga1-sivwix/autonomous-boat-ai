"""WEATHER LAB v0.1: independent, read-only water-surface weather monitor.

This is deterministic source collection and quality monitoring, not a trained AI.
It never imports BOAT LAB prediction code or writes to app/data/.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
SCHEMA = "weather_lab.water_surface_monitor.v1"
SOURCE_ROOT = "https://boatracecsv.github.io/data/previews/sui"
WEATHER_AGE_ALERT_MINUTES = 20  # Research-only, not calibrated.
SOURCE_AGE_ALERT_MINUTES = 15   # Research-only, not calibrated.
VENUES = (
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑",
    "津", "三国", "びわこ", "住之江", "尼崎", "鳴門", "丸亀", "児島",
    "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村",
)


def _iso_datetime(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _num(value, low, high, integer=False):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
        if not math.isfinite(number) or not low <= number <= high:
            return None
        if integer:
            return int(number) if number.is_integer() else None
        return number
    except (TypeError, ValueError, OverflowError):
        return None


def _observed_at(day, clock, captured):
    """The source supplies HHMM without a date; the race day is an assumption."""
    if not isinstance(clock, str) or not re.fullmatch(r"(?:[01]\d|2[0-3])[0-5]\d", clock):
        return None
    value = datetime.combine(day, datetime.min.time(), JST).replace(
        hour=int(clock[:2]), minute=int(clock[2:]))
    if value > captured.astimezone(JST) + timedelta(minutes=2):
        return None
    return value


def _row(record, day, now, invalid):
    code = record.get("レースコード", "")
    if not re.fullmatch(r"\d{12}", code) or code[:8] != day.strftime("%Y%m%d"):
        invalid["invalid_race_code"] += 1
        return None
    venue, race = int(code[8:10]), int(code[10:12])
    if not 1 <= venue <= 24 or not 1 <= race <= 12:
        invalid["out_of_range_venue_or_race"] += 1
        return None
    source_at = _iso_datetime(record.get("取得日時"))
    if not source_at or source_at.astimezone(JST).date() != day:
        invalid["invalid_or_wrong_day_capture_timestamp"] += 1
        return None
    if source_at > now + timedelta(seconds=30):
        invalid["future_source_timestamp"] += 1
        return None
    observation = _observed_at(day, record.get("気象観測時刻", ""), source_at)
    wind = _num(record.get("風速(m)"), 0, 70)
    wave = _num(record.get("波の高さ(cm)"), 0, 150)
    raw_direction = _num(record.get("風向"), 0, 360, integer=True)
    air = _num(record.get("気温(℃)"), -40, 60)
    water = _num(record.get("水温(℃)"), -10, 45)
    weather_code = _num(record.get("天候"), 0, 100, integer=True)
    captured_age = round((now - source_at).total_seconds() / 60, 1)
    observed_age = (round((now - observation.astimezone(UTC)).total_seconds() / 60, 1)
                    if observation else None)
    if wind is None or wave is None:
        status = "incomplete_values"
    elif observation is None or observed_age is None or observed_age < -0.5:
        status = "observation_time_unverified"
    elif observed_age > WEATHER_AGE_ALERT_MINUTES:
        status = "stale_observation"
    elif captured_age > SOURCE_AGE_ALERT_MINUTES:
        status = "stale_source_capture"
    else:
        status = "fresh_snapshot"
    calm = wind == 0 and raw_direction is None
    return {
        "race_code": code, "venue_code": f"{venue:02d}", "venue": VENUES[venue - 1],
        "race": race, "cutoff_jst": record.get("締切時刻"),
        "weather": {
            "wind_mps": wind, "wind_direction_raw_code": raw_direction,
            "wind_direction_status": "calm_undefined" if calm else
                                     "present_unmapped" if raw_direction is not None else
                                     "missing_noncalm",
            "wave_cm": wave, "weather_raw_code": weather_code,
            "air_c": air, "water_c": water,
        },
        "source_captured_at_jst": source_at.astimezone(JST).isoformat(),
        "weather_observed_at_jst": observation.isoformat() if observation else None,
        "weather_date_inferred_from_race_day": observation is not None,
        "source_age_minutes": captured_age,
        "weather_age_minutes": observed_age,
        "freshness_status": status,
        "forecast_eligible": False,
    }


def build(csv_text, at, day, *, source_url=None, fetch_error=None):
    """Always produce all 24 venue statuses; no forecast or probability outputs."""
    if at.tzinfo is None:
        raise ValueError("Monitor clock must be timezone-aware")
    now = at.astimezone(UTC)
    if not isinstance(day, date):
        raise ValueError("day must be a date")
    url = source_url or f"{SOURCE_ROOT}/{day:%Y/%m/%d}.csv"
    invalid = Counter()
    latest = {}
    if fetch_error is None:
        try:
            for record in csv.DictReader(io.StringIO(csv_text or "")):
                row = _row(record, day, now, invalid)
                if row is None:
                    continue
                key = row["race_code"]
                if key not in latest or row["source_captured_at_jst"] > latest[key]["source_captured_at_jst"]:
                    latest[key] = row
        except (csv.Error, TypeError, UnicodeError):
            fetch_error = "invalid_csv"
            latest.clear()
    races = sorted(latest.values(), key=lambda r: (r["venue_code"], r["race"]))
    venues = []
    for i, name in enumerate(VENUES, start=1):
        items = [r for r in races if r["venue_code"] == f"{i:02d}"]
        newest = max(items, key=lambda r: r["source_captured_at_jst"]) if items else None
        venues.append({
            "code": f"{i:02d}", "name": name,
            "boat_lab_prediction_in_scope": i != 3,
            "monitor_status": "provider_unavailable" if fetch_error else
                              "no_race_snapshot" if not items else
                              newest["freshness_status"],
            "race_snapshots": len(items),
            "latest_race_code": newest["race_code"] if newest else None,
            "latest_weather_observed_at_jst": newest["weather_observed_at_jst"] if newest else None,
            "latest_source_captured_at_jst": newest["source_captured_at_jst"] if newest else None,
            "tide": {"status": "not_integrated", "stage": None,
                     "height_cm": None, "current_direction": None},
        })
    status_counts = Counter(r["freshness_status"] for r in races)
    return {
        "schema": SCHEMA,
        "event_date": day.isoformat(),
        "collected_at_utc": now.isoformat(),
        "provider": {"name": "BoatraceCSV", "type": "previews/sui",
                     "url": url, "fetch_status": "unavailable" if fetch_error else
                                            "ok" if races else "ok_empty",
                     "fetch_error_type": fetch_error},
        "scope": {"venues_monitored": 24, "forecast_scope_excludes_edogawa": True,
                  "race_based_snapshot_not_continuous_sensor": True,
                  "no_formal_forecast_integration": True},
        "freshness_thresholds_research_only": {
            "weather_age_minutes": WEATHER_AGE_ALERT_MINUTES,
            "source_capture_age_minutes": SOURCE_AGE_ALERT_MINUTES},
        "summary": {
            "race_snapshots": len(races),
            "venues_with_snapshots": sum(v["race_snapshots"] > 0 for v in venues),
            "fresh_races": status_counts["fresh_snapshot"],
            "stale_weather_races": status_counts["stale_observation"],
            "stale_capture_races": status_counts["stale_source_capture"],
            "incomplete_races": status_counts["incomplete_values"],
            "time_unverified_races": status_counts["observation_time_unverified"],
            "calm_without_direction": sum(r["weather"]["wind_direction_status"] == "calm_undefined"
                                          for r in races),
            "rejected_rows": dict(invalid),
        },
        "venues": venues, "races": races,
        "warnings": [
            "A snapshot is NOT a continuously sampled weather station. No racing venues may be open now.",
            "Observed HHMM date was inferred from the race day; never use it to backdate live acquisition.",
            "Wind direction codes are raw source values, not headwind/tailwind.",
            "Tide level/current not obtained. Do not infer a numeric value or stage.",
            "BOAT LAB's formal predictions, frozen hashes and settlements are unchanged.",
        ],
    }


def download(day):
    url = f"{SOURCE_ROOT}/{day:%Y/%m/%d}.csv"
    req = Request(url, headers={"User-Agent": "WEATHER-LAB-research-monitor/0.1"})
    try:
        with urlopen(req, timeout=12) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                return "", url, "source_too_large"
            return raw.decode("utf-8-sig"), url, None
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return "", url, type(exc).__name__
    except UnicodeError:
        return "", url, "source_encoding_error"


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standalone weather monitor, no forecasts")
    parser.add_argument("--date", help="JST YYYY-MM-DD; live mode restricted to today")
    parser.add_argument("--fixture", type=Path, help="Offline CSV test fixture")
    parser.add_argument("--now-iso", help="Offline test clock only")
    parser.add_argument("--out-dir", type=Path, default=Path("weather_lab/data"))
    args = parser.parse_args(argv)
    if args.now_iso and not args.fixture:
        parser.error("--now-iso requires --fixture")
    now = _iso_datetime(args.now_iso) if args.now_iso else datetime.now(UTC)
    if now is None:
        parser.error("invalid test clock")
    today = now.astimezone(JST).date()
    try:
        day = date.fromisoformat(args.date) if args.date else today
    except ValueError:
        parser.error("invalid date")
    if not args.fixture and day != today:
        parser.error("live monitor cannot backdate or forecast another day")
    if args.fixture:
        source = args.fixture.read_text(encoding="utf-8-sig")
        url, error = "fixture://offline-not-live", None
    else:
        source, url, error = download(day)
    snapshot = build(source, now, day, source_url=url, fetch_error=error)
    # Never write to BOAT LAB inputs. Allow custom fixture output in temp dirs.
    target = args.out_dir.resolve()
    forbidden = Path("app/data").resolve()
    if target == forbidden or target.is_relative_to(forbidden):
        parser.error("WEATHER LAB cannot write into BOAT LAB app/data")
    write_json(target / "latest.json", snapshot)
    if error is None:
        write_json(target / f"{day.isoformat()}.json", snapshot)
    print(json.dumps({"schema": SCHEMA, "event_date": day.isoformat(),
                      "source_status": snapshot["provider"]["fetch_status"],
                      **snapshot["summary"]}, ensure_ascii=False))
    return snapshot


if __name__ == "__main__":
    main()
