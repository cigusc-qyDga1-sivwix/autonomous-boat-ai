"""Unattended processing of generated footage; no real-race accuracy claim."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from scripts.mikuni_auto_vision import MODEL, analyze_automatic_frames, propose_clip_starts
from scripts.mikuni_video_ephemeral import analyze_bytes, collect, decode_in_memory

DAY = "2026-10-28"
NOW = datetime(2026, 10, 28, 0, 20, tzinfo=timezone.utc)
W, H = 480, 320
PALETTE = [(245, 245, 245), (15, 15, 15), (0, 0, 245),
           (245, 30, 0), (0, 235, 245), (20, 210, 20)]


def scene(*, count=8, camera_dx=1, boat_dx=3, background=True,
          boats=True, duplicate_red=False, static_overlay=False):
    rng = np.random.default_rng(28)
    base = np.full((H, W, 3), 112, np.uint8)
    if background:
        # Distributed, static grayscale texture, independent of the six movers.
        for y in range(36, H - 18, 32):
            for x in range(24, W - 18, 36):
                stamp = rng.integers(65, 180, (11, 11), dtype=np.uint8)
                base[y:y + 11, x:x + 11] = stamp[:, :, None]
    output = []
    for index in range(count):
        image = cv2.warpAffine(base, np.float32([[1, 0, camera_dx * index], [0, 1, index]]),
                               (W, H), borderValue=(112, 112, 112))
        if boats:
            for lane, color in enumerate(PALETTE):
                x = 65 + lane * 55 + index * (camera_dx + boat_dx)
                y = 134 + (lane % 2) * 38 + index
                cv2.rectangle(image, (x - 6, y - 5), (x + 6, y + 5), color, -1)
            if duplicate_red:
                x, y = 90 + index * (camera_dx + boat_dx), 230 + index
                cv2.rectangle(image, (x - 6, y - 5), (x + 6, y + 5), PALETTE[2], -1)
        if static_overlay:
            cv2.rectangle(image, (220, 210), (233, 223), PALETTE[3], -1)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 98])
        if not ok:
            raise RuntimeError("synthetic_jpeg_encode_failed")
        output.append(encoded.tobytes())
    return output


def archive():
    return {"event_date": DAY, "records": [{"race_code": "202610281006", "venue_code": "10",
             "race": 6, "boats": [{"lane": n} for n in range(1, 7)]}]}


def receiver(payload):
    def receive(*_):
        return payload, {"sha256": hashlib.sha256(payload).hexdigest(),
                         "file_size": len(payload), "content_type": "video/x-msvideo"}
    return receive


class AutomaticVisionTests(unittest.TestCase):
    def test_scene_is_selected_after_an_uninformative_intro_without_manual_start(self):
        ok, blank = cv2.imencode(".jpg", np.full((H, W, 3), 75, np.uint8))
        self.assertTrue(ok)
        starts = propose_clip_starts([blank.tobytes()] * 12 + scene(count=2))
        self.assertEqual(starts[0], 57.)
        self.assertLessEqual(len(starts), 3)

    def test_preview_windows_are_bounded_and_not_repeated(self):
        starts = propose_clip_starts(scene(count=40))
        self.assertLessEqual(len(starts), 3)
        self.assertTrue(all(0 <= t <= 300 for t in starts))
        self.assertTrue(all(abs(a - b) >= 24 for i, a in enumerate(starts) for b in starts[i + 1:]))

    def test_all_six_movers_without_boat_or_shore_annotations(self):
        report = analyze_automatic_frames(scene())
        self.assertEqual(report["manual_inputs_required"], 0)
        self.assertEqual(report["candidate_boat_tracks"], 6)
        self.assertTrue(report["all_six_candidates_supported"])
        self.assertGreaterEqual(report["camera_stabilized_frames"], 6)
        for boat in report["unverified_tracks"]:
            self.assertAlmostEqual(boat["median_relative_motion_px_per_s"], 6, delta=1.5)
            self.assertFalse(boat["identity_independently_verified"])
        self.assertEqual(report["confirmed_boat_tracks"], 0)
        self.assertFalse(report["water_plane_metre_calibration_confirmed"])
        self.assertFalse(report["eligible_for_formal_or_shadow_forecast"])

    def test_camera_pan_without_relative_motion_is_not_a_moving_boat(self):
        report = analyze_automatic_frames(scene(boat_dx=0))
        self.assertEqual(report["candidate_boat_tracks"], 0)

    def test_no_background_consensus_cannot_measure_relative_motion(self):
        report = analyze_automatic_frames(scene(background=False))
        self.assertEqual(report["candidate_boat_tracks"], 0)

    def test_stationary_screen_overlay_is_rejected_during_camera_pan(self):
        report = analyze_automatic_frames(scene(boats=False, static_overlay=True))
        self.assertEqual(report["candidate_boat_tracks"], 0)

    def test_multiple_same_color_objects_are_ambiguous(self):
        report = analyze_automatic_frames(scene(duplicate_red=True))
        red = next(b for b in report["unverified_tracks"] if b["lane_color_hypothesis"] == 3)
        self.assertFalse(red["candidate_accepted"])
        self.assertGreater(report["ambiguous_color_frames"], 0)

    def test_blank_and_scene_cut_do_not_invent_or_join_tracks(self):
        ok, blank = cv2.imencode(".jpg", np.full((H, W, 3), 75, np.uint8))
        self.assertTrue(ok)
        report = analyze_automatic_frames([blank.tobytes()] * 6)
        self.assertEqual(report["candidate_boat_tracks"], 0)
        cut = analyze_automatic_frames(scene(count=3) + [blank.tobytes()] + scene(count=3))
        self.assertEqual(cut["candidate_boat_tracks"], 0)
        self.assertGreater(cut["scene_segments"], 1)

    def test_invalid_image_or_interval_does_not_become_a_measurement(self):
        for images in ([], [b"invalid"]):
            with self.assertRaises(ValueError):
                analyze_automatic_frames(images)
        with self.assertRaises(ValueError):
            analyze_automatic_frames(scene(), sample_interval_s=0)

    def test_real_video_decode_to_automatic_analysis_without_any_seeds(self):
        # FFmpeg consumes concatenated synthetic JPEGs and emits AVI to RAM.
        video = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "image2pipe",
                                "-framerate", "2", "-vcodec", "mjpeg", "-i", "pipe:0",
                                "-an", "-c:v", "mjpeg", "-f", "avi", "pipe:1"],
                               input=b"".join(scene()), capture_output=True, timeout=15, check=True).stdout
        decoded = decode_in_memory(video)
        self.assertGreaterEqual(len(decoded), 6)
        report = analyze_bytes(video)
        self.assertEqual(report["manual_inputs_required"], 0)
        auto = report["automatic_tracking_candidate"]
        self.assertEqual(auto["candidate_boat_tracks"], 6)
        self.assertEqual(auto["model"], MODEL)
        self.assertEqual(report["confirmed_boat_tracks"], 0)

    def test_collection_runs_automatic_without_seed_file_and_is_idempotent(self):
        payload = b"RIFF" + b"\0" * 4 + b"AVI " + b"synthetic"
        inputs = (DAY, archive(), None, "https://approved.provider.example/{race2}.avi",
                  ["approved.provider.example"])
        with patch("scripts.mikuni_video_ephemeral.decode_in_memory", return_value=scene()):
            report = collect(*inputs, receiver=receiver(payload), now=NOW)
        self.assertEqual(report["summary"]["automatic_candidate_races"], 1)
        self.assertEqual(report["summary"]["automatic_six_candidate_races"], 1)
        self.assertEqual(report["summary"]["confirmed_boat_tracks"], 0)
        repeated = collect(DAY, archive(), report, inputs[3], inputs[4], now=NOW,
                           receiver=lambda *_: self.fail("duplicate download"))
        self.assertEqual(report["races"], repeated["races"])
        self.assertNotIn("approved.provider.example", json.dumps(report))

    def test_upgrade_reprocesses_same_source_once_and_preserves_on_source_change(self):
        payload = b"RIFF" + b"\0" * 4 + b"AVI " + b"synthetic"
        old = {"schema": "boatlabs.mikuni_authorized_video_ingestion.v1", "event_date": DAY,
               "races": {"6": {"status": "MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY",
                                "source_sha256": hashlib.sha256(payload).hexdigest(),
                                "video_observation": {"seeded_tracking_status": "NO_SIX_BOAT_SEEDS"}}}}
        saved = copy.deepcopy(old)
        with patch("scripts.mikuni_video_ephemeral.decode_in_memory", return_value=scene()):
            upgraded = collect(DAY, archive(), old, "https://approved.provider.example/{race2}.avi",
                               ["approved.provider.example"], receiver=receiver(payload), now=NOW)
        self.assertEqual(upgraded["summary"]["automatic_six_candidate_races"], 1)
        changed = collect(DAY, archive(), old, "https://approved.provider.example/{race2}.avi",
                          ["approved.provider.example"], receiver=receiver(payload + b"changed"), now=NOW)
        self.assertEqual(changed["races"]["6"]["source_sha256"], old["races"]["6"]["source_sha256"])
        self.assertEqual(changed["races"]["6"]["analysis_reprocess_status"], "VIDEO_SOURCE_SHA_CHANGED_NO_REPROCESS")
        self.assertEqual(old, saved)

    def test_no_source_means_no_automatic_success(self):
        report = collect(DAY, archive(), None, None, [], now=NOW,
                         receiver=lambda *_: self.fail("unconfigured source accessed"))
        self.assertEqual(report["summary"]["automatic_candidate_races"], 0)
        self.assertEqual(report["input_connection_status"], "DIRECT_MEDIA_SOURCE_REQUIRED")


if __name__ == "__main__":
    unittest.main()
