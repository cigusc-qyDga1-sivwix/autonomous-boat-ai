"""Safety and interpretation tests for independent inside-survival hypotheses."""
import copy
import unittest
from itertools import permutations

from scripts.inside_survival_research import evaluate


def fixture():
    racers = []
    for lane in range(1, 7):
        racers.append({
            "lane": lane, "course": lane,
            "average_start_timing": .17,
            "exhibition_st": .12, "exhibition_time": 6.85,
            "original_exhibition": {"turn_time": 5.60},
        })
    racers[0].update(average_start_timing=.20, exhibition_st=.15,
                     exhibition_time=6.80,
                     original_exhibition={"turn_time": 5.45})
    racers[3].update(average_start_timing=.13, exhibition_st=.08,
                     exhibition_time=6.73,
                     original_exhibition={"turn_time": 5.28})
    combos = ["-".join(map(str, p)) for p in permutations(range(1, 7), 3)]
    ranked = [{"combination": c, "score": 1 / len(combos)} for c in combos]
    bets = [{"combination": c, "virtual_yen": 12500} for c in combos[:4]]
    snapshot = {
        "phase": "exhibition", "venue": "津", "racers": racers,
        "frozen_at_utc": "2026-11-14T01:00:00+00:00",
        "cutoff_iso_jst": "2026-11-14T10:30:00+09:00",
    }
    return snapshot, ranked, bets


class InsideSurvivalResearchTest(unittest.TestCase):
    def test_pre_cutoff_partition_and_formal_immutability(self):
        source, ranked, bets = fixture()
        before = copy.deepcopy((source, ranked, bets))
        out = evaluate(source, ranked, bets)
        self.assertEqual(out["status"], "ATTACK_PATHS_PRESENT")
        self.assertEqual(out["model_role"], "research_shadow")
        self.assertFalse(out["formal_tickets_changed"])
        self.assertFalse(out["result_data_used"])
        self.assertTrue(out["threats"])
        self.assertEqual(out["threats"][0]["challenger_course"], 4)
        self.assertEqual(len(bets), out["formal_ticket_coverage"]["original_ticket_count"])
        self.assertAlmostEqual(sum(out["scenario_relative_mass_unCALIBRATED"].values()), 1, places=5)
        self.assertEqual((source, ranked, bets), before)

    def test_attack_and_second_third_are_separate(self):
        source, ranked, bets = fixture()
        out = evaluate(source, ranked, bets)
        self.assertTrue(out["threats"][0]["inside_displacement_hypothesis"])
        source["racers"][0]["original_exhibition"]["turn_time"] = 5.26
        source["racers"][3]["exhibition_time"] = 6.74
        out = evaluate(source, ranked, bets)
        self.assertEqual(out["status"], "ATTACK_PATHS_PRESENT")
        self.assertTrue(out["threats"][0]["inside_second_third_path_supported"])

    def test_exhibition_f_is_not_legal_start_advantage(self):
        source, ranked, bets = fixture()
        source["racers"][3]["exhibition_st"] = -.04
        out = evaluate(source, ranked, bets)
        self.assertEqual(out["status"], "ATTACK_PATHS_PRESENT")
        self.assertFalse(out["threats"][0]["legal_exhibition_st_confirmation"])

    def test_post_race_labels_cannot_change_pre_race_diagnosis(self):
        source, ranked, bets = fixture()
        before = evaluate(source, ranked, bets)
        source.update(result={"finish": "4-1-3"}, payout=9999999,
                      actual_start={"1": .28}, odds={"4-1-3": 100})
        self.assertEqual(evaluate(source, ranked, bets), before)

    def test_invalid_provenance_or_missing_evidence_fail_closed(self):
        source, ranked, bets = fixture()
        source["frozen_at_utc"] = "2026-11-14T01:29:00+00:00"
        self.assertEqual(evaluate(source, ranked, bets)["status"], "NO_SAFE_PRE_CUTOFF_FREEZE")
        source["frozen_at_utc"] = "2026-11-14T01:00:00+00:00"
        source["racers"][2]["original_exhibition"] = None
        self.assertEqual(evaluate(source, ranked, bets)["status"], "MISSING_SIX_BOAT_TURN_AND_TIME")

    def test_course_swap_and_edo_exclusion(self):
        source, ranked, bets = fixture()
        source["racers"][0]["course"] = 2
        source["racers"][1]["course"] = 1
        self.assertEqual(evaluate(source, ranked, bets)["status"], "LANE_ONE_NOT_IN_COURSE_ONE")
        source["venue"] = "江戸川"
        self.assertEqual(evaluate(source, ranked, bets)["status"], "NOT_ELIGIBLE")

    def test_bad_rankings_do_not_leak_into_research(self):
        source, ranked, bets = fixture()
        wrong = copy.deepcopy(ranked)
        wrong[0]["score"] = .5
        self.assertEqual(evaluate(source, wrong, bets)["status"], "INVALID_CANONICAL_RANKING")
        wrong = copy.deepcopy(ranked)
        wrong[0]["combination"] = wrong[1]["combination"]
        self.assertEqual(evaluate(source, wrong, bets)["status"], "INVALID_CANONICAL_RANKING")


if __name__ == "__main__":
    unittest.main()
