"""Past results are TRAINING labels only; never join a live target outcome."""
import unittest
from datetime import date, datetime, timedelta, timezone
from scripts.finish_pair_research import build, fetch_history, _valid_row


def row(day, venue="12", race=1, winner="1", second="3", third="5",
        method="まくり", order=None):
    code=f"{day:%Y%m%d}{venue}{race:02d}"
    item={"レースコード":code, "レース日":day.isoformat(),
          "決まり手":method,
          "1着_艇番":winner,"2着_艇番":second,"3着_艇番":third}
    for course, lane in enumerate(order or range(1,7),1):
        item[f"{course}コース_艇番"]=str(lane)
        item[f"{course}コース_スタートタイミング"]="0.15"
        item[f"{course}コース_F"]=""
    return item


class FinishPairPriorsTests(unittest.TestCase):
    def setUp(self):
        self.day=date(2026,11,3)
        self.now=datetime(2026,11,3,0,20,tzinfo=timezone.utc)

    def test_history_ends_previous_day_and_venue_excludes_edogawa(self):
        records=[]
        start=self.day-timedelta(days=15)
        for delta in range(14):
            day=start+timedelta(days=delta)
            for race in (1,2,3):
                records.append(row(day,race=race))
        records.append(row(self.day, race=1))
        records.append(row(self.day+timedelta(days=1), race=2))
        records.append(row(self.day-timedelta(days=1),venue="03",race=5))
        result=build(self.day,records,collected_at=self.now)
        self.assertEqual(result["validated_historical_races"],42)
        self.assertEqual(result["historical_date_range"]["max"],"2026-11-01")
        self.assertEqual(result["forecast_eligibility"],
                         "RESEARCH_ONLY_NOT_FROZEN_NOT_READY_FOR_AUTOMATIC_PICKS")
        group=result["groups"]["venue:12:head_course:1"]
        self.assertEqual(group["sample_count"],42)
        self.assertEqual(group["status"],"DESCRIPTIVE_ONLY_NOT_CALIBRATED")
        self.assertEqual(group["possible_ordered_pairs"],20)
        self.assertEqual(group["top_pairs"][0]["second_course"],3)
        self.assertEqual(group["top_pairs"][0]["third_course"],5)
        self.assertEqual(group["top_pairs"][0]["observed_count"],42)
        self.assertTrue(group["top_pairs"][0]["smoothed_share"] < 1)
        self.assertFalse(result["result_data_used_for_current_race_prediction"])
        self.assertEqual(result["formal_forecasts_modified"],0)
        self.assertTrue(all("venue:03:" not in key for key in result["groups"]))

    def test_actual_course_is_not_assumed_to_equal_lane(self):
        old=self.day-timedelta(days=2)
        changed=row(old,venue="18",race=3,winner="4",second="1",third="6",
                    order=[1,4,3,2,5,6])
        seen=_valid_row(changed,self.day)
        self.assertEqual((seen["head_course"],seen["second_course"],seen["third_course"]),
                         (2,1,6))
        report=build(self.day,[changed],collected_at=self.now)
        self.assertEqual(report["groups"]["venue:18:head_course:2"]["sample_count"],1)
        self.assertEqual(report["groups"]["venue:18:head_course:2"]["status"],
                         "INSUFFICIENT_SAMPLE")
        self.assertEqual(report["groups"]["venue:18:head_course:2"]["top_pairs"],[])

    def test_flying_or_duplicate_course_or_finish_rejected(self):
        old=self.day-timedelta(days=1)
        cases=[]
        for field,value in (("1コース_F","F"),
                            ("1コース_スタートタイミング","-0.05"),
                            ("2コース_艇番","1"),
                            ("2着_艇番","1"),
                            ("レース日","2026-11-03")):
            candidate=row(old)
            candidate[field]=value
            cases.append(candidate)
        result=build(self.day,cases,collected_at=self.now)
        self.assertEqual(result["validated_historical_races"],0)
        self.assertEqual(result["groups"],{})
        self.assertEqual(sum(result["rejected"].values()),len(cases))

    def test_duplicate_race_does_not_inflate_sample_count(self):
        r=row(self.day-timedelta(days=2),race=1)
        report=build(self.day,[r,r],collected_at=self.now)
        self.assertEqual(report["validated_historical_races"],1)
        self.assertEqual(report["rejected"]["duplicate_race"],1)

    def test_source_dates_never_include_current_target(self):
        observed=[]
        def fetcher(day):
            observed.append(day)
            return [row(day)], {"day":day.isoformat()}
        rows,meta=fetch_history(self.day,7,fetcher=fetcher)
        self.assertEqual(len(rows),7)
        self.assertEqual(min(observed),self.day-timedelta(days=7))
        self.assertEqual(max(observed),self.day-timedelta(days=1))
        self.assertNotIn(self.day,observed)
        self.assertEqual(len(meta),7)

    def test_invalid_reference_or_unreasonable_support_is_rejected(self):
        with self.assertRaises(ValueError):
            build(self.day,[],collected_at=self.now,min_samples=5)
        with self.assertRaises(ValueError):
            build(self.day,[],collected_at=datetime(2026,11,3))
