"""Regression tests for second-chance display-independent exhibition gate."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from scripts.exhibition_second_chance import eligible_new_previews

JST = ZoneInfo("Asia/Tokyo")
DAY = "2026-11-06"
CODE = "202611062306"


def row():
    return {
        "race_code": CODE,
        "preview_sha256": "fresh-sha",
        "cutoff_jst": "10:48",
        "source_observed_jst": "2026-11-06T10:40:28+09:00",
        "preview_captured_at_utc": "2026-11-06T01:42:38+00:00",
        "source_status": "historical_research_only_not_frozen_forecast",
        "boats": [{"course": i, "exhibition_st": 0.13,
                   "exhibition_time": 6.7} for i in range(1, 7)],
        "result": {"finish": "6-5-4"}, "payout": {"yen_per_100": 12345}
    }


def document(r):
    return {"event_date": DAY, "records": [r]}


class SecondChanceTests(unittest.TestCase):
    def test_new_preview_before_three_minute_safety_deadline_can_trigger_rebuild(self):
        at = datetime(2026, 11, 6, 10, 42, 40, tzinfo=JST)
        older = row()
        older["preview_sha256"] = "older-sha"
        older["boats"][0]["exhibition_time"] = 6.69
        self.assertEqual(eligible_new_previews(document(older), document(row()), at), [CODE])
        timestamp_only = {**row(), "preview_sha256": "new-time-only"}
        self.assertEqual(eligible_new_previews(document(row()), document(timestamp_only), at), [])
        self.assertEqual(eligible_new_previews(document(row()), document(row()), at), [])

    def test_previous_frozen_data_cannot_be_rewritten_after_deadline(self):
        at = datetime(2026, 11, 6, 10, 45, 1, tzinfo=JST)
        self.assertEqual(eligible_new_previews({"event_date":DAY},
                                                 document(row()), at), [])
        too_late = {**row(), "preview_captured_at_utc": "2026-11-06T01:45:20+00:00"}
        at_earlier = datetime(2026, 11, 6, 10, 44, 0, tzinfo=JST)
        self.assertEqual(eligible_new_previews({}, document(too_late), at_earlier), [])

    def test_reject_stale_source_wrong_day_future_capture_and_incomplete_boats(self):
        at = datetime(2026, 11, 6, 10, 42, 40, tzinfo=JST)
        variants = [
            {**row(), "source_observed_jst":"2026-11-06T10:46:00+09:00"},
            {**row(), "preview_captured_at_utc":"2026-11-06T02:00:00+00:00"},
            {**row(), "boats":row()["boats"][:5]},
            {**row(), "boats":[{**b, "course":1} for b in row()["boats"]]},
            {**row(), "source_status":"imported_after_results"},
            {**row(), "source_observed_jst":"2026-11-05T10:40:00+09:00",
             "preview_captured_at_utc":"2026-11-05T01:42:38+00:00"}
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(eligible_new_previews({}, document(variant), at), [])

    def test_only_date_scoped_changed_input_not_result_or_payout(self):
        at = datetime(2026, 11, 6, 10, 42, 40, tzinfo=JST)
        old = document(row())
        outcome_changed = document({**row(), "result":{"finish":"1-2-3"},
                                    "payout":{"yen_per_100":200}})
        self.assertEqual(eligible_new_previews(old, outcome_changed, at), [])
        self.assertEqual(eligible_new_previews(old,
                         {"event_date":"2026-11-05","records":[row()]},at), [])


if __name__ == "__main__":
    unittest.main()
