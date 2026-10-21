"""Read-only Wakamatsu exhibition-data connectivity probe (no betting)."""
import json
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

def probe(day=None, races=("5", "6", "7")):
    if day is None:
        day = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
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
        record = result["races"][number]
        required = ("course_number", "start_timing", "exhibition_time", "tilt_adjustment")
        missing = [f"boat_{i}.{key}" for i in range(1, 7)
                   for key in required if record["boats"][str(i)].get(key) is None]
        missing += [f"weather.{k}" for k, value in record["weather"].items()
                    if value is None]
        observed = len(required) * 6 + len(record["weather"]) - len(missing)
        record["data_status"] = ("COMPLETE" if not missing else
                                 "PARTIAL" if observed else "NOT_READY")
        record["missing_fields"] = missing
        record["preview_present"] = observed > 0
        cutoff = record["cutoff"]
        try:
            cutoff_jst = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone(timedelta(hours=9)))
        except (ValueError, TypeError):
            cutoff_jst = None
        record["inspection_target_jst"] = (
            (cutoff_jst - timedelta(minutes=10)).isoformat()
            if cutoff_jst is not None else None)
        record["before_cutoff"] = (
            datetime.now(timezone.utc) < cutoff_jst if cutoff_jst is not None else False)
        record["snapshot_eligible"] = (
            record["data_status"] == "COMPLETE" and record["before_cutoff"])
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--races", default="5,6,7")
    args = parser.parse_args()
    try:
        race_numbers = tuple(str(int(n)) for n in args.races.split(","))
        if any(int(n) not in range(1, 13) for n in race_numbers):
            raise ValueError("races must be in 1..12")
        print(json.dumps(probe(day=args.date, races=race_numbers), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "FETCH_FAILED", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
