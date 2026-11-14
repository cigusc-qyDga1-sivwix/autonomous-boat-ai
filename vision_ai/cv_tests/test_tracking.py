"""Reused generated-scene regressions; these are NOT real footage validation."""
import cv2
import numpy as np
import unittest
from vision_ai.tracking import analyze_automatic_frames, propose_clip_starts

W, H = (480, 320)
PALETTE = [(245, 245, 245), (15, 15, 15), (0, 0, 245), (245, 30, 0), (0, 235, 245), (20, 210, 20)]

def scene(*, count=8, camera_dx=1, boat_dx=3, background=True, boats=True, duplicate_red=False, static_overlay=False):
    rng = np.random.default_rng(28)
    base = np.full((H, W, 3), 112, np.uint8)
    if background:
        for y in range(36, H - 18, 32):
            for x in range(24, W - 18, 36):
                stamp = rng.integers(65, 180, (11, 11), dtype=np.uint8)
                base[y:y + 11, x:x + 11] = stamp[:, :, None]
    output = []
    for index in range(count):
        image = cv2.warpAffine(base, np.float32([[1, 0, camera_dx * index], [0, 1, index]]), (W, H), borderValue=(112, 112, 112))
        if boats:
            for lane, color in enumerate(PALETTE):
                x = 65 + lane * 55 + index * (camera_dx + boat_dx)
                y = 134 + lane % 2 * 38 + index
                cv2.rectangle(image, (x - 6, y - 5), (x + 6, y + 5), color, -1)
            if duplicate_red:
                x, y = (90 + index * (camera_dx + boat_dx), 230 + index)
                cv2.rectangle(image, (x - 6, y - 5), (x + 6, y + 5), PALETTE[2], -1)
        if static_overlay:
            cv2.rectangle(image, (220, 210), (233, 223), PALETTE[3], -1)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 98])
        if not ok:
            raise RuntimeError('synthetic_jpeg_encode_failed')
        output.append(encoded.tobytes())
    return output

class TrackingTests(unittest.TestCase):

    def test_scene_is_selected_after_an_uninformative_intro_without_manual_start(self):
        ok, blank = cv2.imencode('.jpg', np.full((H, W, 3), 75, np.uint8))
        self.assertTrue(ok)
        starts = propose_clip_starts([blank.tobytes()] * 12 + scene(count=2))
        self.assertEqual(starts[0], 57.0)
        self.assertLessEqual(len(starts), 3)

    def test_preview_windows_are_bounded_and_not_repeated(self):
        starts = propose_clip_starts(scene(count=40))
        self.assertLessEqual(len(starts), 3)
        self.assertTrue(all((0 <= t <= 300 for t in starts)))
        self.assertTrue(all((abs(a - b) >= 24 for i, a in enumerate(starts) for b in starts[i + 1:])))

    def test_all_six_movers_without_boat_or_shore_annotations(self):
        report = analyze_automatic_frames(scene())
        self.assertEqual(report['manual_inputs_required'], 0)
        self.assertEqual(report['candidate_boat_tracks'], 6)
        self.assertTrue(report['all_six_candidates_supported'])
        self.assertGreaterEqual(report['camera_stabilized_frames'], 6)
        for boat in report['unverified_tracks']:
            self.assertAlmostEqual(boat['median_relative_motion_px_per_s'], 6, delta=1.5)
            self.assertFalse(boat['identity_independently_verified'])
        self.assertEqual(report['confirmed_boat_tracks'], 0)
        self.assertFalse(report['water_plane_metre_calibration_confirmed'])
        self.assertFalse(report['eligible_for_formal_or_shadow_forecast'])

    def test_camera_pan_without_relative_motion_is_not_a_moving_boat(self):
        report = analyze_automatic_frames(scene(boat_dx=0))
        self.assertEqual(report['candidate_boat_tracks'], 0)

    def test_no_background_consensus_cannot_measure_relative_motion(self):
        report = analyze_automatic_frames(scene(background=False))
        self.assertEqual(report['candidate_boat_tracks'], 0)

    def test_stationary_screen_overlay_is_rejected_during_camera_pan(self):
        report = analyze_automatic_frames(scene(boats=False, static_overlay=True))
        self.assertEqual(report['candidate_boat_tracks'], 0)

    def test_multiple_same_color_objects_are_ambiguous(self):
        report = analyze_automatic_frames(scene(duplicate_red=True))
        red = next((b for b in report['unverified_tracks'] if b['lane_color_hypothesis'] == 3))
        self.assertFalse(red['candidate_accepted'])
        self.assertGreater(report['ambiguous_color_frames'], 0)

    def test_blank_and_scene_cut_do_not_invent_or_join_tracks(self):
        ok, blank = cv2.imencode('.jpg', np.full((H, W, 3), 75, np.uint8))
        self.assertTrue(ok)
        report = analyze_automatic_frames([blank.tobytes()] * 6)
        self.assertEqual(report['candidate_boat_tracks'], 0)
        cut = analyze_automatic_frames(scene(count=3) + [blank.tobytes()] + scene(count=3))
        self.assertEqual(cut['candidate_boat_tracks'], 0)
        self.assertGreater(cut['scene_segments'], 1)

    def test_invalid_image_or_interval_does_not_become_a_measurement(self):
        for images in ([], [b'invalid']):
            with self.assertRaises(ValueError):
                analyze_automatic_frames(images)
        with self.assertRaises(ValueError):
            analyze_automatic_frames(scene(), sample_interval_s=0)
