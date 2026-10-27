"""Forward v1.3 must never replace a pre-cutoff SHA or edit completed races."""
import copy
import unittest
from datetime import datetime
from scripts import autonomous_daily as A

def race(preview=True):
    src={
       "closed_at":"2026-10-27 20:00:00",
       "racers":{str(i):{
          "name":f"Racer {i}",
          "national_win_rate":[5.4,5.1,5.2,5.5,6.6,6.2][i-1],
          "average_start_timing":.14 if i>=5 else .17,
          "motor_top_2_percent":55 if i==5 else 30
       } for i in range(1,7)}
    }
    if preview:
        src["preview"]={
          "wind_speed":2,"wave_height":1,
          "racers":{str(i):{
             "course_number":i,"exhibition_time":6.78 if i==5 else (6.82 if i==6 else 6.90),
             "start_timing":.04 if i==5 else .16,"tilt_adjustment":0
          } for i in range(1,7)}
        }
    return src

def payload(preview=True):
    return {"programs":{"stadiums":{"10":{"races":{"12":race(preview)}}}}}

class ConditionalForecastTests(unittest.TestCase):
    def test_rollout_upgrades_old_frozen_with_new_sha_only_before_cutoff(self):
        old_time=datetime.fromisoformat("2026-10-27T15:00:00+09:00")
        new_time=datetime.fromisoformat("2026-10-27T17:30:00+09:00")
        old,_,_=A.build(None,payload(),old_time,"fixture")
        before=copy.deepcopy(old["race_records"]["10-12"]["versions"])
        assert before and before[-1]["model_version"]==A.FOUR_FACTOR_MODEL
        new,ui,status=A.build(old,payload(),new_time,"fixture")
        versions=new["race_records"]["10-12"]["versions"]
        assert versions[:len(before)]==before
        final=versions[-1]
        assert final["model_version"]==A.POSTRACE_CONDITIONAL_MODEL
        assert final["model_role"]=="main"
        assert final["model_upgrade"]["previous_sha256"]==before[-1]["sha256"]
        assert final["postrace_conditional_v13"]["result_data_used"] is False
        assert final["postrace_conditional_control"]["model_version"]==A.HEAD_COVERAGE_MODEL
        assert final["postrace_conditional_control"]["frozen_at_utc"]==final["frozen_at_utc"]
        assert final["sha256"]!=before[-1]["sha256"]
        assert 4<=len(final["bets"])<=12
        assert sum(x["virtual_yen"] for x in final["bets"])==50000
        assert ui["forecast_races"][0]["postrace_conditional_v13"]["pre_cutoff_only"] is True
        unchanged=copy.deepcopy(versions)
        again,_,_=A.build(new,payload(),new_time,"fixture")
        assert again["race_records"]["10-12"]["versions"]==unchanged
        closed,_,_=A.build(new,payload(),datetime.fromisoformat("2026-10-27T20:01:00+09:00"),"fixture")
        assert closed["race_records"]["10-12"]["versions"]==unchanged

    def test_new_main_does_not_need_or_consume_result_or_odds(self):
        t=datetime.fromisoformat("2026-10-27T17:30:00+09:00")
        a,_,_=A.build(None,payload(),t,"fixture")
        x=copy.deepcopy(payload())
        x["programs"]["stadiums"]["10"]["races"]["12"]["result"]={"finish":"5-6-1"}
        x["programs"]["stadiums"]["10"]["races"]["12"]["payout"]=99999
        b,_,_=A.build(None,x,t,"fixture")
        assert a["race_records"]["10-12"]["versions"]==b["race_records"]["10-12"]["versions"]

if __name__ == '__main__':
    unittest.main()
