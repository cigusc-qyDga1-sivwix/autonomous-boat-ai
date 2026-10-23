"""Bridge independently collected exhibitions into a pre-cutoff FORECAST.

Only date-matched six-boat measurements retrieved by the current run may be
considered. An already finished race cannot be revised, no matter what the
third-party 'source observed' timestamp says. Results/payouts are never read.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import json

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


def inject(race: dict, row: dict | None, now: datetime, venue_code: str,
           race_number: int):
    """Return (copy of race, provenance), or original race and None.

    Strictly require collection by the current run prior to the safety cutoff.
    Even an old-looking timestamp is not enough if the actual run is after cutoff.
    """
    if not row or now.tzinfo is None or not isinstance(race, dict):
        return race, None
    if row.get("race_code") != f"{now.astimezone(now.tzinfo):%Y%m%d}{int(venue_code):02d}{race_number:02d}":
        return race, None
    if row.get("source_status") != "historical_research_only_not_frozen_forecast":
        return race, None
    from .autonomous_daily import JST, SAFE_MARGIN_SECONDS, cutoff_of
    cutoff = cutoff_of(race)
    if cutoff is None or now.astimezone(JST) >= cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS):
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
        "forecast_run_utc":now.astimezone(__import__("datetime").timezone.utc).isoformat(),
    }
    return copy, copy["_exhibition_origin"]
