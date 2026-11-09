"""Bridge independently collected exhibitions into a pre-cutoff FORECAST.

Only date-matched six-boat measurements retrieved by the current run may be
considered. An already finished race cannot be revised, no matter what the
third-party 'source observed' timestamp says. Results/payouts are never read.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')
SAFE_MARGIN_SECONDS = 120
from pathlib import Path
import json
if __package__:
    from .ingest_boatracecsv_exhibition import preview_signature, original_exhibition_signature
else:
    from ingest_boatracecsv_exhibition import preview_signature, original_exhibition_signature

SOURCE_NAME = "BoatraceCSV"
METRICS = {"一周": ("lap_time", 30, 50),
           "まわり足": ("turn_time", 4, 15),
           "直線": ("straight_time", 5, 12)}


def finite_float(value):
    from math import isfinite
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def available_rows(path: Path, day: str) -> dict:
    """Only the research snapshot for the same JST date; no network access."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != "boatlabs.exhibition_research.v1" or data.get("event_date") != day:
            return {}
        return {r["race_code"]: r for r in data.get("records", [])
                if isinstance(r, dict) and r.get("race_code")}
    except (ValueError, TypeError, KeyError, OSError):
        return {}


def verified_original_for_openapi(race: dict, row: dict | None, now: datetime,
                                  venue_code: str, race_number: int):
    """Only independently captured, six-boat-matched original times.

    The normal CSV preview can be revised by later wind/ST updates even if
    original straight/lap/turn data were already captured before the cutoff.
    This function uses an immutable *per-original* SHA and first-capture time
    instead of accepting the latest composite preview retroactively.
    """
    if not isinstance(row, dict) or not isinstance(race, dict) or now.tzinfo is None:
        return {}, None
    try:
        cutoff = datetime.strptime(race["closed_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
        stamp = datetime.fromisoformat(row["original_exhibition_captured_at_utc"])
        observed = datetime.fromisoformat(row["original_exhibition_observed_jst"])
    except (KeyError, ValueError, TypeError):
        return {}, None
    now_jst = now.astimezone(JST)
    if (row.get("source_status") != "historical_research_only_not_frozen_forecast"
            or row.get("race_code") != f"{cutoff:%Y%m%d}{int(venue_code):02d}{int(race_number):02d}"
            or row.get("venue_code") != f"{int(venue_code):02d}"
            or row.get("race") != int(race_number)
            or stamp.tzinfo is None or observed.tzinfo is None
            or now_jst.date() != cutoff.date()
            or stamp.astimezone(JST).date() != cutoff.date()
            or observed.astimezone(JST).date() != cutoff.date()
            or now_jst >= cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS)
            or stamp.astimezone(JST) >= cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS)
            or stamp > now + timedelta(seconds=30)
            or observed > stamp + timedelta(seconds=30)
            or observed >= cutoff
            or original_exhibition_signature(row) != row.get("original_exhibition_sha256")):
        return {}, None
    boats = row.get("boats")
    preview = (race.get("preview") or {}).get("racers") or {}
    if not isinstance(boats, list) or len(boats) != 6 or not isinstance(preview, dict):
        return {}, None
    by_lane = {b.get("lane"): b for b in boats if isinstance(b, dict)}
    if set(by_lane) != set(range(1, 7)):
        return {}, None
    # A CSV original time is usable only alongside the SAME real entry/course,
    # legal exhibition ST and ordinary exhibition time in the live OpenAPI.
    for lane in range(1, 7):
        b = by_lane[lane]
        a = preview.get(str(lane)) or {}
        for csv_field, api_field in (
                ("course", "course_number"),
                ("exhibition_st", "start_timing"),
                ("exhibition_time", "exhibition_time")):
            left, right = finite_float(b.get(csv_field)), finite_float(a.get(api_field))
            if left is None or right is None or abs(left - right) > 1e-6:
                return {}, None
    extras = {}
    for original_name, (key, lo, hi) in METRICS.items():
        found = {}
        for lane in range(1, 7):
            for metric in by_lane[lane].get("original_exhibition") or []:
                if isinstance(metric, dict) and metric.get("metric") == original_name:
                    v = finite_float(metric.get("value"))
                    if v is not None and lo <= v <= hi:
                        found[str(lane)] = v
        if len(found) == 6:
            extras[key] = found
    if not extras:
        return {}, None
    return extras, {
        "source": SOURCE_NAME,
        "observed_at_jst": row["original_exhibition_observed_jst"],
        "captured_at_utc": row["original_exhibition_captured_at_utc"],
        "measurement_sha256": row["original_exhibition_sha256"],
        "metrics": sorted(extras),
        "six_boat_preview_matched": True,
        "capture_scope": "original_exhibition_only",
    }


