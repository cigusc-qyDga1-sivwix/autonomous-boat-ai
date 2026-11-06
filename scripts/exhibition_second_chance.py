"""Eligible second-chance CSV exhibition previews after first forecast publication.

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

JST = ZoneInfo("Asia/Tokyo")
SAFE_LEAD_SECONDS = 180


def _read(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def eligible_new_previews(before, after, now):
    """List race codes with CHANGED, timely, actually captured six-boat previews."""
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    day = now.astimezone(JST).date().isoformat()
    if after.get("event_date") != day:
        return []
    old = {r.get("race_code"): r.get("preview_sha256")
           for r in before.get("records", []) if isinstance(r, dict)}
    eligible = []
    for row in after.get("records", []):
        if not isinstance(row, dict):
            continue
        code, sig = row.get("race_code"), row.get("preview_sha256")
        if (not isinstance(code, str) or len(code) != 12 or not code.isdigit()
                or code[:8] != day.replace("-", "") or not sig or old.get(code) == sig
                or row.get("source_status") != "historical_research_only_not_frozen_forecast"):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    candidates = eligible_new_previews(_read(args.before), _read(args.after),
                                       datetime.now(timezone.utc))
    output = {
        "eligible": bool(candidates), "candidate_races": candidates,
        "scope": "new timely CSV previews; formalization still requires fresh live build",
    }
    print(json.dumps(output, ensure_ascii=False))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as target:
            target.write("eligible=" + str(bool(candidates)).lower() + "\n")
            target.write("candidate_count=" + str(len(candidates)) + "\n")


if __name__ == "__main__":
    main()
