"""Forecast weather near all 24 Japanese BOATRACE venues (research, non-commercial).

The coordinates below are approximate local weather-grid reference points
near the published venue addresses, NOT precisely surveyed racecourse/water
stations. Forecasts NEVER substitute for on-water observed wind/waves.
Open-Meteo (CC BY 4.0): https://open-meteo.com/; free non-commercial tier.
No post-cutoff feature creation or outcome-driven changes.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo"
SOURCE_CREDIT = "Weather data by Open-Meteo.com (CC BY 4.0)"
# Approximate coordinates close to each venue's municipality / waterfront.
# Not measured boat-racing water-surface coordinates. Verify before using
# bearing-to-course/headwind models. Codes follow official 01–24 venue IDs.
VENUE_POINTS: dict[str, tuple[float, float]] = {
    "1": (36.40, 139.30),  # 桐生 / みどり市
    "2": (35.81, 139.67),  # 戸田 / 戸田公園
    "3": (35.70, 139.87),  # 江戸川 / 東小松川
    "4": (35.59, 139.74),  # 平和島 / 平和島
    "5": (35.66, 139.49),  # 多摩川 / 府中・是政
    "6": (34.70, 137.56),  # 浜名湖 / 湖西・新居
    "7": (34.83, 137.22),  # 蒲郡 / 竹谷
    "8": (34.89, 136.84),  # 常滑 / 新開
    "9": (34.69, 136.53),  # 津 / 藤方
    "10": (36.23, 136.16),  # 三国 / 坂井・池上
    "11": (35.03, 135.87),  # びわこ / 大津・茶が崎
    "12": (34.62, 135.47),  # 住之江 / 泉
    "13": (34.72, 135.40),  # 尼崎 / 水明
    "14": (34.19, 134.62),  # 鳴門 / 撫養
    "15": (34.29, 133.81),  # 丸亀 / 富士見
    "16": (34.47, 133.81),  # 児島 / 元浜
    "17": (34.32, 132.30),  # 宮島 / 宮島口
    "18": (34.05, 131.81),  # 徳山 / 周南・栗屋
    "19": (34.01, 131.00),  # 下関 / 長府
    "20": (33.90, 130.76),  # 若松 / 赤岩
    "21": (33.89, 130.65),  # 芦屋 / 遠賀・芦屋
    "22": (33.60, 130.39),  # 福岡 / 那の津
    "23": (33.44, 129.99),  # 唐津 / 原
    "24": (32.91, 129.96),  # 大村 / 玖島
}
VARIABLES = (
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "temperature_2m", "precipitation", "weather_code",
)


def numeric(value, lo, hi):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (ValueError, TypeError):
        return None
    return round(n, 2) if math.isfinite(n) and lo <= n <= hi else None


def parse_batch(response, codes: list[str], now: datetime) -> dict:
    """Fail closed on malformed provider data or unrelated coordinates."""
    if not codes:
        return {}
    payloads = response if isinstance(response, list) else [response]
    if len(payloads) != len(codes):
        raise ValueError("Weather response location count did not match request")
    result = {}
    for code, payload in zip(codes, payloads):
        lat, lon = VENUE_POINTS[code]
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid weather response for {code}")
        if abs(float(payload.get("latitude", -999)) - lat) > .4 or abs(
            float(payload.get("longitude", -999)) - lon
        ) > .4:
            raise ValueError(f"Wrong location weather response for {code}")
        hourly = payload.get("hourly")
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
            raise ValueError(f"No weather timeline for {code}")
        length = len(hourly["time"])
        if not 1 <= length <= 300 or any(
            not isinstance(hourly.get(key), list) or len(hourly[key]) != length
            for key in VARIABLES
        ):
            raise ValueError(f"Incomplete weather series for {code}")
        samples = {}
        for idx, raw_time in enumerate(hourly["time"]):
            try:
                timestamp = datetime.fromisoformat(raw_time)
            except (TypeError, ValueError):
                continue
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(JST).replace(tzinfo=None)
            if timestamp.date() != now.astimezone(JST).date():
                continue
            speed = numeric(hourly["wind_speed_10m"][idx], 0, 80)
            direction = numeric(hourly["wind_direction_10m"][idx], 0, 360)
            gust = numeric(hourly["wind_gusts_10m"][idx], 0, 110)
            temperature = numeric(hourly["temperature_2m"][idx], -30, 55)
            precipitation = numeric(hourly["precipitation"][idx], 0, 150)
            weather_code = numeric(hourly["weather_code"][idx], 0, 99)
            if speed is None:
                continue
            samples[timestamp.isoformat(timespec="minutes")] = {
                "wind_speed": speed,
                "wind_direction_degrees": direction,
                "wind_gust": gust,
                "air_temperature": temperature,
                "precipitation_mm": precipitation,
                "weather_code": int(weather_code) if weather_code is not None else None,
            }
        if samples:
            result[code] = {
                "source": SOURCE,
                "source_label": "近隣気象予報（現地実測ではない）",
                "source_url": "https://open-meteo.com/",
                "credit": SOURCE_CREDIT,
                "licence": "CC BY 4.0; non-commercial API use",
                "retrieved_at_utc": now.astimezone(ZoneInfo("UTC")).isoformat(),
                "grid_reference": "会場近隣の概算座標・気象予報格子",
                "latitude_approx": lat, "longitude_approx": lon,
                "hours_jst": samples,
            }
    return result


def fetch_weather(active_codes: list[str], now: datetime, timeout=21) -> dict:
    """One batched weather GET for ALL venues hosting races today."""
    codes = sorted({str(int(c)) for c in active_codes if str(c).isdigit()
                    and str(int(c)) in VENUE_POINTS}, key=int)
    if not codes:
        return {}
    query = {
        "latitude": ",".join(str(VENUE_POINTS[c][0]) for c in codes),
        "longitude": ",".join(str(VENUE_POINTS[c][1]) for c in codes),
        "hourly": ",".join(VARIABLES),
        "forecast_days": "1",
        "timezone": "Asia/Tokyo",
        "wind_speed_unit": "ms",
    }
    request = Request(URL + "?" + urlencode(query), headers={
        "User-Agent": "BOAT-LAB-open-source-research/1.0 (non-commercial, weather attribution)",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"Open-Meteo returned HTTP {response.status}")
        raw = response.read(750_001)
    if len(raw) > 750_000:
        raise ValueError("Weather response exceeded size limit")
    return parse_batch(json.loads(raw.decode("utf-8")), codes, now)


def weather_at(venue_weather: dict | None, cutoff: datetime) -> dict | None:
    """Choose nearest hour to scheduled start and preserve issuance timestamp."""
    if not venue_weather or not venue_weather.get("hours_jst"):
        return None
    options = []
    for raw, sample in venue_weather["hours_jst"].items():
        try:
            hour = datetime.fromisoformat(raw).replace(tzinfo=JST)
        except (ValueError, TypeError):
            continue
        delta = abs((hour - cutoff.astimezone(JST)).total_seconds())
        if delta <= 3600:
            options.append((delta, hour, sample))
    if not options:
        return None
    _, hour, sample = min(options, key=lambda x: (x[0], x[1]))
    return {
        **sample,
        "source": SOURCE,
        "source_label": "近隣気象予報",
        "issued_at_utc": venue_weather["retrieved_at_utc"],
        "forecast_hour_jst": hour.isoformat(timespec="minutes"),
        "site_observed": False,
        "grid_reference": venue_weather["grid_reference"],
        "credit": SOURCE_CREDIT,
    }
