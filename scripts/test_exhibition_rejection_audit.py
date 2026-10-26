"""Regression checks for read-only exhibition gap diagnostics."""
from exhibition_rejection_audit import build


def row(code, venue, race, observed, boats=6):
    return {"race_code": code, "venue_code": venue, "race": race,
            "source_observed_jst": observed, "boats": [{}] * boats}


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
    counts = build(research, ledger)["reason_counts"]
    assert counts == {
        "incomplete_six_boat_exhibition": 1,
        "no_matching_forecast_record": 1,
        "not_frozen_despite_plausible_source_timestamp_investigate_runtime": 1,
        "source_timestamp_too_late_for_safe_freeze": 1,
    }, counts
    assert ledger["race_records"]["a"]["versions"] == [{"phase": "baseline"}]
    delayed = {**research, "created_at_utc": "2026-10-26T02:00:00+00:00"}
    delayed_counts = build(delayed, ledger)["reason_counts"]
    assert delayed_counts == {
        "incomplete_six_boat_exhibition": 1,
        "no_matching_forecast_record": 1,
        "research_import_after_safe_freeze_deadline": 2,
    }, delayed_counts
    per_race = {**delayed, "records": [dict(r) for r in delayed["records"]]}
    per_race["records"][0]["first_seen_at_utc"] = "2026-10-26T01:20:00+00:00"
    corrected = build(per_race, ledger)
    assert corrected["first_seen_evidence_rows"] == 1
    assert corrected["reason_counts"] == {
        "incomplete_six_boat_exhibition": 1,
        "no_matching_forecast_record": 1,
        "not_frozen_despite_plausible_source_timestamp_investigate_runtime": 1,
        "research_import_after_safe_freeze_deadline": 1,
    }, corrected["reason_counts"]


if __name__ == "__main__":
    run()
    print("exhibition rejection audit tests passed")
