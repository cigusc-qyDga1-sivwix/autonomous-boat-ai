"""2026-10-28 first-mark study: purely synthetic, offline acceptance tests."""
import copy
from datetime import datetime
import unittest

from scripts.turn_three_pilot import (
    build, outcome_label, sha, STUDY_DAY, PLACES, SCHEMA, LEGACY_SCHEMA, EXCLUDED_FROM_TURN_MODEL, race_cutoff,
)


def fixture(code="23",race_no=1,day=STUDY_DAY,inside=1,finish=None):
    boats=[{
        "lane":i,"name":f"research racer {i}","course":(i if inside==1 else {1:2,2:1}.get(i,i)),
        "exhibition_time":6.70+i/100,"exhibition_st":0.10+i/100,
        "tilt":-0.5,"original_exhibition":[{"metric":"まわり足","value":5.1+i/10}],
    } for i in range(1,7)]
    return {"race_code":day.replace("-","")+code+f"{race_no:02d}",
        "venue_code":code,"race":race_no,"boats":boats,
        "cutoff_jst":"10:00",
        "source_observed_jst":day+"T09:20:00+09:00",
        "first_seen_at_utc":day+"T00:22:00+00:00",
        "weather":{"wind_mps":2,"wave_cm":1},
        "result":None if finish is None else {
            "finish":finish,"decision":"差し","source":"BoatraceCSV/realtime_unofficial",
            "recorded_jst":day+"T10:20:00+09:00"}}


def archived(*rows):
    return {"schema":"boatlabs.exhibition_research.v1","event_date":STUDY_DAY,
            "created_at_utc":"2026-10-28T00:20:00+00:00","records":list(rows)}


