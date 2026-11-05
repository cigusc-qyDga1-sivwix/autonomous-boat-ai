"""Regression checks for read-only exhibition gap diagnostics and 180s safety."""
from exhibition_rejection_audit import build, PRODUCTION_SAFE_FREEZE_LEAD_SECONDS


def row(code, venue, race, observed, boats=6, captured=None):
    r = {"race_code": code, "venue_code": venue, "race": race,
         "source_observed_jst": observed, "boats": [{}] * boats}
    if captured:
        r["preview_captured_at_utc"] = captured
    return r


def run():
    day = "2026-10-26"
    research = {"event_date": day, "records": [
        row("202610262101", "21", 1, "2026-10-26T10:20:00+09:00"),
        row("202610262102", "21", 2, "2026-10-26T10:29:00+09:00"),
        row("202610262103", "21", 3, "2026-10-26T10:20:00+09:00", 5),
        row("202610262104", "21", 4, "2026-10-26T10:20:00+09:00"),
    ]}
    ledger = {"event_date": day, "race_records": {
        "a": {"venue_code": "21", "race": 1, "cutoff_jst": "10:30",
              "versions": [{"phase": "baseline"}]},
        "b": {"venue_code": "21", "race": 2, "cutoff_jst": "10:30",
              "versions": [{"phase": "baseline"}]},
        "c": {"venue_code": "021", "race": "3", "cutoff_jst": "10:30",
              "versions": [{"phase": "baseline"}]},
    }}
    assert PRODUCTION_SAFE_FREEZE_LEAD_SECONDS == 180
    analysis = build(research, ledger)
    assert analysis["production_safe_freeze_lead_seconds"] == 180
    assert analysis["reason_counts"] == {
        "capture_evidence_missing_cannot_certify_early": 1,
        "incomplete_six_boat_exhibition": 1,
        "no_matching_forecast_record": 1,
        "source_timestamp_too_late_for_safe_freeze": 1,
    }, analysis["reason_counts"]
    assert ledger["race_records"]["a"]["versions"] == [{"phase": "baseline"}]

    delayed = {**research, "created_at_utc": "2026-10-26T02:00:00+00:00"}
    counts = build(delayed, ledger)["reason_counts"]
    assert counts == {
        "archive_created_after_safe_deadline_capture_unverified": 1,
        "incomplete_six_boat_exhibition": 1,
        "no_matching_forecast_record": 1,
        "source_timestamp_too_late_for_safe_freeze": 1,
    }, counts

    per_race = {**delayed, "records": [dict(r) for r in delayed["records"]]}
    per_race["records"][0]["first_seen_at_utc"] = "2026-10-26T01:20:00+00:00"
    corrected = build(per_race, ledger)
    assert corrected["first_seen_evidence_rows"] == 1
    assert corrected["reason_counts"] == {
        "incomplete_six_boat_exhibition": 1,
        "no_matching_forecast_record": 1,
        "not_frozen_despite_plausible_source_timestamp_investigate_runtime": 1,
        "source_timestamp_too_late_for_safe_freeze": 1,
    }, corrected["reason_counts"]
    assert corrected["race_reasons"][0]["production_safe_deadline_jst"] == (
        "2026-10-26T10:27:00+09:00"
    )
    assert corrected["race_reasons"][0]["seconds_captured_before_production_deadline"] == 420.0

    # Regress the real operational discrepancy: a 2m30s early source capture
    # falls AFTER the 3m production margin, though the 2m view gate might pass.
    today = "2026-11-05"
    current = {"event_date": today, "records": [
        row("202611050902", "09", 2, "2026-11-05T10:50:29+09:00",
            captured="2026-11-05T01:54:29+00:00"),
        row("202611052103", "21", 3, "2026-11-05T09:20:18+09:00",
            captured="2026-11-05T00:24:27+00:00"),
        row("202611050301", "03", 1, "2026-11-05T10:50:29+09:00",
            captured="2026-11-05T01:54:29+00:00"),
    ]}
    ledger_today = {"event_date": today, "race_records": {
        "09-2": {"venue_code": "9", "race": 2, "cutoff_jst": "10:57",
                  "versions": [{"phase": "baseline"}]},
        "21-3": {"venue_code": "21", "race": 3, "cutoff_jst": "09:27",
                  "versions": [{"phase": "baseline"}]},
        "3-1": {"venue_code": "3", "race": 1, "cutoff_jst": "10:59",
                 "versions": [{"phase": "baseline"}]},
    }}
    report = build(current, ledger_today)
    assert report["reason_counts"] == {
        "excluded_venue_by_operational_policy": 1,
        "research_import_after_safe_freeze_deadline": 2,
    }, report["reason_counts"]
    assert report["race_reasons"][0]["seconds_captured_before_production_deadline"] == -29.0
    assert report["race_reasons"][1]["seconds_captured_before_production_deadline"] == -27.0
    # Never mutate snapshots or pretend these were formal forecasts.
    assert ledger_today["race_records"]["09-2"]["versions"] == [{"phase": "baseline"}]


if __name__ == "__main__":
    run()
    print("exhibition rejection audit tests passed")
