"""Only source-frozen information may determine research SKIP/HOLD."""
import copy
import unittest

from scripts.uncertainty_gate_research import evaluate
from scripts.audit_unpredictable_20261114 import study


def snapshot():
    racers = []
    for lane in range(1, 7):
        racers.append({
            "lane": lane, "course": lane,
            "exhibition_st": .10 + .01 * lane,
            "exhibition_time": 6.75 + lane * .01,
            "original_exhibition": {"turn_time": 5.40 + lane * .02},
        })
    return {
        "venue": "児島", "race": 1, "phase": "exhibition",
        "frozen_at_utc": "2026-11-14T00:00:00+00:00",
        "cutoff_iso_jst": "2026-11-14T09:30:00+09:00",
        "cutoff_jst": "09:30",
        "weather_used": {"wind_speed": 2, "wave_height": 1},
        "racers": racers,
        "model_version": "four-factor-learned-v1-conditional-choice-trained",
        "bets": [
            {"combination": "1-2-3", "virtual_yen": 12500},
            {"combination": "1-3-2", "virtual_yen": 12500},
            {"combination": "2-1-3", "virtual_yen": 12500},
            {"combination": "3-1-2", "virtual_yen": 12500},
        ],
    }


class UncertaintyGateResearchTests(unittest.TestCase):
    def test_clean_source(self):
        x = snapshot()
        r = evaluate(x)
        self.assertEqual(r["status"], "KEEP_SHADOW")
        self.assertEqual(r["risk_points"], 0)
        self.assertFalse(r["formal_bets_changed"])

    def test_f_f_not_equated_to_lawful_fast_st(self):
        x = snapshot()
        x["racers"][1]["exhibition_st"] = -.01
        self.assertEqual(evaluate(x)["status"], "WATCH_SHADOW")
        x["racers"][2]["exhibition_st"] = -.07
        self.assertEqual(evaluate(x)["status"], "SKIP_SHADOW")
        self.assertEqual(evaluate(x)["risk_signals"] if False else
                         evaluate(x)["signals"]["exhibition_f_count"], 2)

    def test_entry_and_other_signal(self):
        x = snapshot()
        x["racers"][3]["course"], x["racers"][4]["course"] = 5, 4
        self.assertEqual(evaluate(x)["status"], "WATCH_SHADOW")
        x["weather_used"]["wind_speed"] = 5
        self.assertEqual(evaluate(x)["status"], "SKIP_SHADOW")

    def test_conflicting_exhibition_signals(self):
        x = snapshot()
        x["racers"][0]["exhibition_time"] = 6.90
        x["racers"][0]["original_exhibition"]["turn_time"] = 5.15
        self.assertEqual(evaluate(x)["status"], "WATCH_SHADOW")

    def test_outcome_payout_and_odds_leakage_prohibited(self):
        x = snapshot()
        first = evaluate(x)
        x["result"] = {"finish": "6-5-4", "decision": "まくり"}
        x["payout"] = {"yen_per_100": 999999}
        x["actual_st"] = {"1": .22}
        x["odds"] = {"6-5-4": 1000}
        self.assertEqual(evaluate(x), first)

    def test_fail_closed(self):
        x = snapshot()
        x["phase"] = "baseline"
        self.assertEqual(evaluate(x)["status"], "HOLD_NO_PRE_CUTOFF_EXHIBITION")
        x["phase"] = "exhibition"
        x["frozen_at_utc"] = "2026-11-14T00:29:00+00:00"
        self.assertEqual(evaluate(x)["status"], "HOLD_UNPROVEN_PRE_CUTOFF")
        x["frozen_at_utc"] = "2026-11-14T00:00:00+00:00"
        x["racers"][3]["exhibition_time"] = None
        self.assertEqual(evaluate(x)["status"], "HOLD_INCOMPLETE_EXHIBITION")

    def test_full_audit_no_historical_mutation(self):
        win = snapshot()
        loss = snapshot()
        loss["race"] = 2
        loss["racers"][3]["course"], loss["racers"][4]["course"] = 5, 4
        loss["weather_used"]["wind_speed"] = 5
        payout = lambda combo: {
            "verified": True, "source": "boatrace_official_pay",
            "finish": combo, "payout_per_100": 1500,
        }
        ledger = {"event_date": "2026-11-14", "race_records": {
            "16-1": {"venue": "児島", "race": 1, "cutoff_jst": "09:30",
                     "versions": [win], "official_pay": payout("1-2-3")},
            "16-2": {"venue": "児島", "race": 2, "cutoff_jst": "09:30",
                     "versions": [loss], "official_pay": payout("6-5-4")},
        }}
        original = copy.deepcopy(ledger)
        out = study(ledger)
        self.assertEqual(out["all_eligible"]["verified_races"], 2)
        self.assertEqual(out["all_eligible"]["hits"], 1)
        self.assertEqual(out["all_eligible"]["head_miss"], 1)
        self.assertEqual(out["by_predetermined_risk"]["KEEP_SHADOW"]["hits"], 1)
        self.assertEqual(out["by_predetermined_risk"]["SKIP_SHADOW"]["head_miss"], 1)
        self.assertEqual(ledger, original)
        ledger["race_records"]["16-2"]["official_review"] = "pending"
        out2 = study(ledger)
        self.assertEqual(out2["all_eligible"]["verified_races"], 1)
        self.assertEqual(out2["excluded_from_official_comparison"]["official_conflict_or_review"], 1)


if __name__ == "__main__":
    unittest.main()
