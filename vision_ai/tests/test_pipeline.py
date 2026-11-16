"""Status, provenance and storage regression checks; no CV dependency."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from vision_ai.pipeline import MANIFEST_SCHEMA, _simultaneous, run
from vision_ai.report_io import write_report


def manifest():
    return {"schema": MANIFEST_SCHEMA, "event_date": "2026-11-03", "venue_code": "10",
            "race": 1, "source_kind": "synthetic_test", "permission_reference": "self-created-test"}


class PipelineTests(unittest.TestCase):
    def test_missing_source_is_not_success_or_network_access(self):
        with patch("vision_ai.pipeline.receive_approved_video") as receive:
            result = run(manifest())
        receive.assert_not_called()
        self.assertEqual(result["status"], "NO_SOURCE_CONFIGURED")
        self.assertFalse(any(result["stages"].values()))
        self.assertFalse(result["eligible_for_formal_forecast"])
        self.assertEqual(result["confirmed_boat_tracks"], 0)

    def test_digest_mismatch_never_decodes_or_leaks_input(self):
        src = manifest()
        src["expected_sha256"] = "a" * 64
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "private-input.mp4"
            video.write_bytes(b"not-the-approved-source")
            with patch("vision_ai.pipeline.decode_in_memory") as decoder:
                result = run(src, video_file=video)
        decoder.assert_not_called()
        self.assertEqual(result["status"], "SOURCE_DIGEST_MISMATCH")
        self.assertTrue(result["stages"]["media_received"])
        self.assertFalse(result["stages"]["frames_decoded"])
        self.assertNotIn("private-input", str(result))

    def test_http_failure_and_decode_failure_have_separate_stages(self):
        secret_url = "https://authorized.example/video?secret=private"
        with patch("vision_ai.pipeline.receive_approved_video",
                   side_effect=HTTPError(secret_url, 403, "secret", None, None)):
            result = run(manifest(), video_url=secret_url, allowed_hosts=("authorized.example",))
        self.assertEqual(result["status"], "SOURCE_HTTP_ERROR")
        self.assertEqual(result["http_status"], 403)
        self.assertNotIn("secret", str(result))
        with patch("vision_ai.pipeline.receive_approved_video", return_value=(b"bad", {})), \
             patch("vision_ai.pipeline.decode_in_memory", side_effect=ValueError("private content")):
            result = run(manifest(), video_url=secret_url)
        self.assertEqual(result["status"], "DECODE_UNAVAILABLE_OR_INVALID")
        self.assertTrue(result["stages"]["media_received"])
        self.assertFalse(result["stages"]["frames_decoded"])
        self.assertEqual(result["source_sha256"], hashlib.sha256(b"bad").hexdigest())
        self.assertNotIn("private", str(result))

    def test_bad_manifest_fields_and_timezone_are_rejected(self):
        for key, value in (("race", True), ("event_date", "2026-11-31"),
                           ("permission_reference", ""), ("expected_sha256", "x" * 64),
                           ("source_kind", "official_verified"), ("odds", {})):
            item = manifest()
            item[key] = value
            with self.assertRaises(ValueError, msg=key):
                run(item)
        with self.assertRaisesRegex(ValueError, "timezone"):
            run(manifest(), now=datetime(2026, 11, 3))
        src = manifest()
        original = deepcopy(src)
        run(src, now=datetime(2026, 11, 3, tzinfo=timezone.utc))
        self.assertEqual(src, original)

    def test_output_is_atomic_and_blocks_production_and_input_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "manifest.json"
            source.write_text("original")
            for name in ("app/data/exhibition/a.json", "live/a.json", "results/a.json"):
                with self.assertRaisesRegex(ValueError, "production"):
                    write_report({}, base / name)
                self.assertFalse((base / name).exists())
            link = base / "link.json"
            link.symlink_to(source)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                write_report({}, link, inputs=(source,))
            write_report({"status": "numeric-only"}, base / "research/report.json")
            self.assertEqual(source.read_text(), "original")
            self.assertEqual(len(list((base / "research").iterdir())), 1)

    def test_six_disjoint_or_stationary_tracks_are_not_simultaneous(self):
        def track(lane, start=0, moving=True):
            return {"candidate_accepted": True, "samples": [
                {"frame": i, "segment": 0, "chain": 0,
                 "center_px": [40 * lane + (i if moving else 0), 100],
                 "camera_stabilized_center_px": [40 * lane + (i if moving else 0), 100]}
                for i in range(start, start + 6)]}
        self.assertEqual(_simultaneous({"unverified_tracks": [track(i) for i in range(6)]}), 6)
        self.assertEqual(_simultaneous({"unverified_tracks": [track(i, i * 6) for i in range(6)]}), 0)
        self.assertEqual(_simultaneous({"unverified_tracks": [track(i, moving=False) for i in range(6)]}), 0)

    def test_scene_or_identity_chain_restart_does_not_join_continuity(self):
        for changed_field in ("segment", "chain"):
            tracks = [{"candidate_accepted": True, "samples": [
                {"frame": i, "segment": 0, "chain": 0,
                 "center_px": [40 * lane + i, 100],
                 "camera_stabilized_center_px": [40 * lane + i, 100]}
                for i in range(8)]} for lane in range(6)]
            for track in tracks:
                for sample in track["samples"][4:]:
                    sample[changed_field] = 1
            self.assertEqual(_simultaneous({"unverified_tracks": tracks}), 4)

    def test_missing_source_cli_writes_status_and_returns_nonzero(self):
        import contextlib
        import io
        import json
        from vision_ai.pipeline import main
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "manifest.json"
            output = Path(folder) / "research/status.json"
            source.write_text(json.dumps(manifest()))
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["--manifest", str(source), "--output", str(output)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.read_text())["status"], "NO_SOURCE_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
