"""Guard against G1 shadow hindsight leakage and accidental mismatched comparisons."""
from copy import deepcopy
import unittest
from scripts.audit_grade_competition_shadow import valid_trial, analyze

BETS = [
    {"combination":"1-2-3","virtual_yen":20000},
    {"combination":"2-1-3","virtual_yen":12000},
    {"combination":"3-1-2","virtual_yen":10000},
    {"combination":"4-1-2","virtual_yen":8000},
]
ALT = [
    {"combination":"4-1-2","virtual_yen":20000},
    {"combination":"3-1-2","virtual_yen":12000},
    {"combination":"2-1-3","virtual_yen":10000},
    {"combination":"1-2-3","virtual_yen":8000},
]
SNAP = {
    "venue":"住之江", "race":1, "phase":"exhibition",
    "frozen_at_utc":"2026-11-07T05:00:00+00:00",
    "cutoff_jst":"15:17",
    "bets":BETS,
    "grade_context":{
        "status":"SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK",
        "grade":"G1","grade_number":2},
    "grade_competition_shadow":{
        "grade_number":2,
        "model_role":"shadow_validation",
        "status":"BOUNDED_G1_PARITY_HYPOTHESIS",
        "not_formal":True,
        "no_additional_stake":True,
        "result_data_used":False,
        "frozen_at_utc":"2026-11-07T05:00:00+00:00",
        "point_count_matched":True,
        "forecast_alternative_bets":ALT,
    }
}


class GradeAuditTests(unittest.TestCase):
    def test_correct_pre_cutoff_provenance(self):
        self.assertEqual(valid_trial(SNAP),(True,"ready"))

    def test_other_grade_and_unfrozen_trials_excluded(self):
        for update in (
            ("grade_context",{"status":"SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK","grade":"GENERAL","grade_number":5}),
            ("grade_competition_shadow",{"point_count_matched":False}),
            ("grade_competition_shadow",{"result_data_used":True}),
            ("grade_competition_shadow",{"frozen_at_utc":"2026-11-07T05:01:00+00:00"}),
            ("grade_competition_shadow",{"forecast_alternative_bets":ALT[:2]}),
            ("grade_competition_shadow",{"forecast_alternative_bets":[ALT[0],ALT[0],ALT[2],ALT[3]]}),
        ):
            row=deepcopy(SNAP)
            row[update[0]].update(update[1])
            self.assertFalse(valid_trial(row)[0])

    def test_missing_official_pay_is_not_a_loss(self):
        ledger={"event_date":"2026-11-07","race_records":{"12-1":{"versions":[SNAP]}}}
        audit=analyze(ledger)
        self.assertEqual(audit["total"]["matched_races"],0)
        self.assertEqual(audit["exclusions"]["unverified"],1)

    def test_old_forecast_not_rebuilt_to_fit_results(self):
        row=deepcopy(SNAP)
        del row["grade_competition_shadow"]
        self.assertEqual(valid_trial(row),(False,"no_forward_g1_trial"))


if __name__=="__main__":
    unittest.main()
