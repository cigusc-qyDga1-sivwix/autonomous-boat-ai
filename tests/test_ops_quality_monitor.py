"""Offline regression checks for the read-only operational quality monitor."""
import copy
import unittest
from datetime import datetime, timezone

from scripts.ops_quality_monitor import evaluate, markdown

DAY = "2026-11-09"
NOW = datetime(2026, 11, 9, 0, 10, tzinfo=timezone.utc)  # 09:10 JST


def fixture():
    race = {"venue": "三国", "race": 1, "phase": "exhibition", "ticket_status": "formal",
            "sha256": "abc", "formal_snapshot_sha256": "abc",
            "entry_exhibition_gate": {"final_eligible": True},
            "frozen_at_utc": "2026-11-09T00:00:00+00:00", "cutoff_jst": "09:30"}
    live = {"event_date": DAY, "forecast_races": [race], "listed_races": 1,
            "final_exhibition_verified_races": 1,
            "official_results": {f"{DAY}|三国|1": {"verified": True,
                                  "source": "boatrace_official_pay", "snapshot_sha256": "abc"}}}
    sync = {"event_date": DAY, "forecast_races": 1, "status": "completed",
            "captured_at_utc": "2026-11-09T00:08:00+00:00"}
    exhibition = {"event_date": DAY, "complete_six_boat_research_races": 1}
    audit = {"event_date": DAY, "coverage": {"official_verified_forecasts": 1}}
    return [live, sync, exhibition, audit]


class MonitorTests(unittest.TestCase):
    def report(self, docs=None):
        return evaluate(*(docs or fixture()), now=NOW)

    def test_valid_canonical_data(self):
        r = self.report()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["metrics"]["formal_ticket_races"], 1)
        self.assertEqual(r["metrics"]["verified_official_results"], 1)
        self.assertFalse(r["prediction_model_modified"])
        self.assertIn("未確認", markdown(r))

    def test_stale_cron_is_warning_not_claimed_crash(self):
        data = fixture()
        data[1]["captured_at_utc"] = "2026-11-08T23:00:00+00:00"
        self.assertIn("FORECAST_STALE", [x["code"] for x in self.report(data)["findings"]])
        self.assertEqual(self.report(data)["status"], "warning")

    def test_formal_without_gate_is_critical(self):
        data = fixture()
        data[0]["forecast_races"][0]["entry_exhibition_gate"]["final_eligible"] = False
        self.assertIn("FORMAL_GATE_MISMATCH", [x["code"] for x in self.report(data)["findings"]])

    def test_post_cutoff_freeze_is_critical(self):
        data = fixture()
        data[0]["forecast_races"][0]["frozen_at_utc"] = "2026-11-09T00:31:00+00:00"
        self.assertIn("POST_CUTOFF_FREEZE", [x["code"] for x in self.report(data)["findings"]])

    def test_official_sha_conflict_is_critical(self):
        data = fixture()
        data[0]["official_results"][f"{DAY}|三国|1"]["snapshot_sha256"] = "wrong"
        self.assertIn("OFFICIAL_SHA_MISMATCH", [x["code"] for x in self.report(data)["findings"]])

    def test_unverified_official_cannot_count(self):
        data = fixture()
        data[0]["official_results"][f"{DAY}|三国|1"]["verified"] = False
        report = self.report(data)
        self.assertEqual(report["metrics"]["verified_official_results"], 0)
        self.assertIn("UNVERIFIED_OFFICIAL", [x["code"] for x in report["findings"]])

    def test_research_only_cannot_promote_formal(self):
        data = fixture()
        data[0]["forecast_races"][0]["ticket_status"] = "provisional"
        data[0]["forecast_races"][0]["phase"] = "baseline"
        data[0]["forecast_races"][0]["formal_snapshot_sha256"] = None
        data[2]["complete_six_boat_research_races"] = 99
        self.assertEqual(self.report(data)["metrics"]["formal_ticket_races"], 0)

    def test_missing_timestamp_is_not_valid(self):
        data = fixture()
        data[1]["captured_at_utc"] = "2026-11-09T00:08:00"
        self.assertEqual(self.report(data)["status"], "critical")

    def test_duplicate_race_detected(self):
        data = fixture()
        data[0]["forecast_races"].append(copy.deepcopy(data[0]["forecast_races"][0]))
        self.assertIn("DUPLICATE_RACE", [x["code"] for x in self.report(data)["findings"]])


if __name__ == "__main__":
    unittest.main()