class TestThreeVenueTurnAudit(unittest.TestCase):
    def test_model_case_scope(self):
        out=build(STUDY_DAY,None,now=datetime.fromisoformat("2026-10-27T22:20:00+00:00"))
        self.assertEqual(out["schema"],SCHEMA)
        self.assertEqual(len(out["targets"]),120)
        self.assertEqual(out["summary"]["study_venues"],10)
        self.assertEqual(out["summary"]["primary_races"],36)
        self.assertEqual(out["summary"]["extended_races"],84)
        self.assertEqual([out["summary"][x] for x in ("morning_races","day_races","night_races")],[24,60,36])
        self.assertEqual(len({t["venue_code"] for t in out["targets"]}),10)
        self.assertFalse(any(t["venue_code"]=="03" for t in out["targets"]))
        self.assertEqual({(t["session"],t["venue_code"]) for t in out["targets"]},
                         {("morning","23"),("morning","10"),
                          ("day","16"),("day","13"),("day","09"),("day","08"),("day","22"),
                          ("night","07"),("night","01"),("night","15")})
        self.assertEqual(out["summary"]["video_races_analyzed"],0)
        self.assertEqual(out["summary"]["precutoff_numeric_pilot_captures"],0)
        self.assertTrue(all(t["video"]["status"]=="NO_LICENSED_VIDEO_ANALYZED" for t in out["targets"]))
        self.assertTrue(all(t["outcome"]["first_mark_cause"]=="UNOBSERVED" for t in out["targets"]))

    def test_immutable_first_prestart_numeric_snapshot(self):
        r=fixture()
        one=build(STUDY_DAY,archived(r),now=datetime.fromisoformat("2026-10-28T00:25:00+00:00"))
        item=one["targets"][0]
        self.assertEqual(item["venue"],"唐津")
        self.assertEqual(item["data_status"],"SIX_BOAT_EXHIBITION_RESEARCH_AVAILABLE")
        self.assertIsNotNone(item["first_numeric_observation"])
        original=copy.deepcopy(item["first_numeric_observation"])
        r["boats"][0]["exhibition_time"]=9.99
        r["result"]={"finish":"2-1-3","decision":"差し",
                     "source":"BoatraceCSV/realtime_unofficial"}
        two=build(STUDY_DAY,archived(r),one,now=datetime.fromisoformat("2026-10-28T01:20:00+00:00"))
        self.assertEqual(two["targets"][0]["first_numeric_observation"],original)
        self.assertEqual(two["targets"][0]["outcome"]["outcome"],"COURSE_ONE_LOST")
        self.assertIsNone(two["targets"][0]["outcome"]["escape_failed_by_turn_error"])
        self.assertEqual(two["summary"]["video_races_analyzed"],0)

    def test_late_preview_not_backdated(self):
        result=build(STUDY_DAY,archived(fixture()),
                     now=datetime.fromisoformat("2026-10-28T02:00:00+00:00"))
        row=result["targets"][0]
        self.assertEqual(row["data_status"],"SIX_BOAT_EXHIBITION_RESEARCH_AVAILABLE")
        self.assertIsNone(row["first_numeric_observation"])
        self.assertEqual(row["earliest_observation_before_cutoff"],"NOT_CONFIRMED_PRIOR_TO_CUTOFF")
        self.assertEqual(result["summary"]["precutoff_numeric_pilot_captures"],0)

    def test_bad_source_timestamp_rejected_prestart(self):
        rec=fixture(); rec["first_seen_at_utc"]="2026-10-28T02:05:00+00:00"
        result=build(STUDY_DAY,archived(rec),
                     now=datetime.fromisoformat("2026-10-28T00:25:00+00:00"))
        self.assertIsNone(result["targets"][0]["first_numeric_observation"])

    def test_wrong_race_code_never_crossjoins(self):
        rec=fixture(code="23")
        rec["race_code"]="202610280701"
        data=build(STUDY_DAY,archived(rec),now=datetime.fromisoformat("2026-10-28T00:25:00+00:00"))
        self.assertEqual(data["summary"]["exhibition_rows_seen"],0)

    def test_actual_course_one_winner_differs_when_entry_changes(self):
        original=fixture(inside=2,finish="1-2-3")
        self.assertEqual(outcome_label(original)["outcome"],"COURSE_ONE_LOST")
        original["result"]["finish"]="2-1-3"
        self.assertEqual(outcome_label(original)["outcome"],"COURSE_ONE_WON")
        self.assertEqual(outcome_label(original)["first_mark_cause"],"UNOBSERVED")

    def test_all_three_venues_all_twelve(self):
        records=[fixture(code=code,race_no=r)
                 for code in ("23","16","07") for r in range(1,13)]
        full=build(STUDY_DAY,archived(*records),now=datetime.fromisoformat("2026-10-28T00:20:00+00:00"))
        self.assertEqual(full["summary"]["target_races"],120)
        self.assertEqual(full["summary"]["observed_venues"],3)
        self.assertEqual(full["summary"]["exhibition_rows_seen"],36)
        self.assertEqual(full["summary"]["unofficial_result_rows"],0)

    def test_ten_venue_full_exhibition_research_coverage(self):
        codes=[value["venue_code"] for value in PLACES.values()]
        self.assertEqual(len(codes),len(set(codes)))
        rows=[fixture(code=code,race_no=r) for code in codes for r in range(1,13)]
        rows.append(fixture(code="03",race_no=1))  # 江戸川 nationally collected, not turn-scored.
        full=build(STUDY_DAY,archived(*rows),now=datetime.fromisoformat("2026-10-28T00:25:00+00:00"))
        self.assertEqual(full["summary"]["target_races"],120)
        self.assertEqual(full["summary"]["exhibition_rows_seen"],120)
        self.assertEqual(full["summary"]["observed_venues"],10)
        self.assertEqual(full["summary"]["precutoff_numeric_pilot_captures"],120)
        self.assertEqual(full["summary"]["video_races_analyzed"],0)
        self.assertFalse(any(x["venue_code"]=="03" for x in full["targets"]))

    def test_old_three_venue_snapshot_migrates_unchanged(self):
        first=build(STUDY_DAY,archived(fixture()),now=datetime.fromisoformat("2026-10-28T00:25:00+00:00"))
        expected=copy.deepcopy(first["targets"][0]["first_numeric_observation"])
        first["schema"]=LEGACY_SCHEMA
        new=build(STUDY_DAY,archived(),first,now=datetime.fromisoformat("2026-10-28T02:00:00+00:00"))
        self.assertEqual(new["targets"][0]["first_numeric_observation"],expected)
        self.assertEqual(new["summary"]["target_races"],120)
        self.assertEqual(new["summary"]["precutoff_numeric_pilot_captures"],1)

    def test_no_fabricated_outcome_on_invalid_result(self):
        rec=fixture(finish="1-1-3")
        self.assertEqual(outcome_label(rec)["state"],"RESULT_INVALID")

    def test_reject_other_dates_and_naive_clock(self):
        with self.assertRaises(ValueError):
            build("2026-10-29",archived())
        with self.assertRaises(ValueError):
            build(STUDY_DAY,archived(),now=datetime(2026,10,28,7,20))

    def test_cutoff_and_sha_deterministic(self):
        self.assertEqual(race_cutoff(STUDY_DAY,"10:00").isoformat(),"2026-10-28T10:00:00+09:00")
        self.assertEqual(sha({"z":1,"a":2}),sha({"a":2,"z":1}))


if __name__=="__main__":
    unittest.main()
