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
# autonomous_daily.build(enforce_wall_clock=True) uses max(120, 180) seconds.
# This diagnostic MUST classify against production's 180-second deadline;
# the separate display/eligibility gate permits 120 seconds for old snapshots.
PRODUCTION_SAFE_FREEZE_LEAD_SECONDS = 180


def build(research, ledger, now=None):
    day = research.get("event_date")
    if not day or day != ledger.get("event_date"):
        raise ValueError("Research and ledger must be from the same JST date")
    records = ledger.get("race_records") or {}
    by_race = {(str(int(r.get("venue_code"))), int(r.get("race"))): r
               for r in records.values()
               if str(r.get("venue_code", "")).isdigit()
               and str(r.get("race", "")).isdigit()}
    reasons = Counter()
    details = []
    for row in research.get("records") or []:
        code = str(row.get("race_code") or "")
        venue = str(row.get("venue_code") or "")
        number = row.get("race")
        matching = by_race.get((str(int(venue)), int(number))) if venue.isdigit() and str(number).isdigit() else None
        deadline = None
        seconds_before_production_deadline = None
        verified_capture_evidence = bool(row.get("preview_captured_at_utc") or row.get("first_seen_at_utc"))
        # Excluded venue is an operational choice, not a failed capture.
        # Linked-primary activation is 2026-11-05 08:15 JST; today's
        # Edogawa race cutoffs all occur after that activation.
        if venue.isdigit() and int(venue) == 3 and day >= "2026-11-05":
            reason = "excluded_venue_by_operational_policy"
        elif not matching:
            reason = "no_matching_forecast_record"
        elif any(v.get("phase") == "exhibition" for v in matching.get("versions", [])):
            reason = "exhibition_snapshot_present_check_formal_gate"
        elif len(row.get("boats") or []) != 6:
            reason = "incomplete_six_boat_exhibition"
        else:
            try:
                cutoff = datetime.fromisoformat(day + "T" + matching["cutoff_jst"] + ":00+09:00")
                safe_deadline = cutoff - timedelta(seconds=PRODUCTION_SAFE_FREEZE_LEAD_SECONDS)
                deadline = safe_deadline.isoformat()
                source = datetime.fromisoformat(row["source_observed_jst"])
                if source.tzinfo is None:
                    raise ValueError("Source observation missing timezone")
                observed = source.astimezone(JST)
                collected_raw = (row.get("preview_captured_at_utc")
                                 or row.get("first_seen_at_utc"))
                captured = datetime.fromisoformat(collected_raw) if collected_raw else None
                if captured is not None and captured.tzinfo is None:
                    raise ValueError("Capture evidence missing timezone")
                if captured is not None:
                    seconds_before_production_deadline = round(
                        (safe_deadline - captured.astimezone(JST)).total_seconds(), 1)
                archive_created_raw = research.get("created_at_utc")
                archive_created = (datetime.fromisoformat(archive_created_raw)
                                   if archive_created_raw else None)
                if captured is not None and captured.astimezone(JST) >= safe_deadline:
                    reason = "research_import_after_safe_freeze_deadline"
                elif observed >= safe_deadline:
                    reason = "source_timestamp_too_late_for_safe_freeze"
                elif observed < cutoff - timedelta(minutes=35):
                    reason = "source_timestamp_outside_bridge_window"
                elif captured is None:
                    # A date-level archive creation timestamp can disprove
                    # early collection, but can never prove a specific race was
                    # already available at forecast time.
                    reason = ("archive_created_after_safe_deadline_capture_unverified"
                              if archive_created is not None and
                              archive_created.tzinfo is not None and
                              archive_created.astimezone(JST) >= safe_deadline
                              else "capture_evidence_missing_cannot_certify_early")
                else:
                    # Capture evidence precedes the 180s limit, but no formal
                    # snapshot exists: investigate live fetch, gate, or runtime.
                    reason = "not_frozen_despite_plausible_source_timestamp_investigate_runtime"
            except (KeyError, ValueError, TypeError):
                reason = "invalid_or_missing_timestamp"
        reasons[reason] += 1
        details.append({"race_code": code, "reason": reason,
                        "first_seen_at_utc": row.get("first_seen_at_utc"),
                        "preview_captured_at_utc": row.get("preview_captured_at_utc"),
                        "source_observed_jst": row.get("source_observed_jst"),
                        "production_safe_deadline_jst": deadline,
                        "seconds_captured_before_production_deadline":
                            seconds_before_production_deadline,
                        "has_per_race_capture_evidence": verified_capture_evidence})
    return {
        "event_date": day,
        "classification": "retrospective_diagnostic_not_live_eligibility",
        "research_rows_checked": len(details),
        "production_safe_freeze_lead_seconds": PRODUCTION_SAFE_FREEZE_LEAD_SECONDS,
        "first_seen_evidence_rows": sum(bool(r.get("first_seen_at_utc")) for r in research.get("records") or []),
        "reason_counts": dict(sorted(reasons.items())),
        "race_reasons": details,
        "warning": "The operational wall-clock freeze gate requires 180s, whereas the view gate checks 120s. Research capture timestamps are not proof of an earlier live forecast run; archive timestamps cannot certify formal eligibility.",
    }


def main():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    research_path = ROOT / "exhibition" / (args.date + ".json")
    ledger_path = ROOT / "live" / (args.date + ".json")
    if research_path.exists() and ledger_path.exists():
        research = json.loads(research_path.read_text())
        ledger = json.loads(ledger_path.read_text())
        report = build(research, ledger)
        report["status"] = "analyzed"
    else:
        report = {"event_date": args.date, "status": "inputs_missing",
                  "research_file_present": research_path.exists(),
                  "ledger_file_present": ledger_path.exists(),
                  "research_rows_checked": 0, "reason_counts": {}, "race_reasons": [],
                  "warning": "Diagnostic inputs missing; this is not proof of no exhibition gaps."}
    out = ROOT / "exhibition" / "rejection-audit-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["reason_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
