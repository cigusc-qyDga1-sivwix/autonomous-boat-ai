"""Safeguards for BOAT LAB's pre-cutoff relative wind research shadow."""
import copy
import itertools
import unittest

from scripts.relative_wind_shadow import directional_signal, rescore


def canonical():
    keys = ["-".join(map(str, p)) for p in itertools.permutations(range(1, 7), 3)]
    raw = [1 / (k + 7) for k in range(len(keys))]
    return [{"combination": key, "relative_score": v / sum(raw)}
            for key, v in zip(keys, raw)]


def racers():
    return [{"lane": i, "course": i, "exhibition_st": .13 + i * .01}
            for i in range(1, 7)]


def weather(code, speed=5):
    return {"site_observed": True, "wind_source": "boatrace_preview",
            "wind_direction_number": code, "wind_speed": speed}


def by_combo(rows, combination):
    return next(row["relative_score"] for row in rows
                if row["combination"] == combination)


class RelativeWindShadowTests(unittest.TestCase):
    def test_api_direction_codes_already_relative_all_venues(self):
        for code in (3, 4, 5, 6, 7):
            self.assertEqual(directional_signal(weather(code))["relative_wind"], "tailwind")
        for code in (11, 12, 13, 14, 15):
            self.assertEqual(directional_signal(weather(code))["relative_wind"], "headwind")
        for code in (1, 2, 8, 9, 10, 16, 17):
            self.assertIsNone(directional_signal(weather(code)))

    def test_source_and_speed_fail_closed(self):
        self.assertIsNone(directional_signal({"wind_speed": 6, "wind_direction_number": 5,
                                               "site_observed": False, "wind_source": "open-meteo"}))
        self.assertIsNone(directional_signal(weather(5, 1.9)))
        self.assertIsNone(directional_signal(weather(5.5)))
        self.assertIsNone(directional_signal(weather(True)))
        self.assertIsNone(directional_signal(weather(5, 66)))
        self.assertIsNone(directional_signal(weather(5, float("nan"))))
        self.assertIsNone(directional_signal({**weather(5), "wind_source": "jma_grid"}))

    def test_shadow_reweights_in_expected_direction_and_preserves_control(self):
        control = canonical()
        original = copy.deepcopy(control)
        tail = rescore(control, racers(), weather(5, 6))
        head = rescore(control, racers(), weather(13, 6))
        self.assertEqual(control, original)
        self.assertTrue(tail["same_pre_cutoff_inputs"])
        self.assertFalse(tail["formal_bets_changed"])
        self.assertFalse(tail["calibrated"])
        self.assertEqual(len(tail["outcomes"]), 120)
        self.assertAlmostEqual(sum(x["relative_score"] for x in tail["outcomes"]), 1)
        self.assertAlmostEqual(sum(x["relative_score"] for x in head["outcomes"]), 1)
        # Ratios cancel the common normalization.
        tail_ratio = (by_combo(tail["outcomes"], "2-1-3") /
                      by_combo(tail["outcomes"], "1-4-3"))
        old_ratio = by_combo(control, "2-1-3") / by_combo(control, "1-4-3")
        self.assertGreater(tail_ratio, old_ratio)
        head_ratio = (by_combo(head["outcomes"], "4-5-1") /
                      by_combo(head["outcomes"], "1-5-4"))
        old_head_ratio = by_combo(control, "4-5-1") / by_combo(control, "1-5-4")
        self.assertGreater(head_ratio, old_head_ratio)

    def test_course_not_frame_and_exhibition_f_not_bonus(self):
        shifted = racers()
        shifted[0]["course"], shifted[1]["course"] = 2, 1
        control = canonical()
        trial = rescore(control, shifted, weather(5, 6))
        ref = rescore(control, racers(), weather(5, 6))
        # Course-2 head now belongs to frame 1 instead of frame 2.
        self.assertNotEqual(by_combo(trial["outcomes"], "1-2-3"),
                            by_combo(ref["outcomes"], "1-2-3"))
        f = racers()
        f[1]["exhibition_st"] = -.09
        alt = rescore(control, f, weather(5, 6))
        self.assertLess(by_combo(alt["outcomes"], "2-1-3") /
                        by_combo(alt["outcomes"], "1-4-3"),
                        by_combo(ref["outcomes"], "2-1-3") /
                        by_combo(ref["outcomes"], "1-4-3"))

    def test_pipeline_frozen_wind_shadow_without_formal_ticket_mutation(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from scripts.autonomous_daily import prediction, stable_hash

        day = "2026-11-22"
        sample = {
            "closed_at": day + " 11:00:00",
            "racers": {str(i): {
                "name": "選手" + str(i),
                "national_win_rate": 5.2, "motor_top_2_percent": 32,
                "average_start_timing": .16
            } for i in range(1, 7)},
            "preview": {
                "wind_speed": 6, "wind_direction_number": 5, "wave_height": 3,
                "racers": {str(i): {
                    "course_number": i, "start_timing": .12 + i * .01,
                    "exhibition_time": 6.8 - i * .01
                } for i in range(1, 7)},
            },
        }
        now = datetime(2026, 11, 22, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        snap = prediction(sample, "徳山", 1, "exhibition", now, "test-source")
        audit = snap["relative_wind_shadow"]
        self.assertEqual(audit["status"], "RESEARCH_SHADOW", audit)
        self.assertEqual(audit["signal"]["relative_wind"], "tailwind")
        self.assertTrue(audit["not_part_of_formal_performance"])
        self.assertTrue(audit["formal_bets_unchanged"])
        self.assertEqual(sum(b["virtual_yen"] for b in snap["bets"]), 50_000)
        self.assertEqual(sum(b["virtual_yen"] for b in audit["forecast_alternative_bets"]), 50_000)
        self.assertEqual(snap["sha256"], stable_hash({
            k: v for k, v in snap.items() if k != "sha256"
        }))

    def test_invalid_actual_entry_or_outcomes_rejected(self):
        bad = racers()
        bad[1]["course"] = 1
        with self.assertRaises(ValueError):
            rescore(canonical(), bad, weather(5))
        with self.assertRaises(ValueError):
            rescore(canonical()[:119], racers(), weather(5))
        dup = canonical()
        dup[-1] = dict(dup[0])
        with self.assertRaises(ValueError):
            rescore(dup, racers(), weather(5))


if __name__ == "__main__":
    unittest.main()
