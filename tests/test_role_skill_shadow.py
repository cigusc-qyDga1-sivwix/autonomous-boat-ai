import unittest
from datetime import datetime, timezone
from scripts.autonomous_daily import promoted_v09
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

if __name__ == "__main__":
    unittest.main()
