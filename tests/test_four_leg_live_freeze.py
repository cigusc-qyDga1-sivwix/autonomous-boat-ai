"""Forward-only four-leg evidence persistence and accounting separation."""
import unittest
from copy import deepcopy

from scripts.four_leg_live_freeze import merge_forward_evidence
from scripts.original_exhibition_venue_research import digest


DAY = "2026-11-18"
AT = "2026-11-18T02:55:00+00:00"
SNAP_SHA = "f" * 64


def capture():
    boats = [
        {"lane": i, "name": f"選手{i}",
         "lap_time": 37 + i / 10,
         "turn_time": 7.5 + i / 10,
         "straight_time": 7.6 + i / 100}
        for i in range(1, 7)
    ]
    return {
        "schema": "boatlabs.boatcast_oriten_smoke.v1",
        "date": DAY, "venue_code": "23", "race_number": 2,
        "status": "SIX_BOAT_PARSED_RESEARCH_ONLY",
        "source_url": "https://race.boatcast.jp/txt/23/bc_oriten_20261118_23_02.txt",
        "captured_at_utc": "2026-11-18T02:53:00+00:00",
        "source_body_sha256": "a" * 64,
        "metrics": ["lap_time", "turn_time", "straight_time"],
        "boats": boats,
        "measurement_sha256": digest(boats),
        "research_only": True, "formal_forecast_eligible": False,
    }


def ledger(c, *, formal=True):
    version = {
        "sha256": SNAP_SHA, "phase": "exhibition",
        "model_version": "four-factor-learned-v1-conditional-choice-trained",
        "model_role": "main",
        "venue": "唐津", "race": 2,
        "frozen_at_utc": "2026-11-18T02:54:00+00:00",
        "cutoff_iso_jst": "2026-11-18T12:00:00+09:00",
        "exhibition_origin": {
            "captured_before_cutoff": True,
            "original_exhibition_source": "BOATCAST_direct",
            "original_exhibition_measurement_sha256": c["measurement_sha256"],
            "original_exhibition_captured_at_utc": c["captured_at_utc"],
        },
        "exhibition_input_check": {
            "verified_before_freeze": True,
            "original_metrics_matched": ["lap_time", "turn_time", "straight_time"],
        },
        "racers": [
            {"lane": i, "course": i, "name": f"選手{i}",
             "exhibition_time": 6.71 + i * .01,
             "exhibition_st": .1 + i * .01}
            for i in range(1, 7)
        ],
        "bets": [{"combination": "1-2-3", "virtual_yen": 50000}],
    }
    if formal:
        version["original_exhibition_formal_v1"] = {
            "capture_sha256": digest(c),
            "measurement_sha256": c["measurement_sha256"],
            "formal_component": True,
        }
    return {
        "event_date": DAY,
        "race_records": {
            "23-2": {
                "venue_code": "23", "race": 2,
                "versions": [
                    {"phase": "baseline", "sha256": "a"*64},
                    version,
                ],
                "payouts": [],
            }
        },
    }


