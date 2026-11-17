"""Forward-only original exhibition v1 learning integration safety tests."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from boat_ai.statistical import digest, distributions
from scripts.boatcast_oriten_smoke import probe
from scripts.learned_formal import VERSION as MODEL_VERSION, apply as apply_learned_primary
from scripts.original_exhibition_venue_research import VENUE_SPECS
from scripts.original_venue_formal_v1 import (
    POLICY_SHA256, PROFILE_DATA, adjust_rankings, apply, attach_to_live_race, collect_candidates,
)

MODEL_SHA = "45535951091f1baad38fe810b3bd5b106bdf0fd80c525ff6bbc7a948e6fd88c8"
MODEL = json.loads((Path("app/data/statistical/models") / f"{MODEL_SHA}.json").read_text())
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
        self.assertTrue(policy["trained_coefficient"])
        self.assertEqual(policy["coefficient_policy_sha256"], POLICY_SHA256)
        self.assertEqual(policy["base_learned_model_sha256"], MODEL["model_sha256"])
        self.assertEqual(len(out["bets"]), 8)
        self.assertEqual(sum(x["virtual_yen"] for x in out["bets"]), 50000)
        self.assertEqual(len(policy["same_time_base_bets"]), 8)
        self.assertTrue(policy["no_results_or_payouts_used"])
        self.assertTrue(policy["pre_cutoff_only"])

    def test_corner_guard_from_today_preserves_budget_without_double_boost(self):
        source = formal_snapshot()
        # Immutable Nov-16-trained model stays valid for Nov-18 forward inference.
        today_model_sha = "0fdc5cacba60dd9af6e1d1cb562b7a868644e99922662298ac3cd62c7572dc96"
        today_model = json.loads((Path("app/data/statistical/models") / f"{today_model_sha}.json").read_text())
        source["frozen_at_utc"] = "2026-11-18T02:54:00+00:00"
        source["cutoff_iso_jst"] = "2026-11-18T12:00:00+09:00"
        source["learned_formal"]["model_sha256"] = today_model["model_sha256"]
        original_capture = saved_capture()
        original_capture["date"] = "2026-11-18"
        original_capture["source_url"] = original_capture["source_url"].replace("20261117", "20261118")
        original_capture["captured_at_utc"] = "2026-11-18T02:53:00+00:00"
        r = source["racers"]
        r[2]["exhibition_st"], r[3]["exhibition_st"], r[4]["exhibition_st"] = .18, .12, .13
        r[2]["exhibition_time"], r[3]["exhibition_time"], r[4]["exhibition_time"] = 6.76, 6.73, 6.74
        r[2]["average_start_timing"], r[3]["average_start_timing"], r[4]["average_start_timing"] = .17, .15, .16
        learned = apply_learned_primary(source, today_model)
        self.assertTrue(learned["corner_attack_formal_v1"]["applied"])
        self.assertEqual(sum(x["virtual_yen"] for x in learned["bets"]), 50000)
        direct_original = apply(source, today_model, original_capture)
        enriched_original = apply(learned, today_model, original_capture)
        self.assertEqual(direct_original["bets"], enriched_original["bets"])
        self.assertEqual(enriched_original["original_exhibition_formal_v1"]["same_time_base_bets"],
                         learned["bets"])
        self.assertTrue(enriched_original["corner_attack_formal_v1"]["applied"])
        self.assertEqual(sum(x["virtual_yen"] for x in enriched_original["bets"]), 50000)
        self.assertIn("corner_guard_policy_sha256",
                      enriched_original["original_exhibition_formal_v1"])

    def test_all_23_venue_profiles_use_only_their_own_measurement_contract(self):
        profiles = PROFILE_DATA["venues"]
        self.assertEqual(set(profiles), set(VENUE_SPECS) - {"03"})
        self.assertEqual(sum(p["training_races"] for p in profiles.values()), PROFILE_DATA["training_races"])
        for code, profile in profiles.items():
            with self.subTest(venue=code):
                self.assertEqual(tuple(profile["metrics"]), VENUE_SPECS[code]["expected_metrics"])
                self.assertEqual(len(profile["weights"]), 3)
                for weights, cap in zip(profile["weights"], PROFILE_DATA["stage_logit_caps"]):
                    self.assertEqual(len(weights), len(profile["metrics"]))
                    self.assertTrue(all(0 <= weight <= cap for weight in weights))
                    self.assertLessEqual(sum(weights), cap + 0.0001)

    def test_same_measurements_rank_differently_by_venue(self):
        karatsu = apply(formal_snapshot(), MODEL, saved_capture())
        omura = apply(formal_snapshot("大村"), MODEL, saved_capture("24"))
        for out in (karatsu, omura):
            self.assertAlmostEqual(sum(x["relative_share"] for x in out["head_course_shares"]), 1)
            self.assertEqual(len(out["bets"]), 8)
            self.assertEqual(sum(b["virtual_yen"] for b in out["bets"]), 50000)
        self.assertEqual(karatsu["original_exhibition_formal_v1"]["profile_stage_weights"]["first"],
                         {"turn_time": 0.08})
        self.assertIn("lap_time", omura["original_exhibition_formal_v1"]["profile_stage_weights"]["first"])
        self.assertNotEqual(karatsu["head_course_shares"], omura["head_course_shares"])

    def test_third_place_changes_do_not_move_the_first_second_pair(self):
        base = distributions(formal_snapshot(), MODEL)
        values = {"turn_time": {str(lane): {"advantage_over_race_median_seconds": lane / 100}
                                for lane in range(1, 7)}}
        adjusted = adjust_rankings(base, values, {"first": {}, "second": {}, "third": {"turn_time": 0.05}})
        choices = {r["combination"][:3] for r in base}
        for pair in choices:
            self.assertAlmostEqual(
                sum(r["score"] for r in base if r["combination"].startswith(pair)),
                sum(r["score"] for r in adjusted if r["combination"].startswith(pair)),
            )
        self.assertNotEqual({r["combination"]: r["score"] for r in base},
                            {r["combination"]: r["score"] for r in adjusted})

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
