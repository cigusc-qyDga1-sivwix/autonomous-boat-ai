"""Read-only Wakamatsu exhibition-data connectivity probe (no betting)."""
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

def probe(day="20261021", races=("5", "6", "7")):
    if len(day) != 8 or not day.isdigit():
        raise ValueError("day must be YYYYMMDD")
    url = f"https://boatraceopenapi.github.io/api/v1/{day[:4]}/{day}.json"
    request = Request(url, headers={"User-Agent": "autonomous-boat-ai/0.1 (read-only pilot)"})
    with urlopen(request, timeout=12) as response:
        data = json.load(response)
    stadium = data.get("programs", {}).get("stadiums", {}).get("20", {})
    all_races = stadium.get("races", {})
    result = {"source": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "venue": "20", "races": {}}
    for number in races:
        race = all_races.get(number, {})
        preview = race.get("preview") or {}
        racers = preview.get("racers") or {}
        result["races"][number] = {
            "cutoff": race.get("closed_at"),
            "preview_present": bool(preview),
            "weather": {k: preview.get(k) for k in ("wind_speed", "wind_direction_number", "wave_height", "weather_number")},
            "boats": {str(i): {k: (racers.get(str(i)) or {}).get(k) for k in ("course_number", "start_timing", "exhibition_time", "tilt_adjustment")} for i in range(1, 7)},
        }
    return result

if __name__ == "__main__":
    try:
        print(json.dumps(probe(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "FETCH_FAILED", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
