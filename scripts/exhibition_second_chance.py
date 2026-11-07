"""Eligible second-chance exhibition previews after first forecast publication.

This gate decides only whether an extra PRE-CUTOFF build is worth running.
It cannot formalize an archived research record or override the immutable
forecast's own per-race 180-second wall-clock/completion-time safety checks.
No race results, payouts, or historical outcome fields are read.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .autonomous_daily import cutoff_of, preview_complete, retrieve, valid_entrants

JST = ZoneInfo("Asia/Tokyo")
SAFE_LEAD_SECONDS = 180


def _read(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _model_inputs(row):
    """Ignore refreshed timestamps and post-race fields; watch measured inputs."""
    return {
        "boats": [{k: boat.get(k) for k in (
            "course", "exhibition_st", "exhibition_time", "tilt",
            "weight_kg", "original_exhibition")} for boat in row.get("boats", [])
            if isinstance(boat, dict)],
        "weather": {k: (row.get("weather") or {}).get(k) for k in (
            "wind_mps", "wind_direction_number", "wave_cm",
            "air_c", "water_c")},
    }


def eligible_new_previews(before, after, now):
    """List race codes with CHANGED, timely, actually captured six-boat previews."""
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    day = now.astimezone(JST).date().isoformat()
    if after.get("event_date") != day:
        return []
    old = {r.get("race_code"): r
           for r in before.get("records", []) if isinstance(r, dict)}
    eligible = []
    for row in after.get("records", []):
        if not isinstance(row, dict):
            continue
        code, sig = row.get("race_code"), row.get("preview_sha256")
        if (not isinstance(code, str) or len(code) != 12 or not code.isdigit()
                or code[:8] != day.replace("-", "") or not sig
                or row.get("source_status") != "historical_research_only_not_frozen_forecast"):
            continue
        prior = old.get(code)
        if (prior and (prior.get("preview_sha256") == sig
                       or _model_inputs(prior) == _model_inputs(row))):
            continue
        boats = row.get("boats")
        if (not isinstance(boats, list) or len(boats) != 6
                or {b.get("course") for b in boats if isinstance(b, dict)} != set(range(1, 7))
                or any(not isinstance(b, dict) or b.get("exhibition_st") is None
                       or b.get("exhibition_time") is None for b in boats)):
            continue
        try:
            cutoff = datetime.fromisoformat(day + "T" + row["cutoff_jst"] + ":00+09:00")
            observed = datetime.fromisoformat(row["source_observed_jst"])
            captured = datetime.fromisoformat(row["preview_captured_at_utc"])
        except (KeyError, ValueError, TypeError):
            continue
        if (observed.tzinfo is None or captured.tzinfo is None
                or observed.astimezone(JST).date().isoformat() != day):
            continue
        deadline = cutoff - timedelta(seconds=SAFE_LEAD_SECONDS)
        if (now >= deadline or observed >= deadline or captured >= deadline
                or captured > now + timedelta(seconds=30)
                or captured.astimezone(JST).date().isoformat() != day):
            continue
        eligible.append(code)
    return sorted(set(eligible))


def pending_api_races(ledger, now):
    """Limit extra reads to nearby races with a baseline but no exhibition."""
    day = now.astimezone(JST).date().isoformat()
    if ledger.get("event_date") != day:
        return []
    pending = []
    for key, record in ledger.get("race_records", {}).items():
        venue, _, race_number = key.partition("-")
        versions = record.get("versions", [])
        if (not venue.isdigit() or not race_number.isdigit() or int(venue) == 3
                or not versions or any(v.get("phase") == "exhibition" for v in versions)):
            continue
        try:
            cutoff = datetime.fromisoformat(day + "T" + record["cutoff_jst"] + ":00+09:00")
        except (KeyError, TypeError, ValueError):
            continue
        if now + timedelta(seconds=SAFE_LEAD_SECONDS) < cutoff <= now + timedelta(minutes=20):
            pending.append((str(int(venue)), str(int(race_number))))
    return pending


def eligible_api_previews(ledger, payload, now):
    """Use the same complete-preview and cutoff gates as the forecast."""
    stadiums = (payload.get("programs") or {}).get("stadiums") or {}
    day = now.astimezone(JST).strftime("%Y%m%d")
    eligible = []
    for venue, number in pending_api_races(ledger, now):
        race = (stadiums.get(venue, {}).get("races") or {}).get(number)
        if not isinstance(race, dict):
            continue
        cutoff = cutoff_of(race)
        if (cutoff is None or cutoff.date() != now.astimezone(JST).date()
                or now + timedelta(seconds=SAFE_LEAD_SECONDS) >= cutoff
                or not valid_entrants(race) or not preview_complete(race)):
            continue
        eligible.append(day + venue.zfill(2) + number.zfill(2))
    return sorted(eligible)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    candidates = eligible_new_previews(_read(args.before), _read(args.after),
                                       datetime.now(timezone.utc))
    if not candidates and args.ledger:
        ledger = _read(args.ledger)
        now = datetime.now(timezone.utc)
        if pending_api_races(ledger, now):
            try:
                payload, _ = retrieve(now.astimezone(JST).strftime("%Y%m%d"))
                candidates = eligible_api_previews(ledger, payload, datetime.now(timezone.utc))
            except (OSError, ValueError) as exc:
                print(f"::warning::Open API exhibition recheck failed: {exc}")
    output = {
        "eligible": bool(candidates), "candidate_races": candidates,
        "scope": "new timely CSV or Open API previews; formalization still requires fresh live build",
    }
    print(json.dumps(output, ensure_ascii=False))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as target:
            target.write("eligible=" + str(bool(candidates)).lower() + "\n")
            target.write("candidate_count=" + str(len(candidates)) + "\n")


if __name__ == "__main__":
    main()
