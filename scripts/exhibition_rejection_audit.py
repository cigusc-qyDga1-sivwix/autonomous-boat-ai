"""Explain why collected exhibition research rows are not formal frozen forecasts.

Historical timestamps cannot certify live pre-cutoff availability. This report
never edits prediction snapshots or treats retrospective data as a forecast.
"""
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1] / "app" / "data"


def build(research, ledger, now=None):
    day = research.get("event_date")
    if not day or day != ledger.get("event_date"):
        raise ValueError("Research and ledger must be from the same JST date")
    records = ledger.get("race_records") or {}
    reasons = Counter()
    details = []
    for row in research.get("records") or []:
        code = str(row.get("race_code") or "")
        venue = str(row.get("venue_code") or "")
        number = row.get("race")
        matching = next((r for r in records.values()
                         if str(r.get("venue_code")) == venue and r.get("race") == number), None)
        if not matching:
            reason = "no_matching_forecast_record"
        elif any(v.get("phase") == "exhibition" for v in matching.get("versions", [])):
            reason = "exhibition_snapshot_present_check_formal_gate"
        elif len(row.get("boats") or []) != 6:
            reason = "incomplete_six_boat_exhibition"
        else:
            try:
                cutoff = datetime.fromisoformat(day + "T" + matching["cutoff_jst"] + ":00+09:00")
                observed = datetime.fromisoformat(row["source_observed_jst"]).astimezone(JST)
                if observed >= cutoff - timedelta(seconds=120):
                    reason = "source_timestamp_too_late_for_safe_freeze"
                elif observed < cutoff - timedelta(minutes=35):
                    reason = "source_timestamp_outside_bridge_window"
                else:
                    reason = "not_frozen_despite_plausible_source_timestamp_investigate_runtime"
            except (KeyError, ValueError, TypeError):
                reason = "invalid_or_missing_timestamp"
        reasons[reason] += 1
        details.append({"race_code": code, "reason": reason})
    return {
        "event_date": day,
        "classification": "retrospective_diagnostic_not_live_eligibility",
        "research_rows_checked": len(details),
        "reason_counts": dict(sorted(reasons.items())),
        "race_reasons": details,
        "warning": "Source timestamps alone do not prove the runner received data before cutoff.",
    }


def main():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    research = json.loads((ROOT / "exhibition" / (args.date + ".json")).read_text())
    ledger = json.loads((ROOT / "live" / (args.date + ".json")).read_text())
    report = build(research, ledger)
    out = ROOT / "exhibition" / "rejection-audit-latest.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["reason_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
