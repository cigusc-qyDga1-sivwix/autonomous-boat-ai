"""Reproducible venue-wide coverage audit of archived BoatraceCSV exhibits.

Read-only: does not fetch providers, alter forecasting, or infer tide measurements.
Coverage means historical records, NOT proof of every event's pre-cutoff delivery.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from scripts.weather_tide_shadow import _freshness

VENUES = (
    "桐生","戸田","江戸川","平和島","多摩川","浜名湖",
    "蒲郡","常滑","津","三国","びわこ","住之江",
    "尼崎","鳴門","丸亀","児島","宮島","徳山",
    "下関","若松","芦屋","福岡","唐津","大村",
)


def audit_archives(files):
    by_venue = {name: {"venue": name, "races": 0, "days": set(),
                       "wind_mps_records": 0, "wave_cm_records": 0,
                       "wind_direction_records": 0, "wind_direction_undefined_calm": 0,
                       "wind_direction_undefined_noncalm": 0, "weather_clock_records": 0,
                       "weather_stale_gt20min": 0, "source_observed_post_cutoff": 0,
                       "tide_stage_records": 0} for name in VENUES}
    days = set()
    unmatched_venues = Counter()
    for file in files:
        doc = json.loads(Path(file).read_text(encoding="utf-8"))
        day = doc.get("event_date")
        datetime.strptime(day, "%Y-%m-%d")
        if day in days:
            raise ValueError(f"duplicate archive date: {day}")
        days.add(day)
        if not isinstance(doc.get("records"), list):
            raise ValueError(f"missing records for {day}")
        for record in doc["records"]:
            name = record.get("venue")
            if name not in by_venue:
                unmatched_venues[str(name)] += 1
                continue
            slot = by_venue[name]
            slot["days"].add(day)
            slot["races"] += 1
            weather = record.get("weather") or {}
            wind = weather.get("wind_mps")
            wave = weather.get("wave_cm")
            valid_wind = (isinstance(wind, (int,float)) and not isinstance(wind,bool)
                          and 0 <= wind <= 70)
            valid_wave = (isinstance(wave, (int,float)) and not isinstance(wave,bool)
                          and 0 <= wave <= 150)
            if valid_wind: slot["wind_mps_records"] += 1
            if valid_wave: slot["wave_cm_records"] += 1
            direction = weather.get("wind_direction_number")
            if direction is not None:
                slot["wind_direction_records"] += 1
            elif valid_wind and wind == 0:
                slot["wind_direction_undefined_calm"] += 1
            else:
                slot["wind_direction_undefined_noncalm"] += 1
            freshness = _freshness(record)
            if freshness["observed_at_jst"] is not None:
                slot["weather_clock_records"] += 1
            if freshness["status"] == "stale":
                slot["weather_stale_gt20min"] += 1
            stamp = freshness["source_observed_jst"]
            cutoff = record.get("cutoff_jst")
            if stamp and cutoff:
                try:
                    src_dt = datetime.fromisoformat(stamp)
                    if src_dt > datetime.fromisoformat(f"{day}T{cutoff}:00+09:00"):
                        slot["source_observed_post_cutoff"] += 1
                except (ValueError, TypeError):
                    pass
            # No tide fields in this source: not evidence of 0 tide or no current.
    entries = [{**s, "days": len(s["days"]), "tide_status": "separate_provider_not_integrated",
                "forecast_eligible": False}
               for s in by_venue.values()]
    counts = {field: sum(row[field] for row in entries) for field in (
        "races", "wind_mps_records", "wave_cm_records", "wind_direction_records",
        "wind_direction_undefined_calm", "wind_direction_undefined_noncalm",
        "weather_clock_records", "weather_stale_gt20min", "source_observed_post_cutoff",
        "tide_stage_records"
    )}
    return {
        "schema": "boatlabs.venue_source_coverage.v1",
        "date_range": {"from": min(days) if days else None, "to": max(days) if days else None,
                       "archive_days": len(days)},
        "status": "historical_research_archive_only",
        "formal_model_changed": False,
        "sources": [str(p) for p in files],
        "summary": {**counts, "venues_with_wind": sum(x["wind_mps_records"]>0 for x in entries),
                    "venues_with_wave": sum(x["wave_cm_records"]>0 for x in entries),
                    "venues_with_tide": 0,
                    "stale_warning_minutes": 20,
                    "unsupported_venue_rows": dict(unmatched_venues)},
        "venues": entries,
        "warnings": [
            "Historical archive coverage does not prove complete or timely pre-cutoff acquisition.",
            "Direction is undefined at zero wind; do not count calm as data failure.",
            "A stale warning threshold of 20 minutes is experimental, not a formal safety gate.",
            "Tides/currents require independent time-stamped station data and site mapping.",
            "Edogawa is reported for audit coverage but excluded from the formal prediction scope."
        ]
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-dir", default="app/data/exhibition")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", help="Optional path under reports/")
    args = parser.parse_args(argv)
    try:
        first = datetime.strptime(args.start, "%Y-%m-%d").date()
        last = datetime.strptime(args.end, "%Y-%m-%d").date()
        if first > last: raise ValueError("start after end")
    except ValueError as exc:
        parser.error(str(exc))
    files = sorted(p for p in Path(args.archive_dir).glob("????-??-??.json")
                   if args.start <= p.stem <= args.end)
    if not files:
        parser.error("no archive files matched")
    result = audit_archives(files)
    result["date_range"]["requested_start"] = args.start
    result["date_range"]["requested_end"] = args.end
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = Path(args.output).resolve()
        reports = Path("reports").resolve()
        if not target.is_relative_to(reports):
            parser.error("coverage output must be inside reports/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return result


if __name__ == "__main__":
    main()
