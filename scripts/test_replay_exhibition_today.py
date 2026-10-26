"""Deterministic no-network tests for result-blind retrospective replay."""
import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts.autonomous_daily import MAIN_WAKE_MODEL
from scripts.replay_exhibition_today import (
    BUDGET, generate_candidates, racer_input, report,
    sanitized_measurements, score_candidates,
)

DAY = "2026-10-26"
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def bets(first, second):
    return [
        {"combination": first, "virtual_yen": 30_000},
        {"combination": second, "virtual_yen": 20_000},
    ]


def baseline():
    return {
        "phase": "baseline",
        "sha256": "a" * 64,
        "model_version": MAIN_WAKE_MODEL,
        "bets": bets("1-2-3", "1-3-2"),
        "racers": [
            {
                "lane": i, "name": f"TEST {i}",
                "national_win_rate": 5.0, "average_start_timing_source_value": .15,
                "motor_top_2_percent": 30.0,
            }
            for i in range(1, 7)
        ],
    }


def exhibition():
    return {
        "race_code": "202610260908",
        "venue_code": "09", "race": 8, "source_status":
        "historical_research_only_not_frozen_forecast",
        "source_observed_jst": "2026-10-26T13:44:00+09:00",
        "first_seen_at_utc": "2026-10-26T08:30:00+00:00",
        "boats": [
            {"lane": i, "course": i, "exhibition_st": .01*i,
             "exhibition_time": 6.80+i/100, "tilt": 0,
             "original_exhibition": []}
            for i in range(1, 7)
        ],
        "weather": {"wind_mps": 2.0},
        # These must NEVER reach prediction(), even through dict aliases.
        "result": {"finish": "4-5-2", "decision": "まくり"},
        "payout": {"payout_per_100": 12560},
    }


def inputs():
    return (
        {"event_date": DAY, "race_records": {
            "9-8": {"venue": "津", "venue_code": "9",
                    "race": 8, "cutoff_jst": "13:55",
                    "versions": [baseline()]},
        }},
        {"event_date": DAY, "records": [exhibition()]},
        {"date": DAY, "results": {"9-8": {
            "finish": "4-5-2", "payout_per_100": 1200,
        }}},
    )


class ReplayTests(unittest.TestCase):
    def test_allowlist_does_not_include_result_payout(self):
        cleaned = sanitized_measurements(exhibition())
        self.assertNotIn("result", cleaned)
        self.assertNotIn("payout", cleaned)
        self.assertEqual(len(cleaned["boats"]), 6)

    def test_original_baseline_fields_only(self):
        race = racer_input(baseline(), DAY, "13:55")
        self.assertEqual(race["racers"]["1"]["flying_count"], 0)
        self.assertNotIn("result", race)
        self.assertEqual(race["closed_at"], "2026-10-26 13:55:00")

    def test_result_separation_and_no_ledger_mutation(self):
        ledger, research, pay = inputs()
        original = copy.deepcopy(ledger)
        def pretend_prediction(race, venue, n, phase, when, source):
            self.assertEqual(venue, "津")
            self.assertEqual(phase, "exhibition")
            self.assertNotIn("result", race)
            self.assertNotIn("payout", race)
            self.assertIsNone(race["_exhibition_origin"])
            self.assertEqual(when.hour, 13)
            return {
                "model_version": MAIN_WAKE_MODEL,
                "bets": bets("4-5-2", "2-1-3"),
            }
        with patch("scripts.replay_exhibition_today.prediction",
                   side_effect=pretend_prediction) as mocked:
            generated, skipped, existing = generate_candidates(
                DAY, ledger, research, NOW
            )
            self.assertEqual(mocked.call_count, 1)
        self.assertEqual(existing, 0)
        self.assertFalse(skipped)
        self.assertEqual(ledger, original)
        self.assertNotIn("official_finish", generated[0])
        self.assertEqual(generated[0]["bets_replayed"][0]["combination"], "4-5-2")
        scored = score_candidates(generated, pay, DAY)
        self.assertTrue(scored["verified"][0]["comparison"]["retrospective_replay"]["hit"])
        self.assertFalse(scored["verified"][0]["comparison"]["frozen_baseline"]["hit"])
        self.assertEqual(scored["verified"][0]["comparison"]["retrospective_replay"]
                         ["virtual_payout_yen"], 360_000)

    def test_refuse_unknown_results_and_eligible_formal(self):
        ledger, research, pay = inputs()
        ledger["race_records"]["9-8"]["versions"].append(
            {"phase": "exhibition"}
        )
        generated, _, existing = generate_candidates(DAY, ledger, research, NOW)
        self.assertEqual(existing, 1)
        self.assertEqual(generated, [])
        ledger["race_records"]["9-8"]["versions"].pop()
        with patch("scripts.replay_exhibition_today.prediction",
                   return_value={"model_version": MAIN_WAKE_MODEL,
                                 "bets": bets("4-5-2", "2-1-3")}):
            generated, _, _ = generate_candidates(DAY, ledger, research, NOW)
        pay["reviews"] = {"9-8": {"reason": "conflicting official result"}}
        self.assertEqual(score_candidates(generated, pay, DAY)["verified"], [])

    def test_date_mismatch_fails_closed(self):
        ledger, research, pay = inputs()
        research["event_date"] = "2026-10-25"
        with self.assertRaises(ValueError):
            generate_candidates(DAY, ledger, research, NOW)
        with self.assertRaises(ValueError):
            score_candidates([], {"date": "2026-10-25"}, DAY)

    def test_cannot_replay_before_cutoff(self):
        ledger, research, _ = inputs()
        early = datetime(2026, 10, 26, 13, 50, tzinfo=ZoneInfo("Asia/Tokyo"))
        with patch("scripts.replay_exhibition_today.prediction") as mock:
            items, skips, _ = generate_candidates(DAY, ledger, research, early)
        self.assertEqual(items, [])
        self.assertEqual(skips["not_yet_finished"], 1)
        mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
