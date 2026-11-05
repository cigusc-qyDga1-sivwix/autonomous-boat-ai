"""Offline source/quality tests for WEATHER LAB; never call a live race source."""
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from weather_lab.monitor import VENUES, build, main

NOW = datetime.fromisoformat("2026-11-05T00:35:00+00:00")
DAY = date(2026, 11, 5)
HEADER = "レースコード,レース日,レース場,レース回,締切時刻,取得日時,気象観測時刻,風速(m),風向,波の高さ(cm),天候,気温(℃),水温(℃)\n"


def csv_row(code="202611051003", venue="10", clock="0850", wind="2", direction="4",
            wave="2", captured="2026-11-05T09:30:00+09:00", race="03R", day="2026-11-05"):
    return ",".join([code, day, venue, race, "09:39", captured, clock,
                     wind, direction, wave, "1", "13", "15"]) + "\n"


class WeatherLabTests(unittest.TestCase):
    def test_always_reports_24_venues_and_no_fake_tides(self):
        snapshot = build(HEADER + csv_row(), NOW, DAY)
        self.assertEqual(len(VENUES), 24)
        self.assertEqual(len(snapshot["venues"]), 24)
        self.assertEqual(snapshot["summary"]["race_snapshots"], 1)
        self.assertEqual(snapshot["summary"]["venues_with_snapshots"], 1)
        self.assertEqual(snapshot["venues"][2]["name"], "江戸川")
        self.assertFalse(snapshot["venues"][2]["boat_lab_prediction_in_scope"])
        self.assertEqual(snapshot["venues"][2]["monitor_status"], "no_race_snapshot")
        self.assertEqual(snapshot["venues"][9]["name"], "三国")
        self.assertEqual(snapshot["venues"][9]["monitor_status"], "stale_observation")
        self.assertTrue(all(v["tide"]["height_cm"] is None for v in snapshot["venues"]))
        self.assertTrue(snapshot["scope"]["no_formal_forecast_integration"])

    def test_weather_observation_age_is_not_the_source_age(self):
        rec = build(HEADER + csv_row(), NOW, DAY)["races"][0]
        self.assertEqual(rec["source_age_minutes"], 5)
        self.assertEqual(rec["weather_age_minutes"], 45)
        self.assertEqual(rec["freshness_status"], "stale_observation")
        self.assertFalse(rec["forecast_eligible"])
        self.assertTrue(rec["weather_date_inferred_from_race_day"])

    def test_fresh_snapshot_with_observed_time(self):
        rec = build(HEADER + csv_row(clock="0930"), NOW, DAY)["races"][0]
        self.assertEqual(rec["freshness_status"], "fresh_snapshot")
        self.assertEqual(rec["weather_age_minutes"], 5)

    def test_zero_wind_undefined_direction_not_outage(self):
        rec = build(HEADER + csv_row(clock="0930", wind="0", direction=""), NOW, DAY)["races"][0]
        self.assertEqual(rec["weather"]["wind_direction_status"], "calm_undefined")
        self.assertEqual(rec["freshness_status"], "fresh_snapshot")

    def test_invalid_venue_and_wrong_date_are_rejected(self):
        invalid = (
            csv_row(code="202611052501", venue="25")
            + csv_row(code="202611041003", day="2026-11-04")
        )
        summary = build(HEADER + invalid, NOW, DAY)["summary"]
        self.assertEqual(summary["race_snapshots"], 0)
        self.assertEqual(sum(summary["rejected_rows"].values()), 2)

    def test_mismatched_metadata_and_invalid_cutoff_do_not_enter_monitor(self):
        wrong = csv_row(venue="09") + csv_row(race="04R")
        doc = build(HEADER + wrong, NOW, DAY)
        self.assertEqual(doc["summary"]["race_snapshots"], 0)
        self.assertEqual(doc["summary"]["rejected_rows"]["mismatched_race_identity_columns"], 2)
        invalid = csv_row().replace(",09:39,", ",29:99,")
        bad = build(HEADER + invalid, NOW, DAY)
        self.assertEqual(bad["summary"]["rejected_rows"]["invalid_cutoff_clock"], 1)

    def test_latest_valid_source_capture_wins_without_fabricating_weather(self):
        older = csv_row(clock="0850", captured="2026-11-05T09:28:00+09:00")
        newer = csv_row(clock="0931", captured="2026-11-05T09:31:00+09:00")
        doc = build(HEADER + older + newer, NOW, DAY)
        self.assertEqual(doc["summary"]["race_snapshots"], 1)
        self.assertEqual(doc["races"][0]["weather_age_minutes"], 4.0)
        self.assertEqual(doc["races"][0]["freshness_status"], "fresh_snapshot")

    def test_source_timestamp_in_future_cannot_be_accepted(self):
        future = csv_row(captured="2026-11-05T09:50:00+09:00")
        doc = build(HEADER + future, NOW, DAY)
        self.assertEqual(doc["summary"]["race_snapshots"], 0)
        self.assertEqual(doc["summary"]["rejected_rows"]["future_source_timestamp"], 1)

    def test_unavailable_provider_not_marked_as_calm_or_zero(self):
        doc = build("", NOW, DAY, fetch_error="HTTPError")
        self.assertEqual(doc["provider"]["fetch_status"], "unavailable")
        self.assertEqual(doc["summary"]["race_snapshots"], 0)
        self.assertTrue(all(v["monitor_status"] == "provider_unavailable" for v in doc["venues"]))

    def test_no_valid_observation_time_is_not_fresh(self):
        rec = build(HEADER + csv_row(clock="25ZZ"), NOW, DAY)["races"][0]
        self.assertEqual(rec["freshness_status"], "observation_time_unverified")
        self.assertIsNone(rec["weather_observed_at_jst"])

    def test_missing_wind_not_replaced_by_guess(self):
        rec = build(HEADER + csv_row(wind="", clock="0930"), NOW, DAY)["races"][0]
        self.assertEqual(rec["freshness_status"], "incomplete_values")
        self.assertIsNone(rec["weather"]["wind_mps"])
        self.assertEqual(rec["weather"]["wind_direction_status"], "present_unmapped")

    def test_fixture_writes_only_independent_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            csvfile = Path(tmp) / "fixture.csv"
            output = Path(tmp) / "weather"
            csvfile.write_text(HEADER + csv_row(), encoding="utf-8")
            result = main(["--fixture", str(csvfile), "--date", "2026-11-05",
                           "--now-iso", "2026-11-05T00:35:00+00:00",
                           "--out-dir", str(output)])
            self.assertTrue((output / "latest.json").is_file())
            self.assertTrue((output / "2026-11-05.json").is_file())
            self.assertEqual(json.loads((output/"latest.json").read_text())["schema"], result["schema"])

    def test_source_error_does_not_create_dated_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            from weather_lab.monitor import write_json
            doc = build("", NOW, DAY, fetch_error="URLError")
            target = Path(tmp) / "latest.json"
            write_json(target, doc)
            self.assertEqual(json.loads(target.read_text())["provider"]["fetch_status"], "unavailable")
            self.assertFalse((Path(tmp) / "2026-11-05.json").exists())


if __name__ == "__main__":
    unittest.main()
