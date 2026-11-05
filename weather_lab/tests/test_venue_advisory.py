"""Independent guards: advice must never modify a forecast or invent tide."""
import unittest
from weather_lab.venue_advisory import VENUES, assess_venue


class VenueAdviceTests(unittest.TestCase):
    def test_24_venues_and_edogawa_out_of_forecast_scope(self):
        self.assertEqual(len(VENUES), 24)
        self.assertEqual(set(VENUES), {f"{i:02d}" for i in range(1, 25)})
        self.assertFalse(assess_venue("03", 6, 5, "fresh_snapshot")["prediction_scope"])

    def test_fresh_calm_and_missing_inputs_do_not_advance_picks(self):
        for code in VENUES:
            x = assess_venue(code, 0, 0, "fresh_snapshot")
            self.assertEqual(x["status"], "monitor")
            self.assertEqual(x["signals"], [])
            self.assertEqual(x["prediction_effect"], "none")
            self.assertIsNone(x["relative_wind_direction"])
            self.assertIsNone(x["tide_stage"])

    def test_stale_observation_cannot_generate_live_alerts(self):
        x = assess_venue("16", 12, 15, "stale_observation")
        self.assertEqual(x["status"], "unavailable")
        self.assertEqual(x["signals"], [])

    def test_wind_and_wave_signals_are_qualitative_only(self):
        x = assess_venue("09", 8, 10, "fresh_snapshot")
        self.assertEqual(x["status"], "attention")
        self.assertEqual(x["signals"], [
            "wind_ge_5mps", "wind_ge_8mps", "wave_ge_5cm", "wave_ge_10cm"])
        self.assertEqual(x["prediction_effect"], "none")
        self.assertFalse(x["tide_data_needed"])

    def test_tides_are_never_invented_or_assumed_for_gated_pools(self):
        self.assertTrue(assess_venue("16", 2, 2, "fresh_snapshot")["tide_data_needed"])
        self.assertTrue(assess_venue("17", 2, 2, "fresh_snapshot")["tide_data_needed"])
        self.assertFalse(assess_venue("08", 2, 2, "fresh_snapshot")["tide_data_needed"])
        self.assertFalse(assess_venue("19", 2, 2, "fresh_snapshot")["tide_data_needed"])
        for code in VENUES:
            x = assess_venue(code, 8, 10, "fresh_snapshot")
            self.assertIsNone(x["tide_current"])
            self.assertTrue(x["wind_direction_source_unmapped"])


if __name__ == "__main__":
    unittest.main()
