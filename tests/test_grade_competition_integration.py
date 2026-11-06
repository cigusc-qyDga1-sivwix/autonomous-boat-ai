"""G1 source read and shadow-vs-formal integration in real prediction path."""
from copy import deepcopy
from datetime import datetime
from unittest import TestCase
from scripts import autonomous_daily as A
from tests.test_four_factor_main import race

NOW = datetime.fromisoformat("2026-11-07T08:30:00+09:00")


def fixture(grade=2):
    r=race("2026-11-07")
    for i in range(1,7):
        r["racers"][str(i)]["national_win_rate"] = 7.0 + .1*i
    if grade is not None:
        r["grade_number"]=grade
        r["grade_number_source"] = {2:"G1b",5:"ippan",6:"G1a"}[grade]
    return r


class GradeCompetitionIntegrationTests(TestCase):
    def predict(self, r):
        return A.prediction(r,"住之江",1,"exhibition",NOW,"fixture")

    def test_verified_g1_creates_independent_shadow(self):
        original=fixture()
        untouched=deepcopy(original)
        pred=self.predict(original)
        self.assertEqual(original,untouched)
        self.assertEqual(pred["model_version"], A.LINKED_MAIN_MODEL)
        self.assertEqual(pred["grade_context"]["grade"], "G1")
        shadow=pred["grade_competition_shadow"]
        self.assertEqual(shadow["status"],"BOUNDED_G1_PARITY_HYPOTHESIS")
        self.assertTrue(shadow["not_formal"])
        self.assertFalse(shadow["result_data_used"])
        self.assertTrue(shadow["no_additional_stake"])
        self.assertEqual(shadow["frozen_at_utc"],pred["frozen_at_utc"])
        self.assertTrue(shadow["point_count_matched"])
        self.assertEqual(sum(b["virtual_yen"] for b in pred["bets"]),50000)
        self.assertEqual(sum(b["virtual_yen"] for b in shadow["forecast_alternative_bets"]),50000)

    def test_grade_only_changes_shadow_not_formal(self):
        g1=self.predict(fixture(grade=2))
        standard=self.predict(fixture(grade=5))
        unknown=self.predict(fixture(grade=None))
        self.assertEqual(g1["bets"],standard["bets"])
        self.assertEqual(g1["bets"],unknown["bets"])
        self.assertNotIn("grade_competition_shadow",standard)
        self.assertNotIn("grade_competition_shadow",unknown)
        self.assertEqual(standard["grade_context"]["grade"],"GENERAL")
        self.assertEqual(unknown["grade_context"]["status"],"UNKNOWN")

    def test_premium_g1_is_separate_stratum(self):
        pg1=self.predict(fixture(grade=6))
        self.assertEqual(pg1["grade_context"]["grade"],"PG1")
        self.assertNotIn("grade_competition_shadow",pg1)

    def test_baseline_has_grade_but_no_trial_without_exhibition(self):
        p=A.prediction(fixture(),"住之江",1,"baseline",NOW,"fixture")
        self.assertEqual(p["grade_context"]["grade"],"G1")
        self.assertNotIn("grade_competition_shadow",p)

    def test_postrace_fields_do_not_affect_shadow_or_main(self):
        r=fixture()
        p=self.predict(r)
        r["result"]={"finish":"4-5-6","payout":999999}
        q=self.predict(r)
        self.assertEqual(p["bets"],q["bets"])
        self.assertEqual(p["grade_competition_shadow"],q["grade_competition_shadow"])


if __name__=="__main__":
    import unittest
    unittest.main()
