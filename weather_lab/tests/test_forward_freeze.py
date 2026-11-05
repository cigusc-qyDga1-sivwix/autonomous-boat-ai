"""Tests for first-observation immutability and true pre-cutoff gating."""
import copy
import unittest
from datetime import datetime

from weather_lab.forward_freeze import freeze, SCHEMA


def snapshot(collection="2026-11-06T00:30:00+00:00", cutoff="09:39", wind=5,
             status="fresh_snapshot", captured="2026-11-06T09:29:00+09:00",
             observed="2026-11-06T09:26:00+09:00"):
    return {
        "schema": "weather_lab.water_surface_monitor.v1",
        "event_date": "2026-11-06", "collected_at_utc": collection,
        "provider": {"fetch_status": "ok"},
        "races": [{
            "race_code": "202611061003", "venue_code": "10", "venue": "三国", "race": 3,
            "cutoff_jst": cutoff, "freshness_status": status,
            "source_captured_at_jst": captured, "weather_observed_at_jst": observed,
            "weather": {"wind_mps": wind, "wave_cm": 5,
                        "wind_direction_raw_code": 4, "air_c": 13, "water_c": 15},
            "weather_advisory": {"signals": ["wind_ge_5mps", "wave_ge_5cm"]},
        }],
    }


class ForwardFreezeTests(unittest.TestCase):
    def test_before_cutoff_immutable_witness_and_no_prediction(self):
        doc, n = freeze(snapshot())
        self.assertEqual(n, 1)
        self.assertEqual(doc["schema"], SCHEMA)
        self.assertEqual(len(doc["records"]), 1)
        r = doc["records"][0]
        self.assertEqual(r["weather"]["wind_mps"], 5)
        self.assertEqual(len(r["weather_evidence_sha256"]), 64)
        self.assertIsNone(r["prediction_sha"])
        self.assertEqual(r["weather_effect_on_predictions"], "not_applied")

    def test_first_witness_not_overwritten_after_outcome_or_new_weather(self):
        old, _ = freeze(snapshot())
        new = snapshot(collection="2026-11-06T00:31:00+00:00", wind=10,
                       captured="2026-11-06T09:30:00+09:00")
        archive, n = freeze(new, old)
        self.assertEqual(n, 0)
        self.assertEqual(archive, old)
        self.assertEqual(archive["records"][0]["weather"]["wind_mps"], 5)

    def test_three_minute_safety_deadline_enforced(self):
        # Race closes 09:39, safe deadline 09:36.
        late = snapshot(collection="2026-11-06T00:37:00+00:00",
                        captured="2026-11-06T09:36:00+09:00",
                        observed="2026-11-06T09:35:00+09:00")
        self.assertEqual(freeze(late)[0]["records"], [])

    def test_stale_or_fake_fresh_flag_rejected(self):
        self.assertEqual(freeze(snapshot(status="stale_observation"))[0]["records"], [])
        bad = snapshot(observed="2026-11-06T08:00:00+09:00")
        self.assertEqual(freeze(bad)[0]["records"], [])
        bad = snapshot(captured="2026-11-06T09:31:00+09:00")
        self.assertEqual(freeze(bad)[0]["records"], [])

    def test_absent_forecast_does_not_generate_model_predictions(self):
        x = snapshot()
        x["races"][0]["weather"]["wind_mps"] = None
        self.assertEqual(freeze(x)[0]["records"], [])
        self.assertEqual(freeze({"schema": "weather_lab.water_surface_monitor.v1",
                               "event_date": "2026-11-06",
                               "collected_at_utc": "2026-11-06T00:30:00+00:00",
                               "provider": {"fetch_status": "unavailable"},
                               "races": []})[0]["records"], [])

    def test_previous_archive_mismatch_blocks_overwrite(self):
        prev, _ = freeze(snapshot())
        prev = copy.deepcopy(prev)
        prev["event_date"] = "2026-11-05"
        with self.assertRaises(ValueError):
            freeze(snapshot(), prev)

    def test_old_day_with_new_collection_time_rejected(self):
        with self.assertRaises(ValueError):
            freeze(snapshot(collection="2026-11-05T23:50:00+00:00"))


if __name__ == "__main__":
    unittest.main()
