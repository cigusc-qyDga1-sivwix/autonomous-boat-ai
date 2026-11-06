"""Read-only forward audit must never backfill or count unmatched shadows."""
import unittest
from copy import deepcopy
from scripts.audit_attack_defence_shadow import analyze_ledger, valid_shadow, ticket_result, time_bucket

BET = [
    {"combination": "1-2-3", "virtual_yen": 20000},
    {"combination": "4-1-2", "virtual_yen": 12000},
    {"combination": "4-2-1", "virtual_yen": 10000},
    {"combination": "2-1-3", "virtual_yen": 8000},
]
ALT = [
    {"combination": "4-1-2", "virtual_yen": 20000},
    {"combination": "4-2-1", "virtual_yen": 12000},
    {"combination": "1-2-3", "virtual_yen": 10000},
    {"combination": "2-1-3", "virtual_yen": 8000},
]
SNAP = {
    "venue": "住之江", "race": 3, "phase": "exhibition",
    "cutoff_jst": "15:30", "frozen_at_utc": "2026-11-06T06:20:00+00:00",
    "bets": BET,
    "attack_defence_shadow": {
        "model_role": "shadow_validation",
        "status": "BOUNDED_HYPOTHESIS_UNCALIBRATED",
        "not_formal": True, "result_data_used": False,
        "no_additional_stake": True,
        "frozen_at_utc": "2026-11-06T06:20:00+00:00",
        "point_count_matched": True,
        "forecast_alternative_bets": ALT,
    },
}


class AuditTests(unittest.TestCase):
    def test_groups_are_by_actual_cutoff_time(self):
        self.assertEqual(time_bucket("11:59"), "before_12")
        self.assertEqual(time_bucket("12:00"), "12_to_15")
        self.assertEqual(time_bucket("15:00"), "15_to_18")
        self.assertEqual(time_bucket("18:00"), "after_18")

    def test_main_control_vs_shadow_ticket_comparison(self):
        p = ticket_result(BET, "4-1-2", 700)
        q = ticket_result(ALT, "4-1-2", 700)
        self.assertEqual(p["stage"], "hit")
        self.assertEqual(q["stage"], "hit")
        self.assertEqual(p["paid"], 84000)
        self.assertEqual(q["paid"], 140000)

    def test_no_outcomes_mean_no_data_to_backfill(self):
        ledger = {"event_date": "2026-11-06", "race_records": {
            "a": {"versions": [SNAP]}}}
        report = analyze_ledger(ledger)
        self.assertEqual(report["total"]["matched_races"], 0)
        self.assertEqual(report["excluded"].get("unverified"), 1)

    def test_no_forward_shadow_never_reconstructed_from_results(self):
        snapshot = deepcopy(SNAP)
        del snapshot["attack_defence_shadow"]
        valid, reason = valid_shadow(snapshot)
        self.assertFalse(valid)
        self.assertEqual(reason, "no_forward_shadow")

    def test_any_mismatched_model_is_excluded(self):
        for change in [
            {"point_count_matched": False},
            {"result_data_used": True},
            {"frozen_at_utc": "2026-11-06T06:00:00+00:00"},
            {"forecast_alternative_bets": ALT[:3]},
            {"forecast_alternative_bets": [ALT[0], ALT[0], ALT[2], ALT[3]]},
        ]:
            snapshot = deepcopy(SNAP)
            snapshot["attack_defence_shadow"].update(change)
            valid, _ = valid_shadow(snapshot)
            self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main()
