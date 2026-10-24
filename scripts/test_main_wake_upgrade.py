"""New main v0.9 starts 2026-10-25, but never overwrites an older fixed prediction."""
from __future__ import annotations
import copy
import unittest
from datetime import date, datetime
from unittest.mock import patch
from scripts import autonomous_daily as A

def fixture(day="2026-10-25"):
    return {
        "closed_at": day+" 12:00:00",
        "racers": {str(i): {
            "name": "選手"+str(i),
            "national_win_rate": [5.8,5.9,5.7,8.7,8.5,5.8][i-1],
            "motor_top_2_percent":[31,33,36,77,70,29][i-1],
            "average_start_timing":[.19,.18,.17,.08,.10,.17][i-1],
        } for i in range(1,7)}
    }

class WakeMainUpgradeTest(unittest.TestCase):
    def test_pre_cutoff_and_model_bridge(self):
        racers=A.features(fixture(),"baseline")[1]
        dt="2026-10-24T22:30:00+00:00"
        old=A.promoted_v07("唐津","baseline",racers,None,None,dt)
        new=A.promoted_v09("唐津","baseline",racers,None,None,dt)
        self.assertEqual(old["model_version"],A.MAIN_MODEL)
        self.assertEqual(new["model_version"],A.MAIN_WAKE_MODEL)
        self.assertEqual(new["wake_v09"]["applies_to_all_head_courses"],True)
        for model in (old,new):
            self.assertEqual(sum(b["virtual_yen"] for b in model["bets"]),50000)
            self.assertTrue(4<=len(model["bets"])<=12)
        # A v0.7 canonical before today's promotion remains v0.7.
        past=A.prediction(fixture("2026-10-24"),"唐津",1,"baseline",
            datetime.fromisoformat("2026-10-24T07:00:00+09:00"),"unit-test")
        self.assertEqual(past["model_version"],A.MAIN_MODEL)
        today=A.prediction(fixture(),"唐津",1,"baseline",
            datetime.fromisoformat("2026-10-25T07:00:00+09:00"),"unit-test")
        self.assertEqual(today["model_version"],A.MAIN_WAKE_MODEL)
        self.assertTrue(today["wake_v09"]["pre_cutoff_only"])
        self.assertEqual(today["legacy_control"]["model_version"],A.MAIN_MODEL)
        self.assertNotEqual(today["legacy_control"]["sha256"],today["sha256"])
        self.assertEqual(today["classification"],"WATCH")
        self.assertRaises(ValueError,A.prediction,fixture(),"唐津",1,"baseline",
            datetime.fromisoformat("2026-10-25T11:59:00+09:00"),"unit-test")

    def test_existing_main_old_sha_retained_and_unique_upgrade(self):
        race=fixture()
        at=datetime.fromisoformat("2026-10-25T07:20:00+09:00")
        with patch.object(A,"WAKE_PROMOTION_DATE",date(2026,10,26)):
            old=A.prediction(race,"唐津",1,"baseline",at,"unit-test")
        self.assertEqual(old["model_version"],A.MAIN_MODEL)
        existing={
           "event_date":"2026-10-25",
           "race_records":{"23-1":{
             "venue_code":"23","venue":"唐津","race":1,"cutoff_jst":"12:00",
             "versions":[copy.deepcopy(old)],"payouts":[]}}
        }
        source={"programs":{"stadiums":{"23":{"races":{"1":race}}}}}
        stamp=datetime.fromisoformat("2026-10-25T07:45:00+09:00")
        ledger,view,status=A.build(copy.deepcopy(existing),source,stamp,"unit-test")
        versions=ledger["race_records"]["23-1"]["versions"]
        self.assertEqual(len(versions),2)
        self.assertEqual(status["new_model_upgrades"],1)
        self.assertEqual(versions[0],old,"never rewrite old SHA or bets")
        self.assertEqual(versions[1]["model_version"],A.MAIN_WAKE_MODEL)
        self.assertEqual(versions[1]["model_upgrade"]["previous_sha256"],old["sha256"])
        self.assertTrue(versions[1]["model_upgrade"]["same_race_pre_cutoff_revision"])
        self.assertEqual(view["forecast_races"][0]["model_version"],A.MAIN_WAKE_MODEL)
        self.assertEqual(view["forecast_races"][0]["legacy_control"]["model_version"],A.MAIN_MODEL)
        # Idempotence and historical immutability.
        replay,web,stats=A.build(ledger,source,stamp,"unit-test")
        self.assertEqual(len(replay["race_records"]["23-1"]["versions"]),2)
        self.assertEqual(stats["new_model_upgrades"],0)
        self.assertEqual(replay["race_records"]["23-1"]["versions"][0],old)
        # After cutoff an older v0.7 version can never be replaced or augmented.
        late=datetime.fromisoformat("2026-10-25T12:10:00+09:00")
        unchanged,_,c=A.build(copy.deepcopy(existing),source,late,"unit-test")
        self.assertEqual(len(unchanged["race_records"]["23-1"]["versions"]),1)
        self.assertEqual(c["new_model_upgrades"],0)

if __name__=="__main__":
    unittest.main()
