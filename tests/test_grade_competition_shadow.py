"""Safety and competitive-ability tests for G1-only forward shadow."""
from itertools import permutations
import math
import unittest

from scripts.grade_competition_shadow import grade_from_program, rescore, VERSION

NOW = "2026-11-07T00:00:00+00:00"
CUTOFF = "2026-11-07T01:00:00+00:00"


def rows(close=True):
    return [{"lane": i, "course": i, "national_win_rate": 7.1 + i*.1 if close else 4.1+i*.65}
            for i in range(1, 7)]


def outcomes():
    weights = {i: 1/(i**1.2) for i in range(1, 7)}
    triples = []
    for a,b,c in permutations(range(1, 7), 3):
        triples.append(("-".join(map(str,(a,b,c))), weights[a]*weights[b]*weights[c]))
    total = sum(x[1] for x in triples)
    return [{"combination": k,"relative_score":v/total} for k,v in triples]


class GradeCompetitionTests(unittest.TestCase):
    def trial(self, grade=None, rs=None, os=None, phase=True, now=NOW):
        return rescore(os if os is not None else outcomes(),
                       rs if rs is not None else rows(),
                       grade if grade is not None else grade_from_program({
                           "grade_number": 2,"grade_number_source":"G1b"}),
                       now, CUTOFF, exhibition_verified=phase)

    def test_grade_mapping_not_ordinal(self):
        self.assertEqual(grade_from_program({"grade_number": 2})["grade"], "G1")
        self.assertEqual(grade_from_program({"grade_number": 5})["grade"], "GENERAL")
        self.assertEqual(grade_from_program({"grade_number": 6,"grade_number_source":"G1a"})["grade"], "PG1")
        self.assertEqual(grade_from_program({"grade_number": 1})["grade"], "SG")
        self.assertEqual(grade_from_program({"grade_number": 2,"grade_number_source":"ippan"})["status"], "CONFLICT")
        self.assertEqual(grade_from_program({"title":"G1 XXX"})["status"], "UNKNOWN")
        self.assertEqual(grade_from_program({"grade_number": True})["status"], "UNKNOWN")

    def test_bounds_and_real_grade_source(self):
        r = self.trial()
        self.assertEqual(r["version"], VERSION)
        self.assertEqual(r["status"], "BOUNDED_G1_PARITY_HYPOTHESIS")
        self.assertFalse(r["result_data_used"])
        self.assertTrue(r["not_formal"])
        self.assertTrue(r["no_additional_stake"])
        self.assertFalse(r["calibrated"])
        self.assertEqual(r["grade_number"], 2)
        self.assertEqual(len(r["outcomes"]), 120)
        self.assertAlmostEqual(sum(x["relative_score"] for x in r["outcomes"]), 1., places=10)
        self.assertLess(r["head_marginal_after"]["1"], r["head_marginal_before"]["1"])
        self.assertGreater(r["head_marginal_after"]["6"], r["head_marginal_before"]["6"])

    def test_other_grade_no_unearned_bonus(self):
        for num in (1,3,4,5,6):
            self.assertIsNone(self.trial(grade=grade_from_program({"grade_number":num})))
        self.assertIsNone(self.trial(grade=grade_from_program({"title":"G1"})))
        self.assertIsNone(self.trial(grade=grade_from_program({"grade_number":2,"grade_number_source":"ippan"})))
        self.assertIsNone(self.trial(phase=False))

    def test_highly_unbalanced_field_no_adjustment(self):
        self.assertIsNone(self.trial(rs=rows(close=False)))
        missing = rows()
        missing[0].pop("national_win_rate")
        self.assertIsNone(self.trial(rs=missing))
        missing = rows()
        missing[2]["national_win_rate"]=float("nan")
        self.assertIsNone(self.trial(rs=missing))

    def test_actual_entry_unique_required(self):
        rs = rows()
        rs[1]["course"] = rs[0]["course"]
        with self.assertRaises(ValueError):
            self.trial(rs=rs)

    def test_result_or_odds_leakage_blocked(self):
        rs = rows()
        rs[0]["finish"] = 1
        with self.assertRaises(ValueError):
            self.trial(rs=rs)
        os = outcomes()
        os[0]["payout"] = 10000
        with self.assertRaises(ValueError):
            self.trial(os=os)

    def test_snapshot_must_precede_cutoff(self):
        with self.assertRaises(ValueError):
            self.trial(now=CUTOFF)
        with self.assertRaises(ValueError):
            self.trial(now="2026-11-07T02:00:00+00:00")
        with self.assertRaises(ValueError):
            self.trial(now="2026-11-07T00:00:00")

    def test_missing_or_nonnormalized_ranking_fails(self):
        os=outcomes()
        os[0]["relative_score"]=float("inf")
        with self.assertRaises(ValueError):
            self.trial(os=os)
        os=outcomes()
        os[0]["combination"]=os[1]["combination"]
        with self.assertRaises(ValueError):
            self.trial(os=os)

    def test_venue_never_enters_model(self):
        self.assertEqual(self.trial()["outcomes"], self.trial()["outcomes"])
        self.assertNotIn("venue", self.trial())
        self.assertNotIn("bets", self.trial())


if __name__ == "__main__":
    unittest.main()
