"""Research-only tests: venue-specific metrics never alter tickets."""
import unittest
from copy import deepcopy

from scripts.original_exhibition_venue_research import (
    VENUE_SPECS, digest, venue_features, LAP, HALF, TURN, STRAIGHT,
)

CAPTURED = "2026-11-17T02:52:00+00:00"
FROZEN = "2026-11-17T02:54:00+00:00"
CUTOFF = "2026-11-17T12:00:00+09:00"


def capture(venue="23", metrics=(LAP, TURN, STRAIGHT)):
    boats = [{"lane": i, "name": f"test{i}",
              **{m: (37+i/10 if m == LAP else
                     18+i/10 if m == HALF else
                     7+i/10 if m == TURN else
                     7.3+i/100) for m in metrics}}
             for i in range(1, 7)]
    return {
        "status": "SIX_BOAT_PARSED_RESEARCH_ONLY",
        "research_only": True, "formal_forecast_eligible": False,
        "captured_at_utc": CAPTURED,
        "date": "2026-11-17", "venue_code": venue,
        "race_number": 1,
        "source_url": f"https://race.boatcast.jp/txt/{venue}/bc_oriten_20261117_{venue}_01.txt",
        "metrics": list(metrics), "boats": boats,
        "measurement_sha256": digest(boats)
    }


def build(c):
    return venue_features(c, frozen_at_utc=FROZEN, cutoff_at_jst=CUTOFF)


class VenueOriginalResearchTests(unittest.TestCase):
    def test_all_24_profiles_and_excluded_edogawa(self):
        self.assertEqual(len(VENUE_SPECS), 24)
        self.assertEqual(VENUE_SPECS["03"]["expected_metrics"], ())
        self.assertEqual(build({"venue_code": "03"})["status"], "VENUE_EXCLUDED")

    def test_verified_karatsu_three_metrics(self):
        result = build(capture())
        self.assertEqual(set(result["features"]), {LAP, TURN, STRAIGHT})
        self.assertEqual(result["features"][TURN]["1"]["within_race_midrank"], 1)
        self.assertGreater(result["features"][TURN]["1"]["advantage_over_race_median_seconds"], 0)
        self.assertFalse(result["formal_model_eligible"])
        self.assertFalse(result["formal_tickets_changed"])

    def test_tokuyama_missing_straight_is_not_fabricated(self):
        x = build(capture("18", (LAP, TURN)))
        self.assertEqual(set(x["features"]), {LAP, TURN})
        self.assertNotIn(STRAIGHT, x["metric_status"])

    def test_kiryu_half_lap_stays_half(self):
        x = build(capture("01", (HALF, TURN, STRAIGHT)))
        self.assertIn(HALF, x["features"])
        self.assertNotIn(LAP, x["features"])

    def test_mikuni_boatcast_full_lap_stays_full(self):
        x = build(capture("10", (LAP, TURN, STRAIGHT)))
        self.assertIn(LAP, x["features"])
        self.assertNotIn(HALF, x["features"])

    def test_unoffered_metric_flagged_without_implicit_bad_score(self):
        x = build(capture("23", (LAP, TURN)))
        self.assertEqual(x["metric_status"][STRAIGHT], "NOT_OFFERED")
        self.assertNotIn(STRAIGHT, x["features"])

    def test_missing_one_value_discards_only_that_metric(self):
        c = capture()
        c["boats"][2][STRAIGHT] = None
        c["measurement_sha256"] = digest(c["boats"])
        x = build(c)
        self.assertEqual(x["metric_status"][STRAIGHT], "MISSING_OR_INVALID_SIX_BOAT")
        self.assertIn(TURN, x["features"])

    def test_tampering_rejected(self):
        c = capture()
        c["boats"][0][TURN] = 6.0
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            build(c)

    def test_late_capture_rejected(self):
        c = capture()
        c["captured_at_utc"] = "2026-11-17T02:55:00+00:00"
        with self.assertRaisesRegex(ValueError, "before eligible freeze"):
            build(c)

    def test_cannot_inject_other_venue_url(self):
        c = capture()
        c["source_url"] = c["source_url"].replace("txt/23/", "txt/18/")
        with self.assertRaisesRegex(ValueError, "unexpected source identity"):
            build(c)

    def test_cannot_masquerade_as_formal(self):
        c = capture()
        c["formal_forecast_eligible"] = True
        with self.assertRaisesRegex(ValueError, "must not masquerade"):
            build(c)

    def test_mixed_weekly_timing_not_combined(self):
        # Wakamatsu's adopted lap is a different selected circuit; no
        # subtraction or lap-time composition feature is introduced.
        x = build(capture("20"))
        self.assertEqual(set(x["features"]), {LAP, TURN, STRAIGHT})
        self.assertTrue(all("gap_to_fastest_seconds" in x["features"][m]["1"]
                            for m in (LAP, TURN, STRAIGHT)))
        self.assertTrue(all("lap_minus" not in str(x) for _ in range(1)))

    def test_source_invalid_cannot_create_features(self):
        c = capture()
        c["status"] = "SOURCE_UNAVAILABLE"
        with self.assertRaisesRegex(ValueError, "source not verified"):
            build(c)


if __name__ == "__main__":
    unittest.main()
