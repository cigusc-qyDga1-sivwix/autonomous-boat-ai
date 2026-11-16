"""Read-only, pre-cutoff on-site weather evidence from BoatraceCSV previews/sui.

Separate from WEATHER LAB's wave-only formal bridge. Observations and raw wind
direction codes are evidence, NEVER headwind/tailwind probabilities or ticket
inputs. The provider snapshots are collected ~5 min before the racing cutoff.
No post-cutoff source data or historical retroactive labels are admitted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from weather_lab.monitor import download as download_sui

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")
SCHEMA = "boatlabs.site-weather-precursor-evidence.v1"
MAX_CAPTURE_AGE = timedelta(minutes=15)
MAX_OBSERVATION_AGE = timedelta(minutes=20)
MARGIN = timedelta(minutes=2)
# 江戸川 remains outside BOAT LAB's forecast/research universe.
EXCLUDED_CODE = 3
VENUES = ("桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
          "蒲郡", "常滑", "津", "三国", "びわこ", "住之江", "尼崎",
          "鳴門", "丸亀", "児島", "宮島", "徳山", "下関", "若松",
          "芦屋", "福岡", "唐津", "大村")


def _time(text):
    if not isinstance(text, str):
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return value if value.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _clock(day, text):
    if not isinstance(text, str) or not re.fullmatch(r"(?:[01]\d|2[0-3])[0-5]\d", text):
        return None
    return datetime(day.year, day.month, day.day, int(text[:2]), int(text[2:]), tzinfo=JST)


def _amount(value, low, high):
    if value is None or not str(value).strip():
        return None
    try:
        amount = float(value)
        return amount if math.isfinite(amount) and low <= amount <= high else None
    except (ValueError, TypeError, OverflowError):
        return None


def parse(csv_text, day, now, *, source_url):
    """Admit source-confirmed fresh weather, never missing-as-zero."""
    if not isinstance(day, date) or now.tzinfo is None:
        raise ValueError("Day and aware clock required")
    if day != now.astimezone(JST).date():
        raise ValueError("Live monitor cannot backdate or forecast")
    evidence = {}
    counts = {}
    if not csv_text:
        return evidence, {"source_missing": 1}
    stream = io.StringIO(csv_text.lstrip("\ufeff"))
    for row in csv.DictReader(stream):
        def reject(reason):
            counts[reason] = counts.get(reason, 0) + 1
        ident = str(row.get("レースコード") or "")
        if not re.fullmatch(r"\d{12}", ident) or ident[:8] != day.strftime("%Y%m%d"):
            reject("wrong_race_code")
            continue
        venue, race = int(ident[8:10]), int(ident[10:12])
        if not 1 <= venue <= 24 or not 1 <= race <= 12 or venue == EXCLUDED_CODE:
            reject("venue_out_of_scope")
            continue
        if (row.get("レース日") != day.isoformat() or
            row.get("レース場") != f"{venue:02d}" or row.get("レース回") != f"{race:02d}R"):
            reject("identity_mismatch")
            continue
        cutoff_clock = row.get("締切時刻")
        if not isinstance(cutoff_clock, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cutoff_clock):
            reject("invalid_cutoff")
            continue
        cutoff = datetime(day.year, day.month, day.day, int(cutoff_clock[:2]),
                          int(cutoff_clock[3:]), tzinfo=JST)
        captured = _time(row.get("取得日時"))
        observed = _clock(day, row.get("気象観測時刻"))
        if not captured or not observed or captured.astimezone(JST).date() != day:
            reject("observation_clock_missing")
            continue
        # The timestamp is not evidence of what was observable after cutoff.
        if (not timedelta(0) <= now - captured <= MAX_CAPTURE_AGE or
            not timedelta(0) <= captured - observed <= MAX_OBSERVATION_AGE or
            captured > cutoff - MARGIN or observed > cutoff - MARGIN or
            now >= cutoff - MARGIN):
            reject("stale_or_post_cutoff")
            continue
        wind = _amount(row.get("風速(m)"), 0, 65)
        wave = _amount(row.get("波の高さ(cm)"), 0, 150)
        if wind is None and wave is None:
            reject("wind_and_wave_missing")
            continue
        raw_direction = str(row.get("風向") or "").strip()
        if not raw_direction or len(raw_direction) > 12 or any(ord(c) < 32 for c in raw_direction):
            raw_direction = None
        data = {
            "venue_code": f"{venue:02d}", "venue": VENUES[venue - 1], "race": race,
            "cutoff_jst": cutoff_clock, "race_code": ident,
            "wind_speed_mps": wind, "wind_direction_raw": raw_direction,
            "wave_height_cm": wave,
            "wind_direction_status": "raw_code_unmapped" if raw_direction is not None else "unavailable",
            "relative_wind_verified": False, "tide_verified": False,
            "source": "boatracecsv_previews_sui",
            "source_url": source_url,
            "source_captured_at_jst": captured.astimezone(JST).isoformat(),
            "observed_at_jst": observed.isoformat(),
            "source_acquired_before_cutoff": True,
            "formal_input": False, "research_only": True,
        }
        data["evidence_sha256"] = hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        key = f"{day.isoformat()}|{VENUES[venue-1]}|{race}"
        prior = evidence.get(key)
        if prior is None or _time(data["source_captured_at_jst"]) > _time(prior["source_captured_at_jst"]):
            evidence[key] = data
        elif prior["source_captured_at_jst"] == data["source_captured_at_jst"] and prior["evidence_sha256"] != data["evidence_sha256"]:
            evidence.pop(key, None)
            reject("duplicate_capture_conflict")
    return evidence, counts



def frozen_preview_fallback(document, day):
    """Previous model's already-frozen weather values, NEVER a timed site sensor.

    The provider's wind source is from BOATRACE preview, but its original
    weather observation timestamp was not supplied. The freeze is proof of
    pre-race availability only, not proof of a fresh 5-minute measurement.
    """
    if not isinstance(document, dict) or document.get("mode") != "auto-live" or document.get("event_date") != day.isoformat():
        return {}
    rows = document.get("forecast_races")
    if not isinstance(rows, list):
        return {}
    found = {}
    for r in rows[:288]:
        if not isinstance(r, dict) or r.get("phase") != "exhibition" or r.get("ticket_status") != "formal":
            continue
        venue, race = r.get("venue"), r.get("race")
        if venue not in VENUES or venue == "江戸川" or type(race) is not int or not 1 <= race <= 12:
            continue
        clock = r.get("cutoff_jst")
        if not isinstance(clock, str) or not re.fullmatch(r"(?:[01]\\d|2[0-3]):[0-5]\\d", clock):
            continue
        cutoff = datetime(day.year, day.month, day.day, int(clock[:2]), int(clock[3:]), tzinfo=JST)
        frozen = _time(r.get("frozen_at_utc"))
        if frozen is None or frozen >= cutoff - MARGIN or frozen.astimezone(JST).date() != day:
            continue
        weather = r.get("weather_used")
        if not isinstance(weather, dict) or weather.get("site_observed") is not True or weather.get("wind_source") != "boatrace_preview":
            continue
        speed = _amount(weather.get("wind_speed"), 0, 65)
        wave = _amount(weather.get("wave_height"), 0, 150)
        if speed is None and wave is None:
            continue
        direction = weather.get("wind_direction_number")
        direction = (str(int(direction)) if type(direction) in (int, float) and
                     math.isfinite(direction) and 0 <= direction <= 999 and
                     direction == int(direction) else None)
        source_sha = r.get("sha256")
        if not isinstance(source_sha, str) or not re.fullmatch("[0-9a-f]{64}", source_sha):
            continue
        code = VENUES.index(venue) + 1
        data = {
            "venue_code": f"{code:02d}", "venue": venue, "race": race,
            "cutoff_jst": clock, "race_code": f"{day:%Y%m%d}{code:02d}{race:02d}",
            "wind_speed_mps": speed, "wind_direction_raw": direction,
            "wave_height_cm": wave,
            "wind_direction_status": "raw_code_unmapped" if direction is not None else "unavailable",
            "relative_wind_verified": False, "tide_verified": False,
            "source": "boatrace_preview_frozen_snapshot",
            "source_url": None, "source_captured_at_jst": None,
            "observed_at_jst": None, "snapshot_frozen_at_utc": frozen.astimezone(UTC).isoformat(),
            "original_observation_clock_verified": False,
            "source_snapshot_sha256": source_sha,
            "source_acquired_before_cutoff": False,
            "source_value_frozen_before_cutoff": True,
            "formal_input": False, "research_only": True,
        }
        data["evidence_sha256"] = hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        key = f"{day.isoformat()}|{venue}|{race}"
        prior = found.get(key)
        if prior is None or _time(data["snapshot_frozen_at_utc"]) > _time(prior["snapshot_frozen_at_utc"]):
            found[key] = data
    return found

def merge_document(current, prior, day, now, *, source_url, error=None, rejects=None):
    if now.tzinfo is None or day != now.astimezone(JST).date():
        raise ValueError("Live day only")
    past = prior.get("records", {}) if isinstance(prior, dict) and prior.get("schema") == SCHEMA and prior.get("event_date") == day.isoformat() else {}
    combined = dict(past)
    conflicts = {}
    for key, value in current.items():
        original = combined.get(key)
        if original is not None and original.get("evidence_sha256") != value["evidence_sha256"]:
            # An independently timestamped provider reading may replace the
            # less-proven frozen-forecast fallback; keep the prior SHA in audit.
            if (original.get("source") == "boatrace_preview_frozen_snapshot"
                    and value.get("source") == "boatracecsv_previews_sui"
                    and value.get("wind_speed_mps") is not None):
                value = {**value, "supersedes_research_sha256": original.get("evidence_sha256")}
            elif (original.get("source") == "boatracecsv_previews_sui"
                  and value.get("source") == "boatrace_preview_frozen_snapshot"):
                continue
            else:
                conflicts[key] = {"prior_sha256": original.get("evidence_sha256"),
                                  "incoming_sha256": value["evidence_sha256"]}
                continue
        combined[key] = value
    return {
        "schema": SCHEMA, "event_date": day.isoformat(),
        "checked_at_utc": now.astimezone(UTC).isoformat(),
        "source_url": source_url, "provider_status": "ok" if error is None else error,
        "admitted_this_check": len(current), "saved_races": len(combined),
        "records": dict(sorted(combined.items())), "conflicts_this_check": conflicts,
        "rejection_counts": rejects or {},
        "formal_model_changed": False,
        "wind_direction_policy": "raw_only_no_venue_relative_conversion",
        "tide_policy": "not_integrated_requires_station_mapping",
        "notes": [
            "Site wind/wave raw evidence is a separate, read-only research feed.",
            "Source observed time and captured time must both predate the cutoff.",
            "Never infer racecourse relative wind or local tide from unverified codes.",
            "No result, payout, post-race wind, or model output is used.",
        ],
    }


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == encoded:
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def run(out_dir=Path("app/data/weather-research"), now=None, downloader=download_sui, frozen_path=None):
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Aware UTC now required")
    day = now.astimezone(JST).date()
    raw, url, error = downloader(day)
    captured = datetime.now(UTC) if downloader is download_sui else now
    if captured.astimezone(JST).date() != day:
        raise ValueError("JST date changed during capture")
    records, rejected = parse(raw, day, captured, source_url=url)
    frozen = {}
    if frozen_path is not None and frozen_path.exists():
        try:
            frozen = frozen_preview_fallback(json.loads(frozen_path.read_text(encoding="utf-8")), day)
        except (OSError, ValueError):
            pass
    # Source-timed SUI wins when both fields exist; the frozen preview is only
    # a correctly labeled fallback, never disguised as a 5-min measurement.
    records = {**frozen, **records}
    target = out_dir / f"{day.isoformat()}.json"
    try:
        prior = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except (OSError, ValueError):
        prior = {}
    doc = merge_document(records, prior, day, captured, source_url=url, error=error, rejects=rejected)
    doc["frozen_preview_fallback_found"] = len(frozen)
    doc["direct_sui_provenance_count"] = sum(v["source"] == "boatracecsv_previews_sui" for v in records.values())
    doc["frozen_preview_only_count"] = sum(v["source"] == "boatrace_preview_frozen_snapshot" for v in doc["records"].values())
    _write(target, doc)
    _write(out_dir / "latest.json", doc)
    return doc


def main():
    parser = argparse.ArgumentParser(description="Pre-cutoff on-site wind/wave capture; no formal forecast effects")
    parser.add_argument("--out-dir", type=Path, default=Path("app/data/weather-research"))
    args = parser.parse_args()
    d = run(out_dir=args.out_dir, frozen_path=Path("app/data/live/latest.json"))
    print(json.dumps({"date": d["event_date"], "source": d["provider_status"],
                      "admitted": d["admitted_this_check"], "saved": d["saved_races"],
                      "conflicts": len(d["conflicts_this_check"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
