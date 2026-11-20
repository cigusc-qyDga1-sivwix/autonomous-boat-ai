"""Read-only, pre-cutoff audit: BOATRACE official beforeinfo vs BOAT LAB Open API.

No result/payout/odds, no model input injection and no modification of
formal picks, SHA or performance. Source observations are NOT guaranteed to
share the same observation time; matching values do not prove live equality.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html import unescape
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")
SCHEMA = "weather_lab.official_openapi_pre_cutoff_diff.v1"
OPEN_API = "https://boatraceopenapi.github.io/api/v1"
OFFICIAL = "https://www.boatrace.jp/owpc/pc/race/beforeinfo"
# Compare near the requested five-minute lead, with room for best-effort cron.
WINDOW_MINUTES = (5, 20)
MAX_OBSERVATION_AGE = timedelta(minutes=20)
FIELDS = ("wind_speed", "wind_direction_number", "wave_height")


def _number(x, low, high, integer=False):
    if isinstance(x, bool) or not isinstance(x, (float, int, str)):
        return None
    try:
        n = float(x)
    except ValueError:
        return None
    if not math.isfinite(n) or not low <= n <= high:
        return None
    if integer and not n.is_integer():
        return None
    return int(n) if integer else n


def _iso(raw):
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo is not None else None
    except (ValueError, AttributeError, TypeError):
        return None


def official_url(event: date, venue: int, race: int) -> str:
    if not 1 <= venue <= 24 or not 1 <= race <= 12:
        raise ValueError("Invalid venue/race")
    return f"{OFFICIAL}?rno={race}&jcd={venue:02}&hd={event:%Y%m%d}"


def _weather_block(html: str):
    # Extract ONLY the weather section; do not match unrelated icons or an
    # accidental weather value in results, navigation, or other race cards.
    match = re.search(
        r'<p\b[^>]*class=["\'][^"\']*\bweather1_title\b[^"\']*["\'][^>]*>'
        r'(.*?)</p>(.{0,8500})', html, re.I | re.S)
    return (match[1], match[2]) if match else None


def _label_number(block: str, label: str, unit: str, max_value: float):
    pattern = (r'<span\b[^>]*class=["\'][^"\']*weather1_bodyUnitLabelTitle'
               r'[^"\']*["\'][^>]*>\s*' + label
               + r'\s*</span>\s*<span\b[^>]*>\s*(\d+(?:\.\d+)?)'
               + re.escape(unit) + r'\s*</span>')
    m = re.search(pattern, block, re.I | re.S)
    return _number(m[1], 0, max_value) if m else None


def parse_official(html: str, race: int, captured: datetime) -> dict:
    """Extract observed wind/waves and explicit observation freshness.

    "nR時点" has no trustworthy clock and cannot be certified as fresh.
    A published weather panel may be copied to later races before preview.
    """
    if captured.tzinfo is None:
        raise ValueError("Aware capture time required")
    section = _weather_block(html)
    if not section:
        return {"status": "WEATHER_SECTION_MISSING", "values": None}
    title, block = section
    label = unescape(re.sub(r"<[^>]+>", "", title)).replace("\u3000", " ").strip()
    label = re.sub(r"\s+", "", label.removeprefix("水面気象情報"))
    speed = _label_number(block, "風速", "m", 65)
    wave = _label_number(block, "波高", "cm", 150)
    dm = re.search(
        r'<(?:p|span|div)\b[^>]*class=["\'][^"\']*'
        r'\bweather1_bodyUnitImage\b[^"\']*\bis-wind(\d{1,2})\b[^"\']*["\']',
        block, re.I | re.S)
    code = _number(dm[1], 1, 17, integer=True) if dm else None
    values = {"wind_speed": speed, "wind_direction_number": code,
              "wave_height": wave}
    local = captured.astimezone(JST)
    clock = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)現在", label)
    reference = re.fullmatch(r"(1[0-2]|[1-9])R時点", label)
    observed = None
    if clock:
        observed = local.replace(hour=int(clock[1]), minute=int(clock[2]),
                                 second=0, microsecond=0)
        age = local - observed
        timing = "OBSERVATION_FRESH" if timedelta(0) <= age <= MAX_OBSERVATION_AGE else "OBSERVATION_STALE"
    elif reference and int(reference[1]) in (race - 1, race):
        timing = "OBSERVATION_CLOCK_UNKNOWN"
    else:
        timing = "OBSERVATION_LABEL_UNVERIFIED"
    return {
        "status": timing,
        "values": values,
        "observation_label": label,
        "observed_at_jst": observed.isoformat() if observed else None,
        "captured_at_utc": captured.astimezone(UTC).isoformat(),
        "source_block_sha256": hashlib.sha256((title + block).encode("utf-8")).hexdigest(),
        "source_kind": "official_beforeinfo_weather_panel",
    }


def _openapi_values(preview):
    if not isinstance(preview, dict):
        return None
    return {
        "wind_speed": _number(preview.get("wind_speed"), 0, 65),
        "wind_direction_number": _number(preview.get("wind_direction_number"), 1, 17, integer=True),
        "wave_height": _number(preview.get("wave_height"), 0, 150),
    }


def candidates(payload: dict, now: datetime) -> list[dict]:
    if now.tzinfo is None:
        raise ValueError("Aware now required")
    day = now.astimezone(JST).date()
    stadiums = (payload.get("programs") or {}).get("stadiums") if isinstance(payload, dict) else None
    if not isinstance(stadiums, dict):
        return []
    found = []
    for raw_code, group in stadiums.items():
        venue = _number(raw_code, 1, 24, integer=True)
        if venue is None or not isinstance(group, dict) or not isinstance(group.get("races"), dict):
            continue
        for raw_race, record in group["races"].items():
            race = _number(raw_race, 1, 12, integer=True)
            if race is None or not isinstance(record, dict):
                continue
            try:
                cutoff = datetime.strptime(record["closed_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
            except (ValueError, KeyError, TypeError):
                continue
            lead = (cutoff - now.astimezone(JST)).total_seconds() / 60
            if cutoff.date() != day or not WINDOW_MINUTES[0] <= lead <= WINDOW_MINUTES[1]:
                continue
            found.append({
                "venue_code": f"{venue:02}", "race": race,
                "cutoff_at_jst": cutoff.isoformat(), "lead_minutes_at_selection": round(lead, 2),
                "openapi_preview": _openapi_values(record.get("preview")),
                "official_url": official_url(day, venue, race),
            })
    return sorted(found, key=lambda x: (x["cutoff_at_jst"], x["venue_code"], x["race"]))[:48]


def _fetch_text(url: str, limit: int, timeout=10) -> str:
    request = Request(url, headers={
        "User-Agent": "WEATHER-LAB-readonly-comparison/0.1",
        "Cache-Control": "no-cache", "Accept": "text/html,application/json",
    })
    with urlopen(request, timeout=timeout) as response:
        if response.geturl() != url:
            raise ValueError("Unexpected source redirect")
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Source exceeded size limit")
    return raw.decode("utf-8", errors="replace")


def _official_fetch(url: str):
    html = _fetch_text(url, 600_000, timeout=9)
    return html, datetime.now(UTC)


def compare(candidate: dict, official_fetch=_official_fetch) -> dict:
    """Official fetch is injected for offline tests; only pre-cutoff reads."""
    row = {k: candidate[k] for k in (
        "venue_code", "race", "cutoff_at_jst", "lead_minutes_at_selection",
        "openapi_preview", "official_url")}
    cutoff = _iso(row["cutoff_at_jst"])
    if cutoff is None:
        raise ValueError("No valid cutoff")
    try:
        html, captured = official_fetch(candidate["official_url"])
        if captured.tzinfo is None:
            raise ValueError("Naive official capture")
        row["official"] = parse_official(html, candidate["race"], captured)
    except (OSError, UnicodeError, ValueError, TimeoutError) as exc:
        row["status"] = "OFFICIAL_FETCH_FAILED"
        row["official"] = {"status": "FETCH_FAILED", "error_type": type(exc).__name__}
        row["differences"] = {}
        return row
    row["differences"] = {}
    # Even the capture must finish >= five minutes before published cutoff.
    if captured > cutoff - timedelta(minutes=WINDOW_MINUTES[0]):
        row["status"] = "TOO_LATE_NOT_ELIGIBLE"
        return row
    if row["official"]["status"] != "OBSERVATION_FRESH":
        row["status"] = "OFFICIAL_TIMING_NOT_VERIFIED"
        return row
    api = candidate["openapi_preview"]
    official = row["official"]["values"]
    if api is None:
        row["status"] = "OPENAPI_PREVIEW_MISSING"
        return row
    for k in FIELDS:
        a, b = api[k], official[k]
        if a is None or b is None:
            row["differences"][k] = {"status": "FIELD_MISSING", "openapi": a, "official": b}
        elif abs(a - b) > 0.01:
            row["differences"][k] = {"status": "VALUE_DIFF", "openapi": a, "official": b}
    if any(v["status"] == "VALUE_DIFF" for v in row["differences"].values()):
        row["status"] = "DIFFERENCE_POSSIBLE_SOURCE_LAG"
    elif row["differences"]:
        row["status"] = "INCOMPLETE_COMPARISON"
    else:
        row["status"] = "VALUES_MATCH_OBSERVATION_TIME_NOT_PAIRED"
    # Open API does not provide the original observation timestamp.
    row["same_observation_time_proven"] = False
    row["formal_forecast_changed"] = False
    return row


def audit(payload: dict, now: datetime, official_fetch=_official_fetch) -> dict:
    """No past or result data. All source values belong to this fetch run."""
    chosen = candidates(payload, now)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda c: compare(c, official_fetch), chosen))
    return {
        "schema": SCHEMA, "event_date": now.astimezone(JST).date().isoformat(),
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "source_input_retrieved_at_utc": now.astimezone(UTC).isoformat(),
        "openapi_source": f"{OPEN_API}/{now.astimezone(JST):%Y}/{now.astimezone(JST):%Y%m%d}.json",
        "record_count": len(records),
        "status_counts": dict(Counter(row["status"] for row in records)),
        "records": records,
        "no_formal_bet_or_model_changes": True,
        "data_quality_note": "Official beforeinfo may show earlier-race weather; matching values do not prove the same observation instant.",
    }


def merge_archive(previous: dict | None, fresh: dict) -> dict:
    """Append-only historical capture (no retrospective official correction)."""
    if fresh.get("schema") != SCHEMA:
        raise ValueError("Wrong fresh audit schema")
    day = fresh["event_date"]
    if previous is not None and (
        previous.get("schema") != SCHEMA or previous.get("event_date") != day):
        raise ValueError("Wrong existing audit day/schema")
    stored = list(previous.get("records", [])) if previous else []
    seen = {(r["venue_code"], r["race"], r.get("official", {}).get("captured_at_utc"),
             r.get("status")) for r in stored}
    for row in fresh.get("records", []):
        key = (row["venue_code"], row["race"], row.get("official", {}).get("captured_at_utc"),
               row.get("status"))
        if key not in seen:
            stored.append(row)
            seen.add(key)
    return {
        "schema": SCHEMA, "event_date": day,
        "created_at_utc": (previous or {}).get("created_at_utc", fresh["collected_at_utc"]),
        "updated_at_utc": fresh["collected_at_utc"],
        "records": stored,
        "source_provenance_kept": True,
        "historical_results_used": False,
        "formal_forecasts_unchanged": True,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path)
    p.add_argument("--merge-from", type=Path)
    p.add_argument("--previous", type=Path)
    p.add_argument("--archive-out", type=Path)
    a = p.parse_args(argv)
    if a.merge_from:
        if not a.archive_out or a.out:
            p.error("--merge-from requires --archive-out only")
        fresh = json.loads(a.merge_from.read_text(encoding="utf-8"))
        prior = (json.loads(a.previous.read_text(encoding="utf-8"))
                 if a.previous and a.previous.exists() else None)
        result, destination = merge_archive(prior, fresh), a.archive_out
    else:
        if not a.out or a.archive_out or a.previous:
            p.error("Collection requires --out only")
        now = datetime.now(UTC)
        url = f"{OPEN_API}/{now.astimezone(JST):%Y}/{now.astimezone(JST):%Y%m%d}.json"
        error = None
        try:
            payload = json.loads(_fetch_text(url, 12_000_000, timeout=14))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            payload, error = {}, type(exc).__name__
        result = audit(payload, now)
        result["openapi_fetch_status"] = "ok" if error is None else "unavailable"
        if error:
            result["openapi_error_type"] = error
        destination = a.out
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
