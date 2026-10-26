"""Historical Mikuni 1R replay safety tests; synthetic measurements, not actual race data."""
import unittest
from datetime import datetime, timezone
from exhibition_bridge import inject

def fixture():
    race = {"closed_at": "2026-10-26 08:47:00", "preview": {}}
    row = {"race_code": "202610261001", "venue_code": "10", "race": 1,
           "source_status": "historical_research_only_not_frozen_forecast",
           "source_observed_jst": "2026-10-26T08:30:00+09:00",
           "boats": [{"lane": i, "course": i, "exhibition_st": .1,
                      "exhibition_time": 6.8, "tilt": 0} for i in range(1, 7)]}
    return race, row

class ReplayTests(unittest.TestCase):
    def test_six_boats_pre_cutoff(self):
        race, row = fixture()
        updated, source = inject(race, row, datetime(2026,10,25,23,40,tzinfo=timezone.utc), "10", 1)
        self.assertIsNotNone(source)
        self.assertEqual(len(updated["preview"]["racers"]), 6)
        self.assertEqual(race["preview"], {})
    def test_after_cutoff_no_mutation(self):
        race, row = fixture()
        updated, source = inject(race, row, datetime(2026,10,26,0,0,tzinfo=timezone.utc), "10", 1)
        self.assertIsNone(source)
        self.assertIs(updated, race)
    def test_missing_boat_rejected(self):
        race, row = fixture()
        row["boats"].pop()
        self.assertIsNone(inject(race, row, datetime(2026,10,25,23,40,tzinfo=timezone.utc), "10", 1)[1])
    def test_course_change(self):
        race, row = fixture()
        row["boats"][1]["course"], row["boats"][2]["course"] = 3, 2
        updated, source = inject(race, row, datetime(2026,10,25,23,40,tzinfo=timezone.utc), "10", 1)
        self.assertIsNotNone(source)
        self.assertEqual(updated["preview"]["racers"]["2"]["course_number"], 3)

if __name__ == "__main__":
    unittest.main()
