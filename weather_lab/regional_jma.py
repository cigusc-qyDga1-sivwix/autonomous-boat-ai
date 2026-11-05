"""WEATHER LAB: independent 24-venue *regional model forecast* feed.

JMA MSM/GSM model data is redistributed through Open-Meteo's JMA API.
This is NOT JMA AMeDAS observed wind, NOT track wind/wave, and NOT a
Weathernews API feed. Free Open-Meteo tier is limited to non-commercial
use; licensing must be reviewed before commercial use.
Never replace weather_lab.monitor's on-track observation feed, never
change BOAT LAB official predictions.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
SCHEMA = "weather_lab.regional_jma_forecast.v1"
API_URL = "https://api.open-meteo.com/v1/jma"
CREDIT = "Forecast data by Open-Meteo.com (CC BY 4.0); source models JMA MSM/GSM"
NAMES = (
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑",
    "津", "三国", "びわこ", "住之江", "尼崎", "鳴門", "丸亀", "児島",
    "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村",
)
# Approximate weather grid reference coordinates, NOT verified on-water sensor locations.
POINTS = (
    (36.40,139.30),(35.81,139.67),(35.70,139.87),(35.59,139.74),
    (35.66,139.49),(34.70,137.56),(34.83,137.22),(34.89,136.84),
    (34.69,136.53),(36.23,136.16),(35.03,135.87),(34.62,135.47),
    (34.72,135.40),(34.19,134.62),(34.29,133.81),(34.47,133.81),
    (34.32,132.30),(34.05,131.81),(34.01,131.00),(33.90,130.76),
    (33.89,130.65),(33.60,130.39),(33.44,129.99),(32.91,129.96),
)
VARIABLES = ("wind_speed_10m", "wind_direction_10m", "temperature_2m", "precipitation")


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        return None
    return round(float(value), 2)


def parse(response, now: datetime) -> dict:
    """Read JMA *model forecast*. Missing/invalid venue samples stay unavailable."""
    if now.tzinfo is None:
        raise ValueError("A timezone-aware acquisition time is required")
    day = now.astimezone(JST).date()
    sources = response if isinstance(response, list) else [response]
    if len(sources) != len(NAMES):
        raise ValueError("Regional forecast needs 24 matched locations")
    venues = []
    for i, obj in enumerate(sources):
        point = POINTS[i]
        if not isinstance(obj, dict) or obj.get("error"):
            raise ValueError(f"Provider error for venue {i+1}")
        lat = number(obj.get("latitude"), -90, 90)
        lon = number(obj.get("longitude"), -180, 180)
        if lat is None or lon is None or abs(lat-point[0]) > .6 or abs(lon-point[1]) > .6:
            raise ValueError("Returned weather grid does not match requested coordinates")
        hourly = obj.get("hourly")
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
            raise ValueError("Missing forecast hourly timeline")
        n = len(hourly["time"])
        if not 1 <= n <= 300 or any(not isinstance(hourly.get(key), list) or len(hourly[key]) != n for key in VARIABLES):
            raise ValueError("Incomplete model forecast grid")
        hours = []
        for j, t in enumerate(hourly["time"]):
            if not isinstance(t, str):
                continue
            try:
                dt = datetime.fromisoformat(t)
            except ValueError:
                continue
            if dt.tzinfo is not None:
                dt = dt.astimezone(JST).replace(tzinfo=None)
            if dt.date() != day:
                continue
            speed = number(hourly["wind_speed_10m"][j], 0, 80)
            direction = number(hourly["wind_direction_10m"][j], 0, 360)
            temp = number(hourly["temperature_2m"][j], -45, 60)
            rain = number(hourly["precipitation"][j], 0, 400)
            if speed is None:
                continue
            hours.append({
                "valid_at_jst": dt.replace(tzinfo=JST).isoformat(),
                "wind_mps": speed, "wind_direction_degrees": direction,
                "air_c": temp, "precipitation_mm": rain,
            })
        current = obj.get("current") or {}
        current_dt = None
        if isinstance(current, dict) and isinstance(current.get("time"), str):
            try:
                current_dt = datetime.fromisoformat(current["time"])
                current_dt = current_dt.astimezone(JST) if current_dt.tzinfo else current_dt.replace(tzinfo=JST)
            except ValueError:
                current_dt = None
        current_model = None
        if (current_dt is not None and current_dt.date() == day
                and timedelta(minutes=-30) <= now.astimezone(JST)-current_dt <= timedelta(minutes=90)):
            speed = number(current.get("wind_speed_10m"), 0, 80)
            if speed is not None:
                current_model = {
                    "valid_at_jst": current_dt.isoformat(),
                    "wind_mps": speed,
                    "wind_direction_degrees": number(current.get("wind_direction_10m"),0,360),
                    "air_c": number(current.get("temperature_2m"),-45,60),
                    "method": "modelled_current_not_station_observation",
                }
        if current_model is None and hours:
            # The nearest hourly forecast is fallback, not a measured current condition.
            nearest = min(hours, key=lambda x: abs((datetime.fromisoformat(x["valid_at_jst"])-now.astimezone(JST)).total_seconds()))
            if abs((datetime.fromisoformat(nearest["valid_at_jst"])-now.astimezone(JST)).total_seconds()) <= 3600:
                current_model = {**nearest, "method": "nearest_hourly_model_forecast_not_observation"}
        venues.append({
            "code": f"{i+1:02d}", "name": NAMES[i],
            "boat_lab_prediction_in_scope": i != 2,
            "reference_coordinates_approx": {"lat": point[0], "lon": point[1]},
            "grid_coordinates_returned": {"lat": lat, "lon": lon},
            "model_current": current_model, "hourly": hours,
        })
    return {
        "schema": SCHEMA, "event_date": day.isoformat(),
        "retrieved_at_utc": now.astimezone(UTC).isoformat(),
        "provider": {
            "name": "Open-Meteo JMA API (redistributed JMA weather models)",
            "api_url": API_URL, "fetch_status": "ok",
            "model_source": "JMA MSM/GSM", "data_type": "grid_model_forecast_not_ground_observation",
            "credit": CREDIT, "licence": "CC BY 4.0; free tier non-commercial",
        },
        "scope": {
            "venues_monitored": 24, "no_track_water_wind_or_wave_measured": True,
            "no_tide_or_current": True, "forecast_role": "regional_context_only",
            "no_bet_or_formal_forecast_changes": True,
        },
        "venues": venues,
    }


def fetch(now: datetime) -> dict:
    query = {
        "latitude": ",".join(str(p[0]) for p in POINTS),
        "longitude": ",".join(str(p[1]) for p in POINTS),
        "current": "wind_speed_10m,wind_direction_10m,temperature_2m",
        "hourly": ",".join(VARIABLES),
        "forecast_days": 1, "timezone": "Asia/Tokyo", "wind_speed_unit": "ms",
    }
    request = Request(API_URL+"?"+urlencode(query), headers={
        "User-Agent": "WEATHER-LAB-noncommercial-research/0.3 (Open-Meteo attribution)",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f"Regional weather provider returned {response.status}")
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Regional model response exceeds size limit")
    return parse(json.loads(raw.decode("utf-8")), now)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--fixture", type=Path)
    p.add_argument("--now-iso", help="Use only with --fixture")
    args = p.parse_args(argv)
    if args.now_iso and not args.fixture:
        p.error("--now-iso requires --fixture")
    try:
        now = datetime.fromisoformat(args.now_iso) if args.now_iso else datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Naive timestamp")
        document = parse(json.loads(args.fixture.read_text(encoding="utf-8")), now) if args.fixture else fetch(now)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"status":"ok","provider":"Open-Meteo JMA model", "venues":len(document["venues"]),
                          "observed_station_count":0,"formal_forecast_changed":False}))
        return document
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        # Do not replace the last successful output with a fabricated observation.
        print(json.dumps({"status":"unavailable","reason":type(exc).__name__, "file_written":False}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
