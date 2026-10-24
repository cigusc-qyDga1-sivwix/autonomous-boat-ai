import unittest
from scripts.research_coupling_patterns import summarize
class CouplingPatternTests(unittest.TestCase):
    def test_outside_attack_and_inner_survival(self):
        rows=[{"venue":"鳴門","finish_courses":(4,5,1),"decision":"まくり"},
              {"venue":"鳴門","finish_courses":(4,1,5),"decision":"まくり差し"},
              {"venue":"唐津","finish_courses":(1,2,3),"decision":"逃げ"},
              {"venue":"唐津","finish_courses":(4,4,1),"decision":"まくり"}]
        x=summarize(rows)
        self.assertEqual(x["n_valid_results"],3)
        self.assertEqual(x["venue_n"]["鳴門"],2)
        attack=[p for p in x["segments"] if p["reported_winning_decision"]=="まくり"][0]
        self.assertEqual(attack["n"],1)
        self.assertEqual(attack["counts"]["following_course_second"],1)
        self.assertEqual(attack["counts"]["inside_course_third"],1)
        self.assertEqual(attack["support_status"],"insufficient_support")
        self.assertTrue(any("NEVER" in m or "Never" in m for m in x["critical_limits"]))
if __name__=="__main__":unittest.main()
