import unittest
from scripts.research_start_gap import study
def example(code,st,finish="4-5-1",method="まくり",courses=None):
    return {"race_code":code,"venue":"唐津","boats":[{
        "lane":i,"course":(courses or [1,2,3,4,5,6])[i-1],
        "exhibition_st":st[i-1], "exhibition_f":st[i-1]<0
    } for i in range(1,7)],"result":{
        "source":"BoatraceCSV/realtime_unofficial","finish":finish,"decision":method}}
class StartResearchTest(unittest.TestCase):
    def test_gap_and_provenance(self):
        doc={"schema":"boatlabs.exhibition_research.v1","event_date":"2026-10-24","records":[
            example("202610242301",[.16,.17,.18,.08,.10,.11]),
            example("202610242302",[.16,.17,.18,.20,.25,.29],"1-2-4","逃げ"),
            example("202610242303",[.16,.17,.18,-.03,.1,.11]),
            example("202610242304",[.16,.17,.18,.08,.1,.11],finish="4-4-1"),
            example("202610232305",[.16,.17,.18,.08,.1,.11]),
            example("202610242301",[.16,.17,.18,.08,.1,.11]),
        ]}
        out=study([doc])
        self.assertEqual(out["valid_result_races"],3)
        a=[x for x in out["groups"] if x["course"]==4 and
           x["exhibition_gap_vs_inner"]=="earlier_by_003s_plus"][0]
        self.assertEqual(a["n"],1)
        self.assertEqual(a["first"],1)
        self.assertEqual(a["winning_makuri_or_makurizashi"],1)
        unknown=[x for x in out["groups"] if x["course"]==4 and
          x["exhibition_gap_vs_inner"]=="unavailable"][0]
        self.assertEqual(unknown["n"],1)
        self.assertIn("NOT actual race ST",out["warning"])
if __name__=="__main__":unittest.main()
