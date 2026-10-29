import unittest
from datetime import datetime, timezone
from scripts.autonomous_daily import promoted_v09, integrate_official
from scripts.venue_profiles import get_profile

class RoleSkillShadowIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.racers = [{
            "lane": i, "course": i, "national_win_rate": 5.4 + .2*i,
            "average_start_timing": .13 + .008*i,
            "motor_top_2_percent": 30.0 + i,
            "exhibition_st": .12 + .01*i, "exhibition_time": 6.75 + .02*i,
            "racer_context": {"values": {
                "national_top3": 48+i*3,
                "frame_start_order": 7-i,
                "frame_st": .17,
                "local_win": 5.0,
                "frame_win": 5.0,
                "motor_top3": 45.0}}
        } for i in range(1, 7)]
    def test_opt_in_shadow_never_replaces_formal(self):
        args = ("唐津", "exhibition", self.racers, get_profile("23"),
                {"wind_speed": 2, "wave_height": 1}, "2026-10-31T04:00:00+00:00")
        kwargs = dict(four_factor=True, venue_tactics=True)
        base = promoted_v09(*args, **kwargs)
        shadow = promoted_v09(*args, role_skill_trial=True, **kwargs)
        self.assertEqual(base["bets"], shadow["bets"])
        self.assertEqual(base["model_version"], shadow["model_version"])
        self.assertNotIn("role_skill_shadow", base)
        s = shadow["role_skill_shadow"]
        self.assertEqual(s["status"], "ready")
        self.assertEqual(s["model_role"], "shadow_validation")
        self.assertEqual(sum(b["virtual_yen"] for b in s["bets"]), 50000)
        self.assertEqual(len(s["bets"]), len(base["bets"]))
        self.assertEqual(s["frozen_at_utc"], args[-1])

    def test_verified_results_compare_shadow_separately(self):
        import copy
        args = ("唐津", "exhibition", self.racers, get_profile("23"),
                {"wind_speed": 2, "wave_height": 1}, "2026-10-31T04:00:00+00:00")
        model = promoted_v09(*args, four_factor=True, venue_tactics=True,
                             role_skill_trial=True)
        primary = copy.deepcopy(model["bets"])
        trial = copy.deepcopy(model["role_skill_shadow"])
        snap = {"bets": primary, "role_skill_shadow": trial,
                "sha256": "a"*64, "frozen_at_utc": args[-1],
                "cutoff_iso_jst": "2026-10-31T14:00:00+09:00",
                "phase": "exhibition"}
        ledger = {"event_date": "2026-10-31",
                  "race_records": {"case1": {"venue": "唐津", "race": 1,
                                            "versions": [snap]}}}
        view = {"event_date": "2026-10-31"}
        combo = trial["bets"][0]["combination"]
        pay = {"date": "2026-10-31", "results": {"case1": {
                "finish": combo, "payout_per_100": 500}},
                "source_url": "https://www.boatrace.jp/owpc/pc/race/pay?hd=20261031",
                "retrieved_at_utc": "2026-10-31T10:00:00+00:00"}
        after = integrate_official(ledger, view, pay,
                                   datetime.fromisoformat("2026-10-31T10:00:00+00:00"))
        self.assertEqual(after["role_skill_backtest"]["races"], 1)
        self.assertEqual(after["role_skill_backtest"]["shadow_hits"], 1)
        record = after["official_results"]["2026-10-31|唐津|1"]
        self.assertEqual(record["role_skill_comparison"]["shadow_hit"], True)
        self.assertEqual(record["role_skill_comparison"]["same_stake_distribution"], True)
        self.assertEqual(record["hit"], combo in {b["combination"] for b in primary})
        self.assertEqual(snap["bets"], primary, "formal snapshot stays frozen")
        # A stale shadow must be ignored rather than retrospectively matched.
        invalid_ledger = copy.deepcopy(ledger)
        invalid_ledger["race_records"]["case1"]["versions"][0]["role_skill_shadow"]["frozen_at_utc"] = "2026-10-30T00:00:00Z"
        invalid_view = {"event_date": "2026-10-31"}
        result = integrate_official(invalid_ledger, invalid_view, pay,
                                    datetime.fromisoformat("2026-10-31T10:00:00+00:00"))
        self.assertNotIn("role_skill_backtest", result)

if __name__ == "__main__":
    unittest.main()
