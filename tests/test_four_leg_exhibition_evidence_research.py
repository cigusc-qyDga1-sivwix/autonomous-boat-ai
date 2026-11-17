"""Four leg evidence audit: no fabricated acceleration or production tickets."""
import unittest
from copy import deepcopy

from scripts.four_leg_exhibition_evidence_research import assess, SCHEMA
from scripts.original_exhibition_venue_research import digest, VENUE_SPECS


def original(code="23", metrics=("lap_time", "turn_time", "straight_time")):
    boats = [
        {"lane": lane, "name": f"選手{lane}",
         **{k: (37 + lane / 10 if k == "lap_time"
                else 18 + lane / 10 if k == "half_lap_time"
                else 7.5 + lane / 10 if k == "turn_time"
                else 7.6 + lane / 100)
            for k in metrics}}
        for lane in range(1, 7)
    ]
    return {
        "schema": "boatlabs.boatcast_oriten_smoke.v1",
        "date": "2026-11-18", "venue_code": code, "race_number": 2,
        "status": "SIX_BOAT_PARSED_RESEARCH_ONLY",
        "source_url": f"https://race.boatcast.jp/txt/{code}/bc_oriten_20261118_{code}_02.txt",
        "captured_at_utc": "2026-11-18T02:53:00+00:00",
        "source_body_sha256": "a" * 64,
        "metrics": list(metrics), "boats": boats,
        "measurement_sha256": digest(boats),
        "research_only": True, "formal_forecast_eligible": False,
    }


def snapshot(venue="唐津"):
    return {
        "phase": "exhibition",
        "venue": venue, "race": 2,
        "frozen_at_utc": "2026-11-18T02:54:00+00:00",
        "cutoff_iso_jst": "2026-11-18T12:00:00+09:00",
        "exhibition_origin": {"captured_before_cutoff": True},
        "racers": [
            {"lane": i, "course": i, "name": f"選手{i}",
             "exhibition_time": 6.71 + i * .01,
             "exhibition_st": .1 + i * .01}
            for i in range(1, 7)
        ],
        "bets": [{"combination": "1-2-3", "virtual_yen": 50000}],
    }


class FourLegExhibitionEvidenceTests(unittest.TestCase):
    def test_full_three_metrics_separate_four_categories_without_scores(self):
        race = snapshot()
        frozen = deepcopy(race)
        out = assess(race, original())
        self.assertEqual(out["schema"], SCHEMA)
        self.assertEqual(out["status"], "SIX_BOAT_EVIDENCE_RESEARCH_ONLY")
        self.assertEqual(len(out["boats"]), 6)
        self.assertTrue(out["research_only"])
        self.assertFalse(out["formal_tickets_changed"])
        self.assertEqual(race, frozen)
        for b in out["boats"]:
            self.assertEqual(set(b) - {"lane", "course"},
                             {"伸び足", "まわり足", "行き足", "出足"})
            self.assertIsNone(b["行き足"]["numeric_score"])
            self.assertIsNone(b["出足"]["numeric_score"])
            self.assertEqual(b["まわり足"]["status"], "MEASURED_TURN_INTERVAL_PROXY")
            self.assertEqual(b["伸び足"]["status"], "MEASURED_TIMING_PROXY")
            self.assertIsNotNone(b["出足"]["post_turn_straight_interval_seconds"])
            self.assertIsNotNone(b["まわり足"]["whole_lap_relative"])
        self.assertTrue(out["no_results_odds_or_payouts_used"])

    def test_suminoe_has_no_imaginary_independent_straight(self):
        out = assess(snapshot("住之江"), original("12", ("lap_time", "turn_time")))
        for b in out["boats"]:
            self.assertIsNone(b["伸び足"]["original_straight_relative"])
            self.assertIsNone(b["出足"]["post_turn_straight_interval_seconds"])
            self.assertIsNotNone(b["伸び足"]["normal_exhibition_relative"])
        self.assertEqual(out["original_metric_status"]["turn_time"], "SIX_BOAT_COMPLETE")

    def test_kiryu_half_lap_is_not_full_lap(self):
        out = assess(snapshot("桐生"), original("01", ("half_lap_time", "turn_time", "straight_time")))
        for b in out["boats"]:
            self.assertIsNone(b["まわり足"]["whole_lap_relative"])
            self.assertIsNotNone(b["まわり足"]["half_lap_relative"])

    def test_actual_course_kept_distinct_from_lane(self):
        race = snapshot()
        race["racers"][2]["course"], race["racers"][3]["course"] = 4, 3
        out = assess(race, original())
        self.assertEqual(out["boats"][2]["course"], 4)
        self.assertEqual(out["boats"][3]["course"], 3)

    def test_same_six_boats_and_cutoff_required(self):
        cases = []
        x = snapshot()
        x["phase"] = "baseline"
        cases.append((x, original()))
        x = snapshot()
        x["exhibition_origin"]["captured_before_cutoff"] = False
        cases.append((x, original()))
        x = snapshot()
        x["racers"][0]["name"] = "違う選手"
        cases.append((x, original()))
        x = snapshot()
        x["racers"][3]["exhibition_time"] = None
        cases.append((x, original()))
        x = snapshot()
        x["racers"][4]["course"] = 4
        cases.append((x, original()))
        x = snapshot()
        c = original()
        c["captured_at_utc"] = "2026-11-18T02:55:00+00:00"
        cases.append((x, c))
        x = snapshot()
        c = original()
        c["boats"][0]["turn_time"] += .2
        cases.append((x, c))
        for x, c in cases:
            with self.subTest(case=len(str(x)) + len(str(c))):
                with self.assertRaises(ValueError):
                    assess(x, c)


if __name__ == "__main__":
    unittest.main()
