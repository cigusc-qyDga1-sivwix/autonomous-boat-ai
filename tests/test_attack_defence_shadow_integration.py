"""Actual forecast integration: shadow input stays pre-cutoff, formal main unchanged."""
from copy import deepcopy
from datetime import datetime
from unittest import TestCase

from scripts import autonomous_daily as A
from tests.test_four_factor_main import race

NOW = datetime.fromisoformat("2026-11-06T09:00:00+09:00")


def strong_outer():
    r = race("2026-11-06")
    r["racers"]["4"]["average_start_timing"] = .095
    r["preview"]["racers"]["4"]["exhibition_time"] = 6.62
    r["preview"]["racers"]["4"]["start_timing"] = .08
    return r


class AttackDefenceIntegrationTests(TestCase):
    def test_verified_exhibition_creates_only_parallel_trial(self):
        r = strong_outer()
        original = deepcopy(r)
        new = A.prediction(r, "住之江", 1, "exhibition", NOW, "fixture")
        self.assertEqual(new["model_version"], A.LINKED_MAIN_MODEL)
        self.assertEqual(r, original)
        self.assertIn("attack_defence_shadow", new)
        trial = new["attack_defence_shadow"]
        self.assertEqual(trial["status"], "BOUNDED_HYPOTHESIS_UNCALIBRATED")
        self.assertTrue(trial["not_formal"])
        self.assertFalse(trial["result_data_used"])
        self.assertTrue(trial["no_additional_stake"])
        self.assertEqual(trial["frozen_at_utc"], new["frozen_at_utc"])
        self.assertEqual(sum(b["virtual_yen"] for b in new["bets"]), 50000)
        self.assertEqual(sum(b["virtual_yen"] for b in trial["forecast_alternative_bets"]), 50000)
        self.assertTrue(4 <= len(new["bets"]) <= 24)

    def test_no_clear_attack_edge_leaves_trial_absent(self):
        new = A.prediction(race("2026-11-06"), "住之江", 1, "exhibition", NOW, "fixture")
        self.assertNotIn("attack_defence_shadow", new)

    def test_baseline_does_not_guess_late_exhibition(self):
        new = A.prediction(strong_outer(), "住之江", 1, "baseline", NOW, "fixture")
        self.assertNotIn("attack_defence_shadow", new)

    def test_result_payout_cannot_change_main_or_trial(self):
        r = strong_outer()
        left = A.prediction(r, "住之江", 1, "exhibition", NOW, "fixture")
        r["result"] = {"finish": "4-1-2", "payout": 9999999}
        right = A.prediction(r, "住之江", 1, "exhibition", NOW, "fixture")
        self.assertEqual(left["bets"], right["bets"])
        self.assertEqual(left.get("attack_defence_shadow"), right.get("attack_defence_shadow"))


if __name__ == "__main__":
    import unittest
    unittest.main()
