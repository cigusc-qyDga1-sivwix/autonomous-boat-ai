"""Forward-only original exhibition v1 learning integration safety tests."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from boat_ai.statistical import digest
from scripts.boatcast_oriten_smoke import probe
from scripts.learned_formal import VERSION as MODEL_VERSION
from scripts.original_venue_formal_v1 import (
    POLICY_SHA256, apply, attach_to_live_race, collect_candidates,
)

MODEL = json.loads(Path("app/data/statistical/latest-model.json").read_text())
CUTOFF = "2026-11-17T12:00:00+09:00"
FROZEN = "2026-11-17T02:54:00+00:00"


def saved_capture(code="23", *, metrics=("lap_time", "turn_time", "straight_time")):
    boats = [{"lane": lane, "name": f"選手{lane}",
              **{m: (37 + lane/10 if m == "lap_time" else
                     18 + lane/10 if m == "half_lap_time" else
                     7.5 + lane/10 if m == "turn_time" else
                     7.5 + lane/100)
                 for m in metrics}}
             for lane in range(1, 7)]
    return {
        "schema": "boatlabs.boatcast_oriten_smoke.v1",
        "date": "2026-11-17", "venue_code": code, "race_number": 2,
        "status": "SIX_BOAT_PARSED_RESEARCH_ONLY",
        "source_url": f"https://race.boatcast.jp/txt/{code}/bc_oriten_20261117_{code}_02.txt",
        "captured_at_utc": "2026-11-17T02:53:00+00:00",
        "source_body_sha256": "c" * 64,
        "metrics": list(metrics), "boats": boats,
        "measurement_sha256": digest(boats),
        "research_only": True, "formal_forecast_eligible": False,
    }


def standard_race():
    return {
        "closed_at": "2026-11-17 12:00:00",
        "racers": {str(n): {"name": f"選手{n}"} for n in range(1, 7)},
        "preview": {"racers": {str(n): {
            "course_number": n,
            "start_timing": round(.12+n/100, 3),
            "exhibition_time": 6.7+n/100
        } for n in range(1, 7)}},
        "_exhibition_origin": {"source": "BoatraceOpenAPI",
                               "captured_before_cutoff": True},
    }


def formal_snapshot(venue="唐津", count=8):
    racers = [{
        "lane": i, "name": f"選手{i}", "course": i,
        "national_win_rate": 5.1 + i/10, "motor_top_2_percent": 32+i,
        "average_start_timing": .16+i/200,
        "average_start_timing_imputed": False,
        "exhibition_time": 6.7+i/100,
        "exhibition_st": .12+i/100,
    } for i in range(1, 7)]
    return {
        "model_version": MODEL_VERSION, "phase": "exhibition",
        "learned_formal": {"model_sha256": MODEL["model_sha256"],
                           "model_role": "formal_primary"},
        "venue": venue, "race": 2,
        "frozen_at_utc": FROZEN, "cutoff_iso_jst": CUTOFF,
        "racers": racers,
        "exhibition_origin": {"source":"BoatraceOpenAPI",
                              "captured_before_cutoff": True},
        "weather_used": {},
        "bets": [{"combination": combo, "virtual_yen": (6000 if idx < count-1
                 else 50000-6000*(count-1))}
                 for idx, combo in enumerate([
                     "1-2-3", "1-2-4", "1-2-5", "1-2-6",
                     "1-3-2", "1-3-4", "1-3-5", "2-1-3"][:count])],
        "point_reason": "学習済みメイン", "scenario": "学習済みメイン",
    }


class VenueOriginalFormalV1Tests(unittest.TestCase):
    def test_live_match_and_attach(self):
        c = saved_capture()
        race = attach_to_live_race(standard_race(), c, venue_code="23", race_number=2,
                                   captured_by_forecast_at_utc=FROZEN)
        self.assertEqual(len(race["_exhibition_original"]["turn_time"]), 6)
        self.assertEqual(race["_exhibition_origin"]["original_exhibition_source"], "BOATCAST_direct")

    def test_wrong_race_rejected(self):
        with self.assertRaises(ValueError):
            attach_to_live_race(standard_race(), saved_capture(), venue_code="23", race_number=3,
                                captured_by_forecast_at_utc=FROZEN)

    def test_wrong_name_rejected(self):
        c = saved_capture()
        c["boats"][0]["name"] = "別人"
        c["measurement_sha256"] = digest(c["boats"])
        with self.assertRaisesRegex(ValueError, "names disagree"):
            attach_to_live_race(standard_race(), c, venue_code="23", race_number=2,
                                captured_by_forecast_at_utc=FROZEN)

    def test_late_capture_rejected(self):
        c = saved_capture()
        c["captured_at_utc"] = "2026-11-17T02:55:00+00:00"
        with self.assertRaisesRegex(ValueError, "before eligible freeze"):
            attach_to_live_race(standard_race(), c, venue_code="23", race_number=2,
                                captured_by_forecast_at_utc=FROZEN)

    def test_venue_aware_formal_uses_control_and_preserves_budget(self):
        out = apply(formal_snapshot(), MODEL, saved_capture())
        policy = out["original_exhibition_formal_v1"]
        self.assertTrue(policy["formal_component"])
        self.assertFalse(policy["trained_coefficient"])
        self.assertEqual(policy["coefficient_policy_sha256"], POLICY_SHA256)
        self.assertEqual(policy["base_learned_model_sha256"], MODEL["model_sha256"])
        self.assertEqual(len(out["bets"]), 8)
        self.assertEqual(sum(x["virtual_yen"] for x in out["bets"]), 50000)
        self.assertEqual(len(policy["same_time_base_bets"]), 8)
        self.assertTrue(policy["no_results_or_payouts_used"])
        self.assertTrue(policy["pre_cutoff_only"])

    def test_twoway_tokuyama_no_imaginary_straight(self):
        out = apply(formal_snapshot("徳山"), MODEL,
                    saved_capture("18", metrics=("lap_time", "turn_time")))
        self.assertEqual(out["original_exhibition_formal_v1"]["metrics_complete_six_boats"],
                         ["lap_time", "turn_time"])

    def test_half_lap_kiryu_never_promoted_to_full(self):
        out = apply(formal_snapshot("桐生"), MODEL,
                    saved_capture("01", metrics=("half_lap_time", "turn_time", "straight_time")))
        self.assertIn("half_lap_time", out["original_exhibition_formal_v1"]["metrics_complete_six_boats"])
        self.assertNotIn("lap_time", out["original_exhibition_formal_v1"]["metrics_complete_six_boats"])

    def test_tamper_rejected(self):
        c = saved_capture()
        c["boats"][0]["turn_time"] = 8
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            apply(formal_snapshot(), MODEL, c)

    def test_wrong_name_rejected_before_bets(self):
        c = saved_capture()
        c["boats"][2]["name"] = "別人"
        c["measurement_sha256"] = digest(c["boats"])
        with self.assertRaisesRegex(ValueError, "names differ"):
            apply(formal_snapshot(), MODEL, c)

    def test_baseline_cannot_use_original(self):
        s = formal_snapshot()
        s["phase"] = "baseline"
        with self.assertRaisesRegex(ValueError, "eligible"):
            apply(s, MODEL, saved_capture())

    def test_collector_bounded_and_reuses_frozen(self):
        now = datetime.fromisoformat("2026-11-17T02:49:00+00:00")
        payload = {"programs":{"stadiums":{"23":{"races":{
            "2": standard_race(), "3": standard_race(), "4": standard_race()
        }}}}}
        calls = []
        def mocked(day, venue, number, timeout):
            calls.append((venue, number))
            return saved_capture()
        got, audit = collect_candidates(payload, None, now,
                                        request_limit=2, sleep_fn=lambda _:None,
                                        probe_fn=mocked)
        self.assertEqual(audit["attempted"], 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(got), 2)
        assert "23-2" in got
        previous = {"race_records":{"23-2":{"versions":[{
            "original_exhibition_formal_v1":{"formal_component":True}}]}}}
        got, audit = collect_candidates(payload, previous, now,
                                        request_limit=3,sleep_fn=lambda _:None,
                                        probe_fn=mocked)
        self.assertEqual(audit["attempted"], 2)

    def test_collector_does_not_fetch_after_cutoff(self):
        payload = {"programs":{"stadiums":{"23":{"races":{"2":standard_race()}}}}}
        got, audit = collect_candidates(
            payload,None,datetime.fromisoformat("2026-11-17T03:01:00+00:00"),
            probe_fn=lambda *a, **k: self.fail("should not fetch"))
        self.assertFalse(got)
        self.assertEqual(audit["attempted"],0)


if __name__ == "__main__":
    unittest.main()
