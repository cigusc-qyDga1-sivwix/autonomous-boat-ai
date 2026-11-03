"""Analytic accuracy checks: swaps, omissions, occlusions and source mismatch."""
from copy import deepcopy
import unittest

from vision_ai.evaluation import LABEL_SCHEMA, evaluate
from vision_ai.pipeline import SCHEMA, _numeric_hash


def seal(run):
    run.pop("report_sha256", None)
    run["report_sha256"] = _numeric_hash(run)
    return run


def examples():
    metadata = {"source_sha256": "a" * 64, "event_date": "2026-11-03", "venue_code": "10",
                "race": 1, "declared_source_kind": "synthetic_test", "clip_start_seconds": 0.,
                "frame_size": {"width": 480, "height": 320}}
    tracks = [{"lane_color_hypothesis": lane, "identity_independently_verified": False,
               "samples": [{"frame": i, "t_s": i * .5,
                            "center_px": [40 + 60 * (lane - 1) + i * 2, 150]}
                           for i in range(6)]} for lane in range(1, 7)]
    run = seal({"schema": SCHEMA, **metadata, "eligible_for_formal_forecast": False,
                "eligible_for_shadow_forecast": False, "confirmed_boat_tracks": 0,
                "stages": {"automatic_tracking_computed": True},
                "tracking": {"sample_interval_s": .5, "sampled_frames": 6, "unverified_tracks": tracks}})
    labels = {"schema": LABEL_SCHEMA, **deepcopy(metadata), "sample_interval_s": .5,
              "annotation_origin": "independent_manual_review", "reviewer_reference": "test-author",
              "frames": [{"frame": i, "boats": [{"boat_id": lane, "visible": True,
                         "center_px": [40 + 60 * (lane - 1) + i * 2, 150]}
                        for lane in range(1, 7)]} for i in range(6)]}
    return run, labels


class EvaluationTests(unittest.TestCase):
    def test_perfect_synthetic_is_never_real_footage_verification(self):
        run, labels = examples()
        before = deepcopy((run, labels))
        report = evaluate(run, labels)
        self.assertEqual((run, labels), before)
        self.assertEqual(report["correct_identity_recall"], 1)
        self.assertEqual(report["all_six_correct_frames"], 6)
        self.assertEqual(report["median_correct_position_error_px"], 0)
        self.assertFalse(report["real_footage_independently_verified"])
        self.assertFalse(report["eligible_for_shadow_forecast"])
        self.assertEqual(report["bets_generated"], 0)

    def test_id_swaps_are_not_hidden_by_same_label_matching(self):
        run, labels = examples()
        tracks = run["tracking"]["unverified_tracks"]
        tracks[0]["samples"], tracks[1]["samples"] = tracks[1]["samples"], tracks[0]["samples"]
        report = evaluate(seal(run), labels)
        self.assertEqual(report["spatial_recall"], 1)
        self.assertEqual(report["identity_confusions"], 12)
        self.assertAlmostEqual(report["correct_identity_recall"], 2 / 3)
        self.assertEqual(report["confusion_matrix_hypothesis_by_label"][0][1], 6)
        self.assertEqual(report["all_six_correct_frames"], 0)

    def test_missed_boat_and_occluded_labels_have_correct_denominators(self):
        run, labels = examples()
        run["tracking"]["unverified_tracks"][5]["samples"] = []
        report = evaluate(seal(run), labels)
        self.assertEqual(report["missed_visible_labels"], 6)
        self.assertAlmostEqual(report["correct_identity_recall"], 5 / 6)
        labels["frames"][0]["boats"][0].update(visible=False, center_px=None)
        report = evaluate(run, labels)
        self.assertEqual(report["visible_boat_labels"], 35)
        self.assertEqual(report["unmatched_predictions"], 1)

    def test_source_clip_scale_clock_and_independent_label_origin_are_bound(self):
        for key, value in (("source_sha256", "b" * 64), ("race", 2), ("race", True),
                           ("event_date", "2026-11-02"), ("clip_start_seconds", 5.),
                           ("sample_interval_s", 1), ("frame_size", {"width": 640, "height": 360}),
                           ("annotation_origin", "model_export"), ("results", {})):
            run, labels = examples()
            labels[key] = value
            with self.assertRaises(ValueError, msg=key):
                evaluate(run, labels)

    def test_duplicate_frames_nan_and_invented_occluded_position_rejected(self):
        run, labels = examples()
        labels["frames"][1]["frame"] = 0
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluate(run, labels)
        run, labels = examples()
        labels["frames"][0]["boats"][0]["center_px"][0] = float("nan")
        with self.assertRaises(ValueError):
            evaluate(run, labels)
        run, labels = examples()
        labels["frames"][0]["boats"][0]["visible"] = False
        with self.assertRaisesRegex(ValueError, "occluded"):
            evaluate(run, labels)

    def test_tampering_and_false_verified_claims_are_rejected(self):
        run, labels = examples()
        run["race"] = 2
        with self.assertRaisesRegex(ValueError, "digest"):
            evaluate(run, labels)
        run, labels = examples()
        run["eligible_for_formal_forecast"] = True
        with self.assertRaisesRegex(ValueError, "verified"):
            evaluate(seal(run), labels)


if __name__ == "__main__":
    unittest.main()
