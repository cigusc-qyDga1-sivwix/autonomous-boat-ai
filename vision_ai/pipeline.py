"""Independent approved media -> automatic candidates -> numeric research JSON.

The manifest declares the source; it does not independently prove the race or
boat identities. No frame bytes, video URLs or file paths enter the report.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError

from .analyzer import _no_postrace_fields, _valid_day
from .media import MAX_VIDEO_BYTES, decode_in_memory, receive_approved_video
from .report_io import write_report
from .tracking import MODEL, analyze_automatic_frames, propose_clip_starts

MANIFEST_SCHEMA = "boatlabs.vision_ai.source_manifest.v1"
SCHEMA = "boatlabs.vision_ai.media_candidate_run.v1"


def _digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("source_manifest_required")
    _no_postrace_fields(manifest)
    allowed = {"schema", "event_date", "venue_code", "race", "source_kind",
               "permission_reference", "expected_sha256"}
    if set(manifest) - allowed or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("source_manifest_schema_invalid")
    if (not _valid_day(manifest.get("event_date")) or manifest.get("venue_code") != "10"
            or type(manifest.get("race")) is not int or not 1 <= manifest["race"] <= 12):
        raise ValueError("source_manifest_race_invalid")
    if manifest.get("source_kind") not in {"real_exhibition", "synthetic_test"}:
        raise ValueError("source_kind_required")
    reference = manifest.get("permission_reference")
    if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 200:
        raise ValueError("permission_reference_required")
    if "expected_sha256" in manifest and not _digest(manifest["expected_sha256"]):
        raise ValueError("expected_source_digest_invalid")


def _numeric_hash(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def run(manifest, *, video_file=None, video_url=None, allowed_hosts=(), now=None):
    """Process one source without numerical-AI imports or production writes.

    Missing input and failures return a numeric status. The CLI returns nonzero
    for these states so a green job cannot imply successful media acquisition.
    """
    validate_manifest(manifest)
    if video_file is not None and video_url is not None:
        raise ValueError("exactly_one_video_source_required")
    clock = now or datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("timezone_aware_clock_required")
    report = {
        "schema": SCHEMA, "model_version": MODEL,
        **{k: manifest[k] for k in ("event_date", "venue_code", "race")},
        "declared_source_kind": manifest["source_kind"],
        "manifest_sha256": _numeric_hash(manifest),
        "run_started_at_utc": clock.astimezone(timezone.utc).isoformat(),
        "status": "NO_SOURCE_CONFIGURED", "source_sha256": None,
        "stages": {"media_received": False, "frames_decoded": False,
                   "automatic_tracking_computed": False, "six_candidates_simultaneous": False},
        "race_identity_status": "MANIFEST_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
        "real_footage_independently_verified": False,
        "confirmed_boat_tracks": 0, "physical_speed_calibrated": False,
        "eligible_for_shadow_forecast": False, "eligible_for_formal_forecast": False,
        "official_results_used": False, "bets_generated": 0,
        "raw_media_bytes_persisted": 0,
    }
    stage = "SOURCE"
    try:
        if video_file is None and not video_url:
            return _finish(report, now)
        if video_file is not None:
            with Path(video_file).open("rb") as source:
                blob = source.read(MAX_VIDEO_BYTES + 1)
            if not blob or len(blob) > MAX_VIDEO_BYTES:
                raise ValueError("video_size_invalid")
        else:
            hosts = {h.strip().lower() for h in allowed_hosts if isinstance(h, str) and h.strip()}
            blob, _ = receive_approved_video(video_url, hosts)
        report["stages"]["media_received"] = True
        report["media_bytes"] = len(blob)
        report["source_sha256"] = hashlib.sha256(blob).hexdigest()
        report["source_received_at_utc"] = _clock(now)
        if (manifest.get("expected_sha256") is not None
                and manifest["expected_sha256"] != report["source_sha256"]):
            report["status"] = "SOURCE_DIGEST_MISMATCH"
            return _finish(report, now)
        stage = "DECODE"
        preview = decode_in_memory(blob, sample_interval_s=5)
        report["stages"]["frames_decoded"] = True
        report["preview_frames_decoded"] = len(preview)
        stage = "TRACKING"
        starts = propose_clip_starts(preview)
        best = None
        for start in starts:
            stage = "DECODE"
            images = decode_in_memory(blob, start_seconds=start)
            stage = "TRACKING"
            tracking = analyze_automatic_frames(images)
            simultaneous = _simultaneous(tracking)
            score = (simultaneous, tracking["candidate_boat_tracks"], tracking["camera_stabilized_frames"])
            if best is None or score > best[0]:
                # Preserve the selected decoded geometry for annotation matching.
                from .tracking import _libraries
                cv2, np = _libraries()
                image = cv2.imdecode(np.frombuffer(images[0], np.uint8), cv2.IMREAD_COLOR)
                height, width = image.shape[:2]
                best = (score, start, tracking, {"width": width, "height": height})
        _, selected, tracking, frame_size = best
        report.update({"status": "AUTOMATIC_CANDIDATES_UNVERIFIED", "tracking": tracking,
                       "clip_start_seconds": selected, "frame_size": frame_size,
                       "candidate_clip_starts_seconds": starts,
                       "longest_simultaneous_six_candidate_run_frames": _simultaneous(tracking)})
        report["stages"]["automatic_tracking_computed"] = True
        report["stages"]["six_candidates_simultaneous"] = _simultaneous(tracking) >= 4
        if tracking["candidate_boat_tracks"] == 0:
            report["status"] = "NO_SUPPORTED_TRACK_CANDIDATES"
    except HTTPError as exc:
        report["status"] = "SOURCE_HTTP_ERROR"
        report["http_status"] = exc.code
    except (URLError, TimeoutError, OSError, RuntimeError, ValueError):
        # Exceptions can contain signed URLs or local paths; do not persist them.
        report["status"] = stage + "_UNAVAILABLE_OR_INVALID"
    return _finish(report, now)


def _clock(fixed):
    return (fixed or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _finish(report, fixed):
    report["run_completed_at_utc"] = _clock(fixed)
    report["report_sha256"] = _numeric_hash(report)
    return report


def _simultaneous(tracking):
    frames = []
    for track in tracking["unverified_tracks"]:
        # Six tracks in different scenes must never mean six boats together.
        groups = {}
        for s in track["samples"]:
            if s["camera_stabilized_center_px"] is not None:
                groups.setdefault((s["segment"], s["chain"]), []).append(s)
        supported = {}
        for group in groups.values():
            if len(group) < 4:
                continue
            raw = max(math.dist(a["center_px"], b["center_px"]) for a in group for b in group)
            relative = max(math.dist(a["camera_stabilized_center_px"], b["camera_stabilized_center_px"])
                           for a in group for b in group)
            if raw > 1.5 and relative > 2:
                supported.update({s["frame"]: (s["segment"], s["chain"]) for s in group})
        frames.append(supported if track["candidate_accepted"] else {})
    common = sorted(set.intersection(*(set(f) for f in frames))) if len(frames) == 6 else []
    longest = current = 0
    previous = None
    previous_signature = None
    for frame in common:
        signature = tuple(f[frame] for f in frames)
        current = current + 1 if previous == frame - 1 and signature == previous_signature else 1
        longest = max(longest, current)
        previous = frame
        previous_signature = signature
    return longest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent approved exhibition video research")
    parser.add_argument("--manifest", required=True, type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--video-file", type=Path)
    source.add_argument("--from-url-env", action="store_true",
                        help="Read VISION_VIDEO_URL and VISION_VIDEO_ALLOWED_HOSTS; do not log them")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = run(manifest, video_file=args.video_file,
                     video_url=os.environ.get("VISION_VIDEO_URL") if args.from_url_env else None,
                     allowed_hosts=os.environ.get("VISION_VIDEO_ALLOWED_HOSTS", "").split(","))
        inputs = [args.manifest] + ([args.video_file] if args.video_file is not None else [])
        write_report(report, args.output, inputs=inputs)
    except (ValueError, TypeError, OSError):
        parser.exit(2, "BOAT VISION AI: invalid manifest or output; no input details logged\n")
    print("BOAT VISION AI: " + report["status"] + "; independently verified 0R; formal picks 0")
    return 0 if report["stages"]["automatic_tracking_computed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
