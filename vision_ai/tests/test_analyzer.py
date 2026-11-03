"""Contract tests: the independent video AI can run without BOAT LAB modules."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from vision_ai import analyze, OUTPUT_SCHEMA


def tracker():
    tracks = []
    for lane in range(1, 7):
        points = [
            {
                "frame": j,
                "t_seconds": j * .5,
                "camera_stabilized_center_px": [80 + 20*lane + j*(2+lane), 100+10*lane],
                "identity_verified": False,
            }
            for j in range(6)
        ]
        tracks.append({
            "lane_seed_label": lane,
            "samples": points,
            "id_independently_verified": False,
            "coverage_ratio": 1.0,
        })
    return {
        "schema": "boatlabs.mikuni_seeded_six_boat_pixel_tracks.v0.1",
        "status": "UNVERIFIED_CAMERA_STABILIZED_SIX_SEED_CANDIDATES",
        "venue_code": "10",
        "event_date": "2026-11-03",
        "race": 1,
        "source_sha256": "a" * 64,
        "frames_seen": 6,
        "camera_stabilized_frames": 6,
        "unverified_tracks": tracks,
        "confirmed_boat_tracks": 0,
        "approved_verified_track_ledger_created": False,
        "eligible_for_formal_or_shadow_forecast": False,
    }


class IndependentVisionTests(unittest.TestCase):
    def test_six_boat_pixel_motion_is_research_only(self):
        src = tracker()
        old = deepcopy(src)
        result = analyze(src, analyzed_at_utc=datetime(2026,11,3,0,30,tzinfo=timezone.utc))
        self.assertEqual(src, old)
        self.assertEqual(result["schema"], OUTPUT_SCHEMA)
        self.assertEqual(result["event_date"], src["event_date"])
        self.assertEqual(result["race"], 1)
        self.assertEqual(len(result["six_seed_motion_candidates"]), 6)
        self.assertEqual(result["six_seed_motion_candidates"][0]["median_apparent_motion_px_per_s"], 6.0)
        self.assertEqual(result["six_seed_motion_candidates"][0]["late_to_early_pixel_motion_ratio"], 1.0)
        self.assertFalse(result["eligible_for_formal_forecast"])
        self.assertFalse(result["eligible_for_shadow_forecast"])
        self.assertFalse(result["video_identity_verified"])
        self.assertFalse(result["official_results_used"])
        self.assertEqual(result["bets_generated"], 0)
        self.assertEqual(len(result["report_sha256"]), 64)
        self.assertFalse(any(x in str(result).lower() for x in ("payout", "winning_bet", "3連単")))

    def test_no_result_or_odds_leakage(self):
        for injected in ({"result": {"finish": "1-2-3"}},
                         {"payout": 1000}, {"odds": {"1-2-3": 12}}):
            src = tracker()
            src.update(injected)
            with self.assertRaisesRegex(ValueError, "postrace_or_betting_field_forbidden"):
                analyze(src)

    def test_bad_identity_is_not_promoted(self):
        src = tracker()
        src["unverified_tracks"][0]["id_independently_verified"] = True
        with self.assertRaisesRegex(ValueError, "unsupported_identity_verification"):
            analyze(src)
        src = tracker()
        src["approved_verified_track_ledger_created"] = True
        with self.assertRaisesRegex(ValueError, "verified_tracker_claim_not_supported"):
            analyze(src)

    def test_missing_or_duplicate_six_tracks_rejected(self):
        src = tracker()
        src["unverified_tracks"] = src["unverified_tracks"][:5]
        with self.assertRaisesRegex(ValueError, "six_tracks_required"):
            analyze(src)
        src = tracker()
        src["unverified_tracks"][-1]["lane_seed_label"] = 1
        with self.assertRaisesRegex(ValueError, "duplicate_or_invalid_seed_label"):
            analyze(src)

    def test_nonfinite_and_disordered_positions_rejected(self):
        src = tracker()
        src["unverified_tracks"][0]["samples"][2]["camera_stabilized_center_px"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "non_finite_motion_measurement"):
            analyze(src)
        src = tracker()
        src["unverified_tracks"][0]["samples"][3]["frame"] = 2
        with self.assertRaisesRegex(ValueError, "invalid_frame_order"):
            analyze(src)

    def test_invalid_day_or_non_mikuni_not_accepted(self):
        src = tracker()
        src["venue_code"] = "01"
        with self.assertRaisesRegex(ValueError, "unverified_mikuni_tracker_required"):
            analyze(src)
        src = tracker()
        src["event_date"] = "2026-11-31"
        with self.assertRaisesRegex(ValueError, "unverified_mikuni_tracker_required"):
            analyze(src)

    def test_no_guessed_source_capture_time_or_real_world_units(self):
        r = analyze(tracker())
        self.assertNotIn("captured_at_utc", r)
        self.assertNotIn("speed_mps", str(r))
        self.assertNotIn("cutoff", str(r))


if __name__ == "__main__":
    unittest.main()