def inject(race: dict, row: dict | None, now: datetime, venue_code: str,
           race_number: int, *, require_capture_evidence=True):
    """Return (copy of race, provenance), or original race and None.

    Strictly require collection by the current run prior to the safety cutoff.
    Even an old-looking timestamp is not enough if the actual run is after cutoff.
    """
    if not row or now.tzinfo is None or not isinstance(race, dict):
        return race, None
    if row.get("race_code") != f"{now.astimezone(JST):%Y%m%d}{int(venue_code):02d}{race_number:02d}":
        return race, None
    if row.get("source_status") != "historical_research_only_not_frozen_forecast":
        return race, None
    try:
        cutoff = datetime.strptime(race['closed_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=JST)
    except (KeyError, TypeError, ValueError):
        return race, None
    if cutoff is None or now.astimezone(JST) >= cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS):
        return race, None
    if require_capture_evidence:
        try:
            captured = datetime.fromisoformat(row["preview_captured_at_utc"])
            if (captured.tzinfo is None
                    or captured.astimezone(JST).date() != cutoff.date()
                    or captured > now + timedelta(seconds=30)
                    or captured.astimezone(JST) >= cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS)
                    or row.get("preview_sha256") != preview_signature(row)):
                return race, None
        except (KeyError, TypeError, ValueError):
            return race, None
    try:
        seen = datetime.fromisoformat(row["source_observed_jst"])
        if seen.tzinfo is None:
            return race, None
        observed = seen.astimezone(JST)
        if (observed.date() != cutoff.date()
            or observed > now.astimezone(JST) + timedelta(seconds=30)
            or observed >= cutoff
            or observed < cutoff - timedelta(minutes=35)):
            return race, None
    except (TypeError, ValueError, KeyError):
        return race, None
    if row.get("venue_code") != f"{int(venue_code):02d}" or row.get("race") != race_number:
        return race, None
    boats = row.get("boats")
    if not isinstance(boats, list) or len(boats) != 6:
        return race, None
    chosen = {}
    seen_courses = set()
    for boat in boats:
        if not isinstance(boat, dict):
            return race, None
        lane = boat.get("lane")
        course = finite_float(boat.get("course"))
        st = finite_float(boat.get("exhibition_st"))
        expo = finite_float(boat.get("exhibition_time"))
        tilt = finite_float(boat.get("tilt"))
        if (not isinstance(lane,int) or lane not in range(1,7) or lane in chosen
            or course not in range(1,7) or course in seen_courses
            or st is None or not -.5 <= st <= 1.0
            or expo is None or not 5 <= expo <= 10):
            return race, None
        chosen[lane] = {
            "course_number":int(course),"start_timing":st,
            "exhibition_time":expo,"tilt_adjustment":tilt}
        seen_courses.add(course)
    extras = {}
    for name, (key,low,high) in METRICS.items():
        vals = {}
        for boat in boats:
            for metric in boat.get("original_exhibition") or []:
                if isinstance(metric,dict) and metric.get("metric")==name:
                    val = finite_float(metric.get("value"))
                    if val is not None and low <= val <= high:
                        vals[str(boat["lane"])] = val
        if len(vals)==6:
            extras[key] = vals
    copy = deepcopy(race)
    current = copy.get("preview") if isinstance(copy.get("preview"),dict) else {}
    preview = dict(current)
    preview["racers"] = {str(k):v for k,v in chosen.items()}
    wx = row.get("weather") or {}
    for src,dest in (("wind_mps","wind_speed"),("wind_direction_number","wind_direction_number"),
                     ("wave_cm","wave_height"),("weather_number","weather_number"),
                     ("air_c","air_temperature"),("water_c","water_temperature")):
        val = finite_float(wx.get(src))
        if val is not None: preview[dest] = val
    copy["preview"] = preview
    copy["_exhibition_original"] = extras
    copy["_exhibition_origin"] = {
        "source":SOURCE_NAME, "observed_at_jst":row["source_observed_jst"],
        "captured_before_cutoff":True,"metrics":list(extras),
        "forecast_run_utc":now.astimezone(timezone.utc).isoformat(),
        "captured_at_utc":row.get("preview_captured_at_utc"),
        "measurement_sha256":row.get("preview_sha256"),
    }
    return copy, copy["_exhibition_origin"]
