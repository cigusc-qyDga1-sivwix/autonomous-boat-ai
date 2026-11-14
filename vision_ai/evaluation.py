"""Compare color candidates to separately authored image-coordinate labels.

This measures localization/ID confusion on declared annotation frames only.
It never certifies real footage, calibrated motion or forecast eligibility.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median

from .analyzer import _no_postrace_fields, _real, _valid_day
from .pipeline import SCHEMA as RUN_SCHEMA, _digest, _numeric_hash
from .report_io import write_report

SCHEMA = "boatlabs.vision_ai.candidate_label_evaluation.v1"
LABEL_SCHEMA = "boatlabs.vision_ai.frame_labels.v1"


def _point(value, width, height):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("image_point_required")
    x, y = (_real(v) for v in value)
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError("image_point_out_of_frame")
    return [x, y]


def _assignment(predicted, truth, radius):
    """Maximum-cardinality, minimum-distance one-to-one matching (<=6 boats).

    IDs are deliberately ignored during spatial matching so swaps are counted
    as confusion, rather than made invisible by matching same IDs only.
    """
    states = {0: (0., [])}
    for hypothesis, point in predicted:
        following = dict(states)  # Missing detections/false positives are legal.
        for mask, (cost, pairs) in states.items():
            for j, (boat, target) in enumerate(truth):
                distance = math.dist(point, target)
                if mask & (1 << j) or distance > radius:
                    continue
                new = mask | (1 << j)
                candidate = (cost + distance, pairs + [(hypothesis, boat, distance)])
                if new not in following or candidate[0] < following[new][0]:
                    following[new] = candidate
        states = following
    mask = max(states, key=lambda k: (k.bit_count(), -states[k][0]))
    return states[mask][1]


def evaluate(run, labels, *, radius_px=12.):
    if not isinstance(run, dict) or not isinstance(labels, dict):
        raise ValueError("run_and_labels_required")
    _no_postrace_fields(run)
    _no_postrace_fields(labels)
    if (run.get("schema") != RUN_SCHEMA or labels.get("schema") != LABEL_SCHEMA
            or not run.get("stages", {}).get("automatic_tracking_computed")):
        raise ValueError("completed_candidate_run_and_frame_labels_required")
    if (run.get("eligible_for_formal_forecast") is not False
            or run.get("eligible_for_shadow_forecast") is not False
            or run.get("confirmed_boat_tracks") != 0):
        raise ValueError("unsupported_verified_candidate_claim")
    if not _digest(run.get("source_sha256")):
        raise ValueError("source_digest_required")
    if (not _valid_day(run.get("event_date")) or run.get("venue_code") != "10"
            or type(run.get("race")) is not int or not 1 <= run["race"] <= 12
            or run.get("declared_source_kind") not in {"real_exhibition", "synthetic_test"}):
        raise ValueError("invalid_run_source_metadata")
    body = {k: v for k, v in run.items() if k != "report_sha256"}
    if run.get("report_sha256") != _numeric_hash(body):
        raise ValueError("run_report_digest_mismatch")
    # Comparisons must use the exact selected clip, decoder scale, frame axis
    # and source. A label set from an earlier clip is not an accuracy test.
    for key in ("source_sha256", "event_date", "venue_code", "race", "declared_source_kind",
                "clip_start_seconds", "frame_size"):
        if type(run.get(key)) is not type(labels.get(key)) or run.get(key) != labels.get(key):
            raise ValueError("label_source_or_geometry_mismatch")
    tracking = run["tracking"]
    interval = _real(tracking.get("sample_interval_s"))
    if not .1 <= interval <= 3 or _real(labels.get("sample_interval_s")) != interval:
        raise ValueError("label_time_axis_mismatch")
    if labels.get("annotation_origin") != "independent_manual_review":
        raise ValueError("separate_manual_labels_required")
    reviewer = labels.get("reviewer_reference")
    if not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 200:
        raise ValueError("reviewer_reference_required")
    width, height = run["frame_size"]["width"], run["frame_size"]["height"]
    if type(width) is not int or type(height) is not int or width < 120 or height < 80:
        raise ValueError("invalid_image_geometry")
    radius = _real(radius_px)
    if not 0 < radius <= min(width, height) / 4:
        raise ValueError("invalid_matching_radius")
    count = tracking.get("sampled_frames")
    if type(count) is not int or not 2 <= count <= 48:
        raise ValueError("invalid_sampled_frame_count")
    indexed = {}
    tracks = tracking.get("unverified_tracks")
    if not isinstance(tracks, list) or len(tracks) != 6:
        raise ValueError("six_hypotheses_required")
    seen_ids = set()
    for track in tracks:
        if not isinstance(track, dict) or not isinstance(track.get("samples"), list):
            raise ValueError("candidate_track_required")
        lane = track.get("lane_color_hypothesis")
        if type(lane) is not int or lane not in range(1, 7) or lane in seen_ids:
            raise ValueError("duplicate_or_invalid_hypothesis")
        seen_ids.add(lane)
        if track.get("identity_independently_verified") is not False:
            raise ValueError("unsupported_identity_verification")
        last_frame = -1
        for sample in track["samples"]:
            if not isinstance(sample, dict):
                raise ValueError("candidate_sample_required")
            frame = sample.get("frame")
            if type(frame) is not int or not last_frame < frame < count:
                raise ValueError("invalid_candidate_frame_order")
            expected_t = frame * tracking["sample_interval_s"]
            if abs(_real(sample.get("t_s")) - expected_t) > .00011:
                raise ValueError("candidate_time_axis_mismatch")
            indexed.setdefault(frame, []).append((lane, _point(sample["center_px"], width, height)))
            last_frame = frame
    frames = labels.get("frames")
    if not isinstance(frames, list) or not 2 <= len(frames) <= count:
        raise ValueError("at_least_two_labeled_frames_required")
    visible_total = predicted_total = matched = correct = all_six = 0
    errors, reviewed = [], set()
    confusion = [[0] * 6 for _ in range(6)]  # rows: hypothesis; columns: actual label
    by_boat = {lane: {"visible_labels": 0, "correct_matches": 0} for lane in range(1, 7)}
    for row in frames:
        if not isinstance(row, dict):
            raise ValueError("label_frame_required")
        frame = row.get("frame")
        if type(frame) is not int or not 0 <= frame < count or frame in reviewed:
            raise ValueError("duplicate_or_invalid_label_frame")
        reviewed.add(frame)
        boats = row.get("boats")
        if not isinstance(boats, list) or len(boats) != 6:
            raise ValueError("six_visibility_labels_per_frame_required")
        truth, boat_ids = [], set()
        for boat in boats:
            if not isinstance(boat, dict):
                raise ValueError("boat_label_required")
            lane = boat.get("boat_id")
            if type(lane) is not int or lane not in range(1, 7) or lane in boat_ids:
                raise ValueError("duplicate_or_invalid_label_id")
            boat_ids.add(lane)
            if type(boat.get("visible")) is not bool:
                raise ValueError("visibility_flag_required")
            if boat["visible"]:
                truth.append((lane, _point(boat.get("center_px"), width, height)))
                by_boat[lane]["visible_labels"] += 1
            elif boat.get("center_px") is not None:
                raise ValueError("occluded_label_must_not_invent_position")
        # Overlapping ground truth cannot support a unique boat assignment.
        if any(math.dist(a[1], b[1]) <= 2 * radius
               for i, a in enumerate(truth) for b in truth[i + 1:]):
            raise ValueError("ambiguous_label_positions_reduce_radius_or_mark_occluded")
        predicted = indexed.get(frame, [])
        pairs = _assignment(predicted, truth, radius)
        visible_total += len(truth)
        predicted_total += len(predicted)
        matched += len(pairs)
        frame_correct = 0
        for hypothesis, boat, distance in pairs:
            confusion[hypothesis - 1][boat - 1] += 1
            if hypothesis == boat:
                correct += 1
                frame_correct += 1
                by_boat[boat]["correct_matches"] += 1
                errors.append(distance)
        all_six += int(len(truth) == 6 and frame_correct == 6)
    report = {
        "schema": SCHEMA, "status": "MANUAL_LABEL_COMPARISON_ONLY",
        **{k: run[k] for k in ("source_sha256", "event_date", "venue_code", "race", "declared_source_kind")},
        "run_report_sha256": run.get("report_sha256"), "labels_sha256": _numeric_hash(labels),
        "matching_radius_px": radius, "labeled_frames": len(frames),
        "visible_boat_labels": visible_total, "predicted_points_on_labeled_frames": predicted_total,
        "spatial_matches": matched, "correct_identity_matches": correct,
        "identity_confusions": matched - correct, "missed_visible_labels": visible_total - matched,
        "unmatched_predictions": predicted_total - matched,
        "spatial_recall": matched / visible_total if visible_total else None,
        "spatial_precision": matched / predicted_total if predicted_total else None,
        "correct_identity_recall": correct / visible_total if visible_total else None,
        "all_six_correct_frames": all_six, "per_boat": by_boat,
        "confusion_matrix_hypothesis_by_label": confusion,
        "median_correct_position_error_px": round(median(errors), 3) if errors else None,
        "p95_correct_position_error_px": round(sorted(errors)[math.ceil(.95 * len(errors)) - 1], 3) if errors else None,
        "evaluation_scope": "Raw color candidate localization on labeled frames; not IDF1 or motion accuracy",
        "real_footage_independently_verified": False, "physical_speed_calibrated": False,
        "eligible_for_shadow_forecast": False, "eligible_for_formal_forecast": False,
        "bets_generated": 0,
    }
    report["report_sha256"] = _numeric_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare VISION candidates to independent frame labels")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--radius-px", type=float, default=12.)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate(json.loads(args.run.read_text(encoding="utf-8")),
                          json.loads(args.labels.read_text(encoding="utf-8")), radius_px=args.radius_px)
        write_report(report, args.output, inputs=(args.run, args.labels))
    except (ValueError, TypeError, KeyError, OSError):
        parser.exit(2, "BOAT VISION AI: invalid candidate/labels/output; no input details logged\n")
    print("BOAT VISION AI: manual label comparison; formal picks 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
