"""Forward-only six-boat attack/defence shadow safety and scenario tests."""
from datetime import datetime, timedelta, timezone
from itertools import permutations
import math
import unittest

from scripts.attack_defense_shadow import rescore, VERSION

NOW = "2026-11-06T09:00:00+00:00"
CUTOFF = "2026-11-06T09:15:00+00:00"


def racers(*, actual_entry=False, threat=True):
    # Real entry can be different from boat numbers. Lane 1 is course 2 and
    # lane 2 is course 1 in this test to catch wrong lane/course indexing.
    rows = []
    for lane in range(1, 7):
        course = {1: 2, 2: 1}.get(lane, lane) if actual_entry else lane
        avg = .16
        expo = 6.85
        st = .16
        if threat and course == 4:
            avg, expo, st = .105, 6.72, .09
        rows.append({"lane": lane, "course": course,
                     "average_start_timing": avg,
                     "average_start_timing_imputed": False,
                     "exhibition_time": expo, "exhibition_st": st})
    return rows


def outcomes():
    n = 120
    return [{"combination": "-".join(map(str, p)), "relative_score": 1.0/n}
            for p in permutations(range(1, 7), 3)]


class AttackDefenceShadowTest(unittest.TestCase):
    def trial(self, rs=None, os=None, yes=True, time=NOW, cutoff=CUTOFF):
        return rescore(os if os is not None else outcomes(),
                       rs if rs is not None else racers(),
                       "住之江", time, cutoff, exhibition_verified=yes)

    def test_120_outcomes_and_bounded_input(self):
        value = self.trial()
        self.assertEqual(value["version"], VERSION)
        self.assertFalse(value["not_formal"] is False)
        self.assertFalse(value["result_data_used"])
        self.assertFalse(value["calibrated"])
        self.assertTrue(value["no_additional_stake"])
        self.assertEqual(len(value["outcomes"]), 120)
        self.assertAlmostEqual(sum(r["relative_score"] for r in value["outcomes"]), 1, places=12)
        self.assertLess(value["head_marginal_trial"]["1"], value["head_marginal_prior"]["1"])
        self.assertGreater(value["head_marginal_trial"]["4"], value["head_marginal_prior"]["4"])
        self.assertEqual(value["threats"]["4"]["course"], 4)
        self.assertIn("outer_attack_overruns_inside_counter", value["conditional_scenarios"])

    def test_actual_courses_drive_defender_identity(self):
        value = self.trial(rs=racers(actual_entry=True))
        self.assertEqual(value["inside_lane"], 2)
        self.assertEqual(value["actual_entry"]["1"], 2)
        self.assertLess(value["head_marginal_trial"]["2"], value["head_marginal_prior"]["2"])
        self.assertNotEqual(value["head_marginal_trial"]["1"], value["head_marginal_prior"]["1"])

    def test_no_evidence_no_adjustment(self):
        self.assertIsNone(self.trial(rs=racers(threat=False)))
        self.assertIsNone(self.trial(yes=False))

    def test_flying_exhibition_not_fast_evidence(self):
        rs = racers(threat=False)
        rs[3]["exhibition_st"] = -.10
        self.assertIsNone(self.trial(rs=rs))

    def test_imputed_zero_average_st_not_attack_advantage(self):
        rs = racers(threat=False)
        rs[3]["average_start_timing"] = 0.
        rs[3]["average_start_timing_imputed"] = True
        self.assertIsNone(self.trial(rs=rs))

    def test_missing_racer_or_duplicate_course_fail_closed(self):
        with self.assertRaises(ValueError):
            self.trial(rs=racers()[:5])
        rs = racers()
        rs[4]["course"] = 4
        with self.assertRaises(ValueError):
            self.trial(rs=rs)

    def test_no_postrace_leakage(self):
        rs = racers()
        rs[2]["finish"] = "1-2-3"
        with self.assertRaises(ValueError):
            self.trial(rs=rs)
        os = outcomes()
        os[0]["payout"] = 55000
        with self.assertRaises(ValueError):
            self.trial(os=os)

    def test_frozen_before_cutoff_only(self):
        with self.assertRaises(ValueError):
            self.trial(time=CUTOFF)
        with self.assertRaises(ValueError):
            self.trial(time="2026-11-06T10:00:00+00:00")
        with self.assertRaises(ValueError):
            self.trial(time="2026-11-06T09:00:00")

    def test_invalid_canonical_ranking(self):
        os = outcomes()
        os[1]["relative_score"] = float("nan")
        with self.assertRaises(ValueError):
            self.trial(os=os)
        os = outcomes()
        os[1]["combination"] = os[0]["combination"]
        with self.assertRaises(ValueError):
            self.trial(os=os)

    def test_venue_is_group_not_retrospective_loss_correction(self):
        a = self.trial()
        b = rescore(outcomes(), racers(), "丸亀", NOW, CUTOFF,
                    exhibition_verified=True)
        self.assertNotEqual(a["venue"], b["venue"])
        self.assertEqual(a["outcomes"], b["outcomes"])

    def test_stake_is_not_allocated_by_this_module(self):
        value = self.trial()
        self.assertNotIn("bets", value)
        self.assertNotIn("payout", value)
        self.assertNotIn("official_results", value)


if __name__ == "__main__":
    unittest.main()
