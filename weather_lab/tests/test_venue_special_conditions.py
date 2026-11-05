"""Formal safeguards for venue-specific weather triggers."""
import unittest
from weather_lab.venue_special_conditions import evaluate
from weather_lab.venue_advisory import assess_venue


class VenueSpecificRulesTests(unittest.TestCase):
    def test_official_numeric_thresholds_tsu_and_amagasaki(self):
        self.assertEqual(evaluate("09", 4.99, 0, "fresh_snapshot")["conditions"], [])
        self.assertEqual(evaluate("09", 5, 0, "fresh_snapshot")["conditions"][0]["id"], "tsu_wind_5m")
        self.assertEqual(evaluate("13", 6, 0, "fresh_snapshot")["conditions"][0]["id"], "amagasaki_wind_6m")

    def test_nothing_active_on_stale_or_missing(self):
        for code in ["09", "10", "13", "14", "16", "17"]:
            self.assertEqual(evaluate(code, 12, 12, "stale_observation")["conditions"], [])
            self.assertEqual(evaluate(code, None, None, "incomplete_values")["conditions"], [])

    def test_mikuni_tailwind_needs_explicit_verified_wind_relative_to_course(self):
        raw=evaluate("10", 7, 2, "fresh_snapshot", relative_wind="tailwind")
        self.assertEqual(raw["conditions"], [])
        verified=evaluate("10", 7, 2, "fresh_snapshot", relative_wind="tailwind",
                          relative_wind_verified=True)
        self.assertEqual(verified["conditions"][0]["id"], "mikuni_strong_tailwind")
        self.assertEqual(evaluate("10", 7, 2, "fresh_snapshot", relative_wind="headwind",
                                  relative_wind_verified=True)["conditions"], [])

    def test_miyajima_tide_and_kojima_compound_require_verified_site_data(self):
        self.assertEqual(evaluate("17", 2, 2, "fresh_snapshot", tide_stage="high")["conditions"], [])
        high=evaluate("17", 2, 2, "fresh_snapshot", tide_stage="high", tide_verified=True)
        self.assertEqual(high["conditions"][0]["id"], "miyajima_high_tide")
        kojima=evaluate("16", 5, 1, "fresh_snapshot", tide_stage="high", tide_verified=True,
                        relative_wind="tailwind", relative_wind_verified=True)
        self.assertEqual(kojima["conditions"][0]["id"], "kojima_high_tide_tailwind")
        no_bearing=evaluate("16", 5, 1, "fresh_snapshot", tide_stage="high", tide_verified=True,
                            relative_wind="tailwind")
        self.assertEqual(no_bearing["conditions"], [])

    def test_controlled_tokoname_never_uses_nearby_tide_directly(self):
        r=evaluate("08", 5, 6, "fresh_snapshot", tide_stage="high", tide_verified=True)
        self.assertEqual(r["conditions"], [])
        self.assertEqual(r["status"], "pending")

    def test_all_venue_rules_remain_supplemental_and_no_ticket_changes(self):
        for code in range(1,25):
            for wind in [1,5,8,12]:
                r=assess_venue(str(code),wind,5,"fresh_snapshot")
                self.assertFalse(r["venue_special_conditions"]["formal_ticket_modified"])
                self.assertTrue(r["venue_special_conditions"]["supplementary_only"])
                self.assertEqual(r["prediction_effect"], "none")


if __name__ == "__main__":
    unittest.main()