class FourLegLiveFreezeTests(unittest.TestCase):
    def test_same_run_capture_creates_sha_bound_evidence_without_model_edit(self):
        c = capture()
        before = ledger(c)
        frozen = deepcopy(before)
        saved, status = merge_forward_evidence(None, before, {"23-2": c},
                                               event_date=DAY, generated_at_utc=AT)
        self.assertEqual(before, frozen)
        self.assertEqual(status["new_evidence_versions"], 1)
        self.assertEqual(status["total_evidence_versions"], 1)
        self.assertEqual(status["evidence_races"], 1)
        self.assertEqual(status["venues_with_evidence"], 1)
        self.assertEqual(status["six_boat_original_metric_coverage_versions"]["turn_time"], 1)
        self.assertEqual(status["six_boat_original_metric_coverage_versions"]["straight_time"], 1)
        self.assertEqual(status["six_boat_original_metric_coverage_versions"]["half_lap_time"], 0)
        self.assertEqual(status["ikiasi_acceleration_independently_measured"], 0)
        self.assertEqual(status["deashi_acceleration_independently_measured"], 0)
        self.assertFalse(status["no_results_or_payouts_used"] is False)
        row = saved["race_versions"]["23-2"][SNAP_SHA]
        self.assertEqual(row["forecast_bets_sha256"], digest(before["race_records"]["23-2"]["versions"][-1]["bets"]))
        self.assertEqual(len(row["evidence"]["boats"]), 6)
        self.assertTrue(row["formal_bets_unchanged"])
        self.assertTrue(row["research_only"])
        self.assertFalse(row["postrace_result_used"])

    def test_immutable_repeat_no_capture_preserves_old(self):
        c = capture()
        data, _ = merge_forward_evidence(None, ledger(c), {"23-2": c},
                                         event_date=DAY, generated_at_utc=AT)
        original = deepcopy(data)
        data2, status = merge_forward_evidence(data, ledger(c), {},
                                               event_date=DAY,
                                               generated_at_utc="2026-11-18T03:02:00+00:00")
        self.assertEqual(data2, original)
        self.assertEqual(status["new_evidence_versions"], 0)
        self.assertEqual(status["preserved_evidence_versions"], 1)

    def test_unbound_original_source_is_not_misattributed(self):
        c = capture()
        data = ledger(c, formal=False)
        data["race_records"]["23-2"]["versions"][-1]["exhibition_origin"]["original_exhibition_measurement_sha256"] = "z"*64
        saved, status = merge_forward_evidence(None, data, {"23-2": c},
                                               event_date=DAY, generated_at_utc=AT)
        self.assertEqual(status["total_evidence_versions"], 0)
        self.assertFalse(saved["race_versions"])

    def test_nonformal_traceable_six_boat_source_is_allowed_as_research(self):
        c = capture()
        saved, status = merge_forward_evidence(None, ledger(c, formal=False), {"23-2": c},
                                               event_date=DAY, generated_at_utc=AT)
        self.assertEqual(status["new_evidence_versions"], 1)
        self.assertTrue(saved["race_versions"]["23-2"][SNAP_SHA]["research_only"])

    def test_wrong_racer_and_postfreeze_capture_fail_closed(self):
        for variant in ("wrong_name", "late_capture"):
            with self.subTest(variant=variant):
                c = capture()
                data = ledger(c)
                if variant == "wrong_name":
                    data["race_records"]["23-2"]["versions"][-1]["racers"][0]["name"] = "別人"
                else:
                    c["captured_at_utc"] = "2026-11-18T02:55:30+00:00"
                    data["race_records"]["23-2"]["versions"][-1]["original_exhibition_formal_v1"]["capture_sha256"] = digest(c)
                saved, status = merge_forward_evidence(None, data, {"23-2": c},
                                                       event_date=DAY, generated_at_utc=AT)
                self.assertEqual(status["new_evidence_versions"], 0)
                self.assertGreaterEqual(status["rejected_versions"], 1)
                self.assertEqual(status["total_evidence_versions"], 0)

    def test_outcomes_never_change_preserved_evidence(self):
        c = capture()
        first, _ = merge_forward_evidence(None, ledger(c), {"23-2": c},
                                          event_date=DAY, generated_at_utc=AT)
        later = ledger(c)
        later["race_records"]["23-2"]["payouts"] = [{"result": "3-4-1", "amount": 5000}]
        again, status = merge_forward_evidence(first, later, {},
                                               event_date=DAY,
                                               generated_at_utc="2026-11-18T04:10:00+00:00")
        self.assertEqual(first, again)
        self.assertEqual(status["new_evidence_versions"], 0)
        self.assertTrue(again["outcomes_payouts_not_used"])

    def test_wrong_day_rejected(self):
        with self.assertRaisesRegex(ValueError, "ledger date"):
            merge_forward_evidence(None, ledger(capture()), {}, event_date="2026-11-19",
                                   generated_at_utc="2026-11-19T02:55:00+00:00")


if __name__ == "__main__":
    unittest.main()
