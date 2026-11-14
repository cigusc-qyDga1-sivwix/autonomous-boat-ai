"""Real decoder/CV execution on generated video; no actual race footage."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_tracking import scene, W, H
from vision_ai.evaluation import LABEL_SCHEMA, evaluate
from vision_ai.pipeline import MANIFEST_SCHEMA, run


def make_video(images):
    return subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "image2pipe",
        "-framerate", "2", "-vcodec", "mjpeg", "-i", "pipe:0", "-an", "-c:v", "mjpeg",
        "-threads", "1", "-f", "avi", "pipe:1"],
        input=b"".join(images), capture_output=True, timeout=15, check=True).stdout


class MediaIntegrationTests(unittest.TestCase):
    def test_synthetic_video_to_six_candidates_and_independent_geometric_labels(self):
        video = make_video(scene())
        manifest = {"schema": MANIFEST_SCHEMA, "event_date": "2026-11-03", "venue_code": "10",
                    "race": 1, "source_kind": "synthetic_test", "permission_reference": "generated-by-test",
                    "expected_sha256": hashlib.sha256(video).hexdigest()}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "generated.avi"
            source.write_bytes(video)
            report = run(manifest, video_file=source)
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["generated.avi"])
        self.assertEqual(report["status"], "AUTOMATIC_CANDIDATES_UNVERIFIED")
        self.assertTrue(all(report["stages"].values()))
        self.assertEqual(report["frame_size"], {"width": W, "height": H})
        self.assertEqual(report["tracking"]["candidate_boat_tracks"], 6)
        self.assertGreaterEqual(report["longest_simultaneous_six_candidate_run_frames"], 6)
        self.assertEqual(report["raw_media_bytes_persisted"], 0)
        self.assertFalse(report["real_footage_independently_verified"])
        self.assertFalse(report["eligible_for_formal_forecast"])
        labels = {"schema": LABEL_SCHEMA,
                  **{k: report[k] for k in ("source_sha256", "event_date", "venue_code", "race",
                     "declared_source_kind", "clip_start_seconds", "frame_size")},
                  "sample_interval_s": .5, "annotation_origin": "independent_manual_review",
                  "reviewer_reference": "analytic-scene-generator-ground-truth",
                  "frames": [{"frame": i, "boats": [
                      {"boat_id": lane + 1, "visible": True,
                       "center_px": [65 + lane * 55 + i * 4, 134 + (lane % 2) * 38 + i]}
                      for lane in range(6)]} for i in range(report["tracking"]["sampled_frames"])]}
        accuracy = evaluate(report, labels, radius_px=5)
        self.assertEqual(accuracy["correct_identity_recall"], 1)
        self.assertEqual(accuracy["identity_confusions"], 0)
        self.assertLess(accuracy["p95_correct_position_error_px"], 2)
        self.assertFalse(accuracy["real_footage_independently_verified"])

    def test_decodable_camera_pan_without_boats_cannot_mean_six_tracked_boats(self):
        video = make_video(scene(boats=False))
        manifest = {"schema": MANIFEST_SCHEMA, "event_date": "2026-11-03", "venue_code": "10",
                    "race": 2, "source_kind": "synthetic_test", "permission_reference": "generated-by-test"}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "background.avi"
            source.write_bytes(video)
            report = run(manifest, video_file=source)
        self.assertTrue(report["stages"]["frames_decoded"])
        self.assertTrue(report["stages"]["automatic_tracking_computed"])
        self.assertFalse(report["stages"]["six_candidates_simultaneous"])
        self.assertEqual(report["status"], "NO_SUPPORTED_TRACK_CANDIDATES")
        self.assertEqual(report["confirmed_boat_tracks"], 0)


if __name__ == "__main__":
    unittest.main()
