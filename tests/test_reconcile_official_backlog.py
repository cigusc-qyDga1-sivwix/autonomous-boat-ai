"""Backlog settlement invariants: independent evidence, no forecast backfill."""
import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.reconcile_official_backlog import merge_verified, reconcile_day, run

DAY = "2026-10-22"
NOW = datetime(2026, 10, 24, 17, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
URL = "https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022"


def payout(combo="2-1-3", yen=2460):
    return {"finish": combo, "payout_per_100": yen}


def pay(combo="2-1-3", yen=2460):
    return {
        "date": DAY, "source_url": URL,
        "retrieved_at_utc": "2026-10-22T10:30:00+00:00",
        "results": {"18-1": payout(combo, yen)},
        "reviews": {}, "cancellations": {}, "pending_count": 0,
    }


def ledger():
    version = {
        "venue": "徳山", "race": 1, "phase": "baseline",
        "sha256": "a" * 64,
        "cutoff_iso_jst": "2026-10-22T10:00:00+09:00",
        "frozen_at_utc": "2026-10-22T00:00:00+00:00",
        "bets": [
            {"combination": "2-1-3", "virtual_yen": 20000},
            {"combination": "1-2-3", "virtual_yen": 10000},
            {"combination": "3-2-1", "virtual_yen": 10000},
            {"combination": "1-3-2", "virtual_yen": 10000},
        ],
    }
    return {
        "event_date": DAY,
        "race_records": {
            "18-1": {"venue": "徳山", "race": 1, "versions": [version]},
            "18-2": {"venue": "徳山", "race": 2, "versions": []},
        },
    }


class BacklogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.file = self.directory / (DAY + ".json")
        self.file.write_text(json.dumps(ledger()), encoding="utf-8")

    def read(self):
        return json.loads(self.file.read_text(encoding="utf-8"))

    def test_reconcile_past_date_without_recreating_forecasts(self):
        original = copy.deepcopy(self.read()["race_records"]["18-1"]["versions"])
        status = reconcile_day(self.directory, DAY, NOW, lambda _: pay())
        self.assertEqual(status["newly_verified"], 1)
        self.assertEqual(status["verified"], 1)
        doc = self.read()
        self.assertEqual(doc["race_records"]["18-1"]["versions"], original)
        self.assertEqual(doc["race_records"]["18-2"]["versions"], [])
        self.assertEqual(doc["race_records"]["18-1"]["official_pay"]["finish"], "2-1-3")
        second = reconcile_day(self.directory, DAY, NOW, lambda _: pay())
        self.assertEqual(second["newly_verified"], 0)
        self.assertEqual(second["verified"], 1)

    def test_conflict_is_quarantined_instead_of_overwriting(self):
        reconcile_day(self.directory, DAY, NOW, lambda _: pay())
        conflict = reconcile_day(self.directory, DAY, NOW, lambda _: pay("3-1-2", 9990))
        self.assertGreaterEqual(conflict["needs_review"], 1)
        self.assertEqual(conflict["verified"], 0)
        self.assertEqual(self.read()["race_records"]["18-1"]["official_pay"]["finish"], "2-1-3")

    def test_wrong_date_and_unavailable_source_never_create_results(self):
        wrong = pay()
        wrong["date"] = "2026-10-23"
        first = reconcile_day(self.directory, DAY, NOW, lambda _: wrong)
        self.assertEqual(first["state"], "SOURCE_UNAVAILABLE")
        self.assertNotIn("official_pay", self.read()["race_records"]["18-1"])
        reconcile_day(self.directory, DAY, NOW, lambda _: pay())
        retained = reconcile_day(self.directory, DAY, NOW,
                                 lambda _: (_ for _ in ()).throw(OSError("offline")))
        self.assertFalse(retained["fresh_fetch"])
        self.assertEqual(retained["verified"], 1)

    def test_only_frozen_records_and_missing_days_are_explicit(self):
        self.file.write_text(json.dumps({"event_date": DAY, "race_records": {
            "18-1": {"venue": "徳山", "race": 1, "versions": []}
        }}), encoding="utf-8")
        record = reconcile_day(self.directory, DAY, NOW, lambda _: pay())
        self.assertEqual(record["state"], "NO_PRE_RACE_FORECASTS")
        report = run(self.directory, NOW, 3, lambda _: pay())
        self.assertEqual(report["newly_verified"], 0)
        self.assertEqual(report["days"][0]["date"], DAY)
        self.assertEqual(report["days"][1]["state"], "NO_FROZEN_LEDGER")
        self.assertEqual(report["days"][2]["state"], "NO_FROZEN_LEDGER")

    def test_merge_does_not_silently_accept_official_correction(self):
        old = {**pay(), "status": "verified_by_server_fetch",
               "evidence_type": "official_boatrace_pay_snapshot",
               "conflicts": {}}
        merged = merge_verified(old, pay("6-2-1", 12340), DAY)
        self.assertNotIn("18-1", merged["results"])
        self.assertIn("18-1", merged["conflicts"])
        self.assertIn("18-1", merged["reviews"])


if __name__ == "__main__":
    unittest.main()
