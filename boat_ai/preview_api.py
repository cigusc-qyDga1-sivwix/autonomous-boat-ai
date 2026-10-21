"""Read-only adapter for the unofficial Boatrace Open API.

The API is delayed, unaffiliated with BOATRACE, and may be incomplete.
No wagering and no automated polling is performed by this module.
"""
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE = "https://boatraceopenapi.github.io/api/v1"

def parse_preview(payload: dict, race_number: int, stadium_number: int = 20) -> dict:
    if stadium_number != 20:
        raise ValueError("Pilot limited to Wakamatsu (20)")
    races = payload.get("programs", {}).get("stadiums", {}).get(str(stadium_number), {}).get("races", {})
    race = races.get(str(race_number), {})
    preview = race.get("preview")
    if not isinstance(preview, dict):
        return {"status": "missing", "venue": "20", "race": race_number, "racers": None, "weather": None}
    fields = ("course_number", "start_timing", "exhibition_time", "tilt_adjustment")
    racers = {str(k): {field: r.get(field) for field in fields} for k, r in preview.get("racers", {}).items()}
    weather = {k: preview.get(k) for k in ("wind_speed", "wind_direction_number", "wave_height", "weather_number", "air_temperature", "water_temperature")}
    complete = len(racers) == 6 and all(all(v is not None for v in r.values()) for r in racers.values())
    return {"status": "complete" if complete else "incomplete", "venue": "20", "race": race_number, "racers": racers, "weather": weather}

def fetch_preview(date_yyyymmdd: str, race_number: int, timeout: int = 15) -> dict:
    if len(date_yyyymmdd) != 8 or not date_yyyymmdd.isdigit():
        raise ValueError("Date must be YYYYMMDD")
    url = f"{BASE}/{date_yyyymmdd[:4]}/{date_yyyymmdd}.json"
    request = Request(url, headers={"User-Agent": "autonomous-boat-ai-research/0.1"})
    with urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    result = parse_preview(data, race_number)
    result["source_url"] = url
    result["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
    return result
