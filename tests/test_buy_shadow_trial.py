"""Prospective BUY research shadow: immutability, timing and evidence tests."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from scripts.buy_shadow_trial import RULE, RULE_V1, START_DAY, classify, evaluate, freeze

NOW = datetime.fromisoformat("2026-11-17T01:00:00+00:00")
SHA = "a" * 64


def example_race(**changes):
    race = {
        "venue": "若松", "race": 8, "cutoff_jst": "10:30",
        "frozen_at_utc": "2026-11-17T00:58:00+00:00",
        "sha256": SHA, "formal_snapshot_sha256": SHA,
        "model_version": "test-learned-model", "classification": "WATCH",
        "phase": "exhibition", "ticket_status": "formal",
        "entry_exhibition_gate": {"final_eligible": True},
        "exhibition_input_check": {"verified_before_freeze": True, "six_boats_matched": 6},
        "racers": [{"lane": x} for x in range(1, 7)],
        "bets": [{"combination": "1-3-4"}, {"combination": "1-4-3"}],
        "head_weight_concentration": 0.69, "head_weight_gap": 0.45,
        "head_course_shares": [{"lane": 1, "relative_share": 0.69}],
    }
    race.update(changes)
    return race


def payload(*races):
    return {"event_date": "2026-11-17", "mode": "auto-live",
            "forecast_races": list(races), "official_results": {}}


class ProspectiveTrialTest(unittest.TestCase):
    def test_buy_watch_skip_are_exploratory(self):
        base = example_race()
        self.assertEqual(classify(base)[0], "BUY")
        self.assertEqual(classify(example_race(head_weight_concentration=0.55))[0], "WATCH")
        self.assertEqual(classify(example_race(head_weight_gap=0.05))[0], "SKIP")

    def test_ticket_count_never_downgrades_v02_buy(self):
        combinations = [
            {"combination": f"{first}-{second}-{third}"}
            for first in range(1, 7)
            for second in range(1, 7) if second != first
            for third in range(1, 7) if third not in (first, second)
        ]
        for point_count in (2, 10, 12, 18, 24, 30):
            with self.subTest(point_count=point_count):
                race = example_race(bets=combinations[:point_count])
                self.assertEqual(classify(race)[0], "BUY")
                if point_count > 10:
                    self.assertEqual(classify(race, rule=RULE_V1)[0], "WATCH")
        self.assertEqual(
            classify(example_race(bets=combinations[:30], head_weight_concentration=0.55))[0],
            "WATCH",
        )
        self.assertEqual(
            classify(example_race(bets=combinations[:30], head_weight_gap=0.05))[0],
            "SKIP",
        )

    def test_nov23_policy_uses_new_rule_without_rewriting_old_ledger(self):
        combinations = [
            {"combination": f"{first}-{second}-{third}"}
            for first in range(1, 7)
            for second in range(1, 7) if second != first
            for third in range(1, 7) if third not in (first, second)
        ][:24]
        old_source = payload(example_race(bets=combinations))
        old_ledger = freeze(old_source, NOW)
        self.assertEqual(old_ledger["rule"], RULE_V1)
        self.assertEqual(old_ledger["entries"][0]["decision"], "WATCH")
        self.assertEqual(evaluate(old_ledger, old_source)["rule"], RULE_V1)

        new_day = "2026-11-23"
        new_time = datetime.fromisoformat("2026-11-23T01:00:00+00:00")
        new_source = payload(example_race(
            bets=combinations, frozen_at_utc="2026-11-23T00:58:00+00:00"))
        new_source["event_date"] = new_day
        fresh = freeze(new_source, new_time)
        self.assertEqual(fresh["rule"], RULE)
        self.assertNotIn("buy_ticket_count_lte", fresh["thresholds"])
        self.assertEqual(fresh["entries"][0]["decision"], "BUY")
        self.assertEqual(fresh["entries"][0]["ticket_count"], 24)
        self.assertEqual(freeze(new_source, new_time + timedelta(minutes=1), fresh), fresh)
        self.assertEqual(evaluate(fresh, new_source)["rule"], RULE)
        self.assertEqual(evaluate(old_ledger, old_source)["rule"], RULE_V1)

    def test_forward_freeze_preserves_formal_and_is_idempotent(self):
        original = payload(example_race())
        unchanged = copy.deepcopy(original)
        first = freeze(original, NOW)
        self.assertEqual(first["entries"][0]["decision"], "BUY")
        self.assertEqual(first["entries"][0]["source_sha256"], SHA)
        self.assertEqual(len(first["entries"][0]["decision_sha256"]), 64)
        self.assertEqual(original, unchanged)
        second = freeze(original, NOW + timedelta(minutes=1), first)
        self.assertEqual(first, second)
        self.assertTrue(second["no_formal_ticket_or_classification_changes"])

    def test_closed_race_cannot_receive_new_decision(self):
        self.assertEqual(freeze(payload(example_race(cutoff_jst="10:01")), NOW)["entries"], [])
        self.assertEqual(freeze(payload(example_race()), NOW + timedelta(minutes=31))["entries"], [])

    def test_fail_closed_on_missing_exhibition_or_hash(self):
        variants = [
            {"phase": "baseline"}, {"ticket_status": "provisional"},
            {"classification": "SKIP"}, {"formal_snapshot_sha256": "b" * 64},
            {"exhibition_input_check": {"verified_before_freeze": False, "six_boats_matched": 6}},
            {"entry_exhibition_gate": {"final_eligible": False}},
            {"venue": "江戸川"},
            {"racers": [{"lane": 1}]},
            {"frozen_at_utc": "2026-11-17T01:01:00+00:00"},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(freeze(payload(example_race(**variant)), NOW)["entries"], [])

    def test_wrong_day_and_pretrial_date_refused(self):
        with self.assertRaises(ValueError):
            freeze(payload(example_race()), datetime.fromisoformat("2026-11-16T01:00:00+00:00"))
        with self.assertRaises(ValueError):
            freeze({"event_date": "2026-11-16", "mode": "auto-live", "forecast_races": []}, NOW)

    def test_official_only_and_no_reclassification(self):
        shadow = freeze(payload(example_race()), NOW)
        key = shadow["entries"][0]["race_id"]
        official = {"source": "boatrace_official_pay", "verified": True,
                    "snapshot_sha256": SHA, "finish": "1-3-4"}
        results = payload(example_race())
        results["official_results"] = {key: official}
        evaluated = evaluate(shadow, results)
        self.assertEqual(evaluated["cohorts"]["BUY"]["hits"], 1)
        self.assertEqual(evaluated["cohorts"]["BUY"]["verified"], 1)
        self.assertEqual(shadow["entries"][0]["decision"], "BUY")
        results["official_results"][key]["snapshot_sha256"] = "b" * 64
        self.assertEqual(evaluate(shadow, results)["cohorts"]["BUY"]["unresolved"], 1)
        results["official_results"][key] = {**official, "verified": False}
        self.assertEqual(evaluate(shadow, results)["cohorts"]["BUY"]["unresolved"], 1)
        results["official_results"][key] = {**official, "refunded_boats": [5]}
        self.assertEqual(evaluate(shadow, results)["cohorts"]["BUY"]["unresolved"], 1)

    def test_modified_decision_proof_rejected(self):
        shadow = freeze(payload(example_race()), NOW)
        shadow["entries"][0]["decision"] = "SKIP"
        with self.assertRaises(ValueError):
            evaluate(shadow, payload(example_race()))
        with self.assertRaises(ValueError):
            freeze(payload(example_race()), NOW, shadow)

    def test_wrong_trial_day_rejected(self):
        shadow = freeze(payload(example_race()), NOW)
        with self.assertRaises(ValueError):
            evaluate(shadow, {"event_date": "2026-11-18", "official_results": {}})


if __name__ == "__main__":
    unittest.main()
