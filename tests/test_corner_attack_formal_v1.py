"""Guardrails for the provisional formal 3/4 corner and 4/5 follower rule."""
import unittest
from itertools import permutations

from scripts.corner_attack_formal_v1 import POLICY, POLICY_SHA256, rescore


def six_racers():
    racers = [{
        "lane": n, "course": n,
        "exhibition_st": .15,
        "exhibition_time": 6.75,
        "average_start_timing": .17,
        "average_start_timing_imputed": False,
    } for n in range(1, 7)]
    racers[2]["exhibition_st"] = .18
    racers[3]["exhibition_st"] = .12
    racers[3]["exhibition_time"] = 6.73
    racers[3]["average_start_timing"] = .16
    racers[4]["exhibition_st"] = .13
    racers[4]["exhibition_time"] = 6.75
    racers[4]["average_start_timing"] = .17
    return racers


def distribution():
    return [
        {"combination": "-".join(map(str, p)), "score": 1 / 120}
        for p in permutations(range(1, 7), 3)
    ]


def mass(ranked, prefix):
    return sum(r["score"] for r in ranked
               if r["combination"].split("-")[:len(prefix)] == [str(x) for x in prefix])


class CornerAttackFormalV1Tests(unittest.TestCase):
    def test_real_course_4_attack_is_bounded_and_normalized(self):
        before = distribution()
        after, audit = rescore(before, six_racers())
        self.assertTrue(audit["applied"])
        self.assertTrue(audit["follower_second_adjusted"])
        self.assertFalse(audit["calibrated"])
        self.assertFalse(audit["result_data_used"])
        self.assertFalse(audit["odds_used"])
        self.assertEqual(audit["policy_sha256"], POLICY_SHA256)
        self.assertEqual({r["combination"] for r in before},
                         {r["combination"] for r in after})
        self.assertAlmostEqual(sum(r["score"] for r in after), 1.0, places=10)
        self.assertGreater(mass(after, [4]), mass(before, [4]))
        self.assertLessEqual(
            mass(after, [4]) / mass(before, [4]),
            __import__("math").exp(POLICY["first_log_boost"]) + 1e-9)
        self.assertGreater(mass(after, [4, 5]) / mass(after, [4]),
                           mass(before, [4, 5]) / mass(before, [4]))
        # Conditional 3rd-place ordering remains the same for each (h, s).
        self.assertAlmostEqual(
            mass(after, [4, 5, 1]) / mass(after, [4, 5]),
            mass(before, [4, 5, 1]) / mass(before, [4, 5]))

    def test_course_not_lane_is_the_signal(self):
        racers = six_racers()
        racers[2]["lane"], racers[3]["lane"] = 4, 3
        ranked, audit = rescore(distribution(), racers)
        self.assertTrue(audit["applied"])
        self.assertEqual(audit["corner_lane"], 3)
        self.assertEqual(audit["guard_lane"], 4)
        self.assertGreater(mass(ranked, [3]), mass(distribution(), [3]))

    def test_no_corner_advantage_never_changes_distribution(self):
        racers = six_racers()
        racers[3]["exhibition_st"] = .19
        before = distribution()
        after, audit = rescore(before, racers)
        self.assertFalse(audit["applied"])
        self.assertEqual(before, after)

    def test_missing_or_imputed_data_fails_closed(self):
        for field, value in [
            ("exhibition_st", None),
            ("exhibition_time", 0),
            ("average_start_timing", float("nan")),
            ("average_start_timing_imputed", True),
        ]:
            with self.subTest(field=field):
                racers = six_racers()
                racers[2][field] = value
                before = distribution()
                after, audit = rescore(before, racers)
                self.assertFalse(audit["applied"])
                self.assertEqual(before, after)

    def test_fast_corner_without_follower_never_boosts_second(self):
        racers = six_racers()
        racers[4]["exhibition_st"] = .24
        before = distribution()
        after, audit = rescore(before, racers)
        self.assertTrue(audit["applied"])
        self.assertFalse(audit["follower_second_adjusted"])
        self.assertAlmostEqual(
            mass(after, [4, 5]) / mass(after, [4]),
            mass(before, [4, 5]) / mass(before, [4]))

    def test_broken_distribution_is_not_rescored(self):
        before = distribution()[:-1]
        after, audit = rescore(before, six_racers())
        self.assertFalse(audit["applied"])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
