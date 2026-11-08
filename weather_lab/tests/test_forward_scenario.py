"""Forward-only WEATHER LAB context: timing, provenance and immutable controls."""
from __future__ import annotations
import copy
import unittest
from datetime import datetime, timedelta, timezone
from weather_lab.forward_scenario import build

NOW = datetime.fromisoformat("2026-11-08T00:10:00+00:00")
DAY = "2026-11-08"


def wave():
    return {"schema": "weather_lab.water_surface_monitor.v1",
            "event_date": DAY, "collected_at_utc": "2026-11-08T00:08:00+00:00",
            "provider": {"fetch_status": "ok"},
            "races": [{
                "race_code": "202611082102", "venue_code": "21", "venue": "芦屋",
                "race": 2, "cutoff_jst": "09:25",
                "source_captured_at_jst": "2026-11-08T09:07:00+09:00",
                "weather_observed_at_jst": "2026-11-08T09:05:00+09:00",
                "freshness_status": "fresh_snapshot",
                "weather": {"wave_cm": 7},
            }]}


def regional():
    return {"schema": "weather_lab.regional_jma_forecast.v1", "event_date": DAY,
            "retrieved_at_utc": "2026-11-08T00:00:00+00:00",
            "provider": {"fetch_status": "ok"},
            "venues": [
                {"code": f"{i:02d}", "hourly": [{
                    "valid_at_jst": "2026-11-08T09:00:00+09:00",
                    "wind_mps": 6.4, "wind_direction_degrees": 84,
                }]} for i in range(1, 25)]}


class ScenarioForwardTests(unittest.TestCase):
    def test_pre_cutoff_joint_cue_and_no_main_change(self):
        w, m = wave(), regional()
        saved_w, saved_m = copy.deepcopy(w), copy.deepcopy(m)
        doc, new = build(w, m, NOW)
        self.assertEqual(new, 1)
        row = doc["records"][0]
        self.assertEqual(row["race_code"], "202611082102")
        self.assertEqual(row["status"], "research_attention")
        self.assertIn("wind_wave_joint_attention", row["signals"])
        self.assertTrue(row["regional_wind_is_observation"] is False)
        self.assertEqual(row["headwind_tailwind"], "unverified_not_inferred")
        self.assertEqual(row["local_tide_current"], "unavailable_not_inferred")
        self.assertFalse(row["bets_changed"])
        self.assertFalse(row["formal_prediction_modified"])
        self.assertEqual(len(row["evidence_sha256"]), 64)
        self.assertEqual(w, saved_w)
        self.assertEqual(m, saved_m)

    def test_first_frozen_evidence_cannot_be_rewritten(self):
        first, _ = build(wave(), regional(), NOW)
        later = wave()
        later["races"][0]["weather"]["wave_cm"] = 1
        changed, count = build(later, regional(), NOW + timedelta(minutes=1), first)
        self.assertEqual(count, 0)
        self.assertEqual(changed, first)

    def test_fails_closed_post_cutoff_and_stale(self):
        self.assertEqual(build(wave(), regional(), NOW + timedelta(minutes=13))[1], 0)
        stale = wave()
        stale["races"][0]["source_captured_at_jst"] = "2026-11-08T08:30:00+09:00"
        self.assertEqual(build(stale, regional(), NOW)[1], 0)
        late_model = regional()
        late_model["retrieved_at_utc"] = "2026-11-08T00:11:00+00:00"
        self.assertEqual(build(wave(), late_model, NOW)[1], 0)
        self.assertEqual(build(wave(), None, NOW)[1], 0)

    def test_rejects_site_identity_and_venue_exclusion(self):
        wrong = wave()
        wrong["races"][0]["venue_code"] = "19"
        self.assertEqual(build(wrong, regional(), NOW)[1], 0)
        edo = wave()
        edo["races"][0].update(race_code="202611080302", venue_code="03", venue="江戸川")
        self.assertEqual(build(edo, regional(), NOW)[1], 0)

    def test_calibration_not_inferred_from_mild_weather(self):
        w = wave()
        w["races"][0]["weather"]["wave_cm"] = 1
        m = regional()
        m["venues"][20]["hourly"][0]["wind_mps"] = 2
        result, count = build(w, m, NOW)
        self.assertEqual(count, 1)
        self.assertEqual(result["records"][0]["status"], "research_baseline")
        self.assertEqual(result["records"][0]["signals"], [])

    def test_no_backdating_or_mismatched_previous_archive(self):
        with self.assertRaises(ValueError):
            build(wave(), regional(), datetime.fromisoformat("2026-11-09T00:00:00Z"))
        old, _ = build(wave(), regional(), NOW)
        old["event_date"] = "2026-11-07"
        with self.assertRaises(ValueError):
            build(wave(), regional(), NOW, old)


if __name__ == "__main__":
    unittest.main()
