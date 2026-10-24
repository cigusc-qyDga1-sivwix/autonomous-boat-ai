"""The archived results can describe survivors; they cannot observe wake crossings."""
import unittest
from scripts.research_wake_hypotheses import summarize, research

class WakeResearchTests(unittest.TestCase):
    def test_outcome_proxy_not_claimed_as_physical_wake(self):
        rows=[
          {"finish_courses":(4,5,1),"decision":"まくり","venue":"唐津"},
          {"finish_courses":(4,1,5),"decision":"まくり","venue":"唐津"},
          {"finish_courses":(1,2,3),"decision":"逃げ","venue":"児島"},
          {"finish_courses":(3,1,2),"decision":"まくり差し","venue":"住之江"},
          {"finish_courses":(2,3,1),"decision":"差し","venue":"三国"},
          {"finish_courses":(4,4,1),"decision":"まくり"},
        ]
        report=summarize(rows)
        self.assertEqual(report["sample_races"],5)
        slices={item["segment"]:item for item in report["segments"]}
        attack=slices["center_outer_attack"]
        self.assertEqual(attack["sample"],3)
        self.assertEqual(attack["counts"]["inner_second"],2)
        self.assertEqual(attack["counts"]["next_course_second"],1)
        self.assertEqual(attack["support"],"too_few_cases")
        self.assertEqual(slices["inside_1_escape"]["sample"],1)
        self.assertEqual(report["predictor_training"],"disabled")
        self.assertEqual(report["frozen_forecasts"],"unchanged")
        self.assertIn("DO NOT observe wake contact",report["warning"])
        self.assertNotIn("wake_probability",str(report).split("warning")[0])
        for key in ("wake_crossing_per_boat","wake_contact_time","speed_loss_after_contact"):
            self.assertIn(key,report["missing_physical_observations"])
        self.assertNotIn("payout",str(report))
    def test_empty_is_safe(self):
        report=summarize([])
        self.assertEqual(report["sample_races"],0)
        self.assertEqual(report["segments"],[])

if __name__=="__main__":
    unittest.main()
