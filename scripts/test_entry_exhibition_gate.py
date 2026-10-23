#!/usr/bin/env python3
"""No-network, future-safe regression tests for exhibition and front entry gate."""
import copy
import unittest
from datetime import datetime
from entry_exhibition_gate import validated_courses, validated_preview, summarize_gate
from autonomous_daily import preview_complete

DAY = "2026-10-23"
COURSES = [1, 4, 5, 3, 6, 2]  # By lane => start-exhibition 1-6-4-2-3-5.


def racers(courses=None, name6="赤岩 善生"):
    cs = courses or [1, 2, 3, 4, 5, 6]
    return [{"lane": i, "course": cs[i-1],
             "name": name6 if i == 6 else f"選手{i}",
             "exhibition_st": .07+i/100,
             "exhibition_time": 6.6+i/100}
            for i in range(1, 7)]


def preview(courses=None):
    cs = courses or COURSES
    return {"racers": {str(i): {"course_number": str(cs[i-1]),
             "start_timing": .1, "exhibition_time": 6.8}
            for i in range(1, 7)}}


def race_snapshot(phase="exhibition", courses=None, frozen="2026-10-23T08:00:00Z",
                  cutoff="17:50", name6="赤岩 善生"):
    return {"phase": phase, "racers": racers(courses, name6),
            "frozen_at_utc": frozen, "cutoff_jst": cutoff,
            "exhibition_origin": {"source": "BoatraceCSV"}}


class EntryGateTests(unittest.TestCase):
    def test_start_exhibition_reorder_and_validity(self):
        self.assertEqual(validated_preview(preview()), tuple(COURSES))
        self.assertTrue(preview_complete({"preview": preview()}))
        snap = race_snapshot(courses=COURSES)
        original = copy.deepcopy(snap)
        result = summarize_gate(snap, DAY)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["exhibition_course_order"], [1,6,4,2,3,5])
        self.assertTrue(result["entry_changed"])
        self.assertTrue(result["entry_watch"])
        self.assertEqual(result["entry_watch_racers"], ["赤岩善生"])
        self.assertIs(result["buy_allowed"], False)
        self.assertEqual(snap, original, "derive gate without mutating frozen SHA source")
    def test_baseline_even_watchlist_missing_never_final(self):
        snap = race_snapshot("baseline")
        self.assertEqual(summarize_gate(snap, DAY)["status"], "hold")
        snap["racers"][5]["name"]="その他"
        self.assertEqual(summarize_gate(snap, DAY)["status"], "hold")
        self.assertFalse(summarize_gate(snap, DAY)["entry_watch"])
    def test_duplicate_course_and_missing_measurement(self):
        bad = [1,2,2,4,5,6]
        self.assertIsNone(validated_preview(preview(bad)))
        self.assertFalse(preview_complete({"preview": preview(bad)}))
        self.assertEqual(summarize_gate(race_snapshot(courses=bad),DAY)["status"],"hold")
        badp=preview()
        del badp["racers"]["4"]["start_timing"]
        self.assertFalse(preview_complete({"preview": badp}))
        badsnap=race_snapshot(courses=COURSES)
        badsnap["racers"][3]["exhibition_time"]=None
        self.assertFalse(summarize_gate(badsnap,DAY)["final_eligible"])
    def test_fractional_or_missing_course(self):
        fractional=preview();fractional["racers"]["6"]["course_number"]="2.5"
        self.assertFalse(preview_complete({"preview":fractional}))
        p=preview();p["racers"]["6"].pop("course_number")
        self.assertFalse(preview_complete({"preview":p}))
        self.assertIsNone(validated_courses(racers([1,2,3,4,5,5])))
    def test_after_cutoff_and_late_commit_fail_closed(self):
        for stamp in ["2026-10-23T08:49:00Z","2026-10-23T08:50:01Z",
                      "2026-10-23T11:00:00Z"]:
            self.assertFalse(summarize_gate(
                race_snapshot(courses=COURSES,frozen=stamp),DAY)["final_eligible"])
        self.assertFalse(summarize_gate(race_snapshot(courses=COURSES),None)["final_eligible"])
    def test_negative_exhibition_st_is_not_fast_bonus(self):
        p=preview();p["racers"]["6"]["start_timing"]=-.12
        self.assertTrue(preview_complete({"preview":p}))
        snap=race_snapshot(courses=COURSES)
        snap["racers"][5]["exhibition_st"]=-.12
        self.assertTrue(summarize_gate(snap,DAY)["exhibition_verified_before_cutoff"])


if __name__ == "__main__":
    unittest.main()
