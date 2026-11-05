"""Research-only weather/wave/tide audit tests; no primary prediction imports."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.weather_tide_shadow import analyze, main


def mikuni_three():
    return {
        "race_code": "202611051003", "venue": "三国", "race": 3,
        "cutoff_jst": "09:39",
        "source_observed_jst": "2026-11-05T09:30:31+09:00",
        "weather": {"wind_mps": 2, "wave_cm": 2,
                    "wind_direction_number": 4, "observed_time_jst": "0850"}
    }


class WeatherTideShadowTests(unittest.TestCase):
    def test_mikuni_weather_age_not_hidden_by_fresh_exhibition(self):
        result = analyze(mikuni_three())
        self.assertEqual(result["weather"]["freshness"]["status"], "stale")
        self.assertEqual(result["weather"]["freshness"]["age_at_source_minutes"], 40.5)
        self.assertEqual(result["weather"]["freshness"]["age_at_cutoff_minutes"], 49.0)
        self.assertEqual(result["weather"]["wind_orientation"]["status"], "unverified_geometry")

    def test_wind_direction_number_never_inferred_as_headwind(self):
        rec = mikuni_three()
        rec["weather"]["wind_mps"] = 8
        self.assertIsNone(analyze(rec)["weather"]["wind_orientation"]["wind_relative_to_start"])
        rec["research_verified_geometry"] = {
            "wind_bearing_verified": True, "start_to_first_mark_bearing_verified": True,
            "wind_from_true_degrees": 90,
            "start_to_first_mark_true_degrees": 90
        }
        self.assertEqual(analyze(rec)["weather"]["wind_orientation"]["wind_relative_to_start"], "headwind")
        rec["research_verified_geometry"]["wind_from_true_degrees"] = 270
        self.assertEqual(analyze(rec)["weather"]["wind_orientation"]["wind_relative_to_start"], "tailwind")

    def test_valid_tide_stage_does_not_infer_current(self):
        t = {
            "venue_station_mapping_verified": True, "station_id": "verified-test-station",
            "source_url": "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/index.php",
            "kind": "astronomical_prediction", "datum": "station_chart_datum",
            "captured_at_utc": "2026-11-04T23:45:00+00:00",
            "points": [
                {"time_jst": "2026-11-05T08:00:00+09:00", "level_cm": 100},
                {"time_jst": "2026-11-05T09:00:00+09:00", "level_cm": 115}
            ],
        }
        tide = analyze(mikuni_three(), t)["tide"]
        self.assertEqual(tide["stage"], "rising")
        self.assertEqual(tide["change_cm_per_hour"], 15)
        self.assertEqual(tide["current_direction"], "unknown")
        self.assertEqual(tide["status"], "research_valid_not_current")

    def test_unknown_tide_station_cannot_create_tide_stage(self):
        t = {"venue_station_mapping_verified": False, "station_id": "nearby",
             "source_url": "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/index.php",
             "kind": "observed", "datum": "TP", "captured_at_utc": "2026-11-05T00:25:00Z",
             "points": []}
        self.assertEqual(analyze(mikuni_three(), t)["tide"]["stage"], None)

    def test_late_tide_capture_is_not_pretended_pre_cutoff(self):
        t = {"venue_station_mapping_verified": True, "station_id": "verified-test",
             "source_url": "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/index.php",
             "kind": "observed", "datum": "TP", "captured_at_utc": "2026-11-05T01:00:00Z",
             "points": [{"time_jst": "2026-11-05T08:00:00+09:00", "level_cm": 100},
                        {"time_jst": "2026-11-05T09:00:00+09:00", "level_cm": 110}]}
        self.assertEqual(analyze(mikuni_three(), t)["tide"]["status"],
                         "capture_time_unverified_or_late")

    def test_no_bets_or_forecast_mutations(self):
        rec = mikuni_three()
        original = copy.deepcopy(rec)
        result = analyze(rec)
        self.assertEqual(rec, original)
        self.assertNotIn("bets", result)
        self.assertEqual(result["forecast_integration"], "none")

    def test_cli_research_report_is_opt_in_and_date_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/"source.json"
            out = Path(temp)/"audit.json"
            source.write_text(json.dumps({"event_date": "2026-11-05",
                                           "records": [mikuni_three()]}, ensure_ascii=False))
            result = main(["--date", "2026-11-05", "--archive", str(source),
                           "--output", str(out)])
            saved = json.loads(out.read_text())
            self.assertFalse(saved["formal_predictions_changed"])
            self.assertEqual(result["summary"]["stale_weather"], 1)
            self.assertEqual(result["summary"]["tide_unavailable"], 1)

    def test_cannot_overwrite_source_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/"source.json"
            original = json.dumps({"event_date": "2026-11-05",
                                   "records": [mikuni_three()]}, ensure_ascii=False)
            archive.write_text(original, encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["--date", "2026-11-05", "--archive", str(archive),
                      "--output", str(archive)])
            self.assertEqual(archive.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
