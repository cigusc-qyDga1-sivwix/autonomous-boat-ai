"""BOAT VISION AI — independent, unverified visual motion candidate analyzer.

No imports from BOAT LAB forecasting modules, no video downloads, no result
data, no odds and no stakes. Candidate pixels are not calibrated speeds or
verified boat identities. The output cannot be directly used for formal picks.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
from statistics import median

INPUT_SCHEMA = "boatlabs.mikuni_seeded_six_boat_pixel_tracks.v0.1"
OUTPUT_SCHEMA = "boatlabs.vision_ai.pixel_motion_candidate.v1"
MODEL = "boat-vision-ai-independent-pixel-motion-v0.1"
PROHIBITED = frozenset({"finish", "result", "results", "payout", "payouts",
                         "official_results", "odds", "bets", "winner"})
MAX_FRAMES = 48


def _no_postrace_fields(value):
    if isinstance(value, dict):
        if any(str(k).lower() in PROHIBITED for k in value):
            raise ValueError("postrace_or_betting_field_forbidden")
        for nested in value.values():
            _no_postrace_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _no_postrace_fields(nested)


def _valid_day(value):
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _real(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("non_numeric_motion_measurement")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non_finite_motion_measurement")
    return number


def _segments(track, count):
    """Pixel-only candidate motion, not real-world speed or turn angle."""
    samples = track.get("samples")
    if not isinstance(samples, list) or len(samples) > count:
        raise ValueError("invalid_candidate_samples")
    prior = None
    intervals = []
    headings = []
    last_frame = -1
    last_time = -1.0
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("invalid_candidate_frame")
        frame = sample.get("frame")
        if type(frame) is not int or not 0 <= frame < count or frame <= last_frame:
            raise ValueError("invalid_frame_order")
        t = _real(sample.get("t_seconds"))
        if not 0 <= t <= 300 or t <= last_time:
            raise ValueError("invalid_frame_time")
        pt = sample.get("camera_stabilized_center_px")
        if (not isinstance(pt, list) or len(pt) != 2
                or any(abs(_real(x)) > 4096 for x in pt)):
            raise ValueError("invalid_stabilized_pixel_position")
        p = (_real(pt[0]), _real(pt[1]))
        if prior is not None:
            old_frame, old_t, old_p = prior
            if frame == old_frame + 1:
                delta = t - old_t
                if delta > 3:
                    raise ValueError("excessive_frame_gap")
                dx, dy = p[0]-old_p[0], p[1]-old_p[1]
                speed = math.hypot(dx, dy) / delta
                if speed > 1500:
                    raise ValueError("implausible_pixel_step")
                intervals.append((t, speed))
                if speed >= 0.001:
                    headings.append(math.atan2(dy, dx))
        prior = (frame, t, p)
        last_frame, last_time = frame, t
    coverage = len(samples) / count
    ratio = None
    if len(intervals) >= 4:
        mid = len(intervals)//2
        early = median(v for _, v in intervals[:mid])
        late = median(v for _, v in intervals[mid:])
        if early > 0.01:
            ratio = round(late/early, 3)
    change = None
    if len(headings) >= 3:
        changes = [abs(math.atan2(math.sin(b-a), math.cos(b-a)))
                   for a, b in zip(headings, headings[1:])]
        change = round(sum(changes)*180/math.pi, 2)
    return {
        "observed_frames": len(samples),
        "candidate_coverage": round(coverage, 3),
        "median_apparent_motion_px_per_s": (
            round(median(v for _, v in intervals), 3) if intervals else None),
        "late_to_early_pixel_motion_ratio": ratio,
        "cumulative_image_heading_change_deg": change,
        "identity_verified": False,
        "real_world_calibration": False,
    }


def analyze(tracker, *, analyzed_at_utc=None):
    """Receive only the independent tracker JSON, emit a safe candidate JSON."""
    if not isinstance(tracker, dict):
        raise ValueError("tracker_json_required")
    _no_postrace_fields(tracker)
    if (tracker.get("schema") != INPUT_SCHEMA
            or tracker.get("status") != "UNVERIFIED_CAMERA_STABILIZED_SIX_SEED_CANDIDATES"
            or tracker.get("venue_code") != "10" or not _valid_day(tracker.get("event_date"))):
        raise ValueError("unverified_mikuni_tracker_required")
    race, count = tracker.get("race"), tracker.get("frames_seen")
    if (type(race) is not int or not 1 <= race <= 12
            or type(count) is not int or not 2 <= count <= MAX_FRAMES):
        raise ValueError("invalid_race_or_frame_count")
    digest = tracker.get("source_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)):
        raise ValueError("invalid_video_digest")
    if (tracker.get("eligible_for_formal_or_shadow_forecast") is not False
            or tracker.get("approved_verified_track_ledger_created") is not False
            or tracker.get("confirmed_boat_tracks") != 0):
        raise ValueError("verified_tracker_claim_not_supported")
    tracks = tracker.get("unverified_tracks")
    if not isinstance(tracks, list) or len(tracks) != 6:
        raise ValueError("six_tracks_required")
    rows = {}
    for track in tracks:
        lane = track.get("lane_seed_label") if isinstance(track, dict) else None
        if type(lane) is not int or lane not in range(1, 7) or lane in rows:
            raise ValueError("duplicate_or_invalid_seed_label")
        if track.get("id_independently_verified") is not False:
            raise ValueError("unsupported_identity_verification")
        rows[lane] = {"seed_label": lane, **_segments(track, count)}
    if set(rows) != set(range(1, 7)):
        raise ValueError("missing_seed_labels")
    analyzed = analyzed_at_utc or datetime.now(timezone.utc)
    if not isinstance(analyzed, datetime) or analyzed.tzinfo is None:
        raise ValueError("timezone_aware_analysis_clock_required")
    core = {
        "schema": OUTPUT_SCHEMA,
        "model_version": MODEL,
        "event_date": tracker["event_date"],
        "venue_code": tracker["venue_code"],
        "race": race,
        "source_sha256": digest,
        "analyzed_at_utc": analyzed.astimezone(timezone.utc).isoformat(),
        "status": "PIXEL_CANDIDATES_UNVERIFIED",
        "input_type": "seeded_camera_stabilized_pixel_tracks",
        "camera_stabilized_frame_count": tracker.get("camera_stabilized_frames"),
        "six_seed_motion_candidates": [rows[lane] for lane in range(1, 7)],
        "video_identity_verified": False,
        "physical_speed_calibrated": False,
        "eligible_for_shadow_forecast": False,
        "eligible_for_formal_forecast": False,
        "official_results_used": False,
        "bets_generated": 0,
        "data_policy": "Numeric research only. No video or frame bytes persisted.",
        "blocker": "authorized_real_media_and_independent_six_boat_identity_calibration",
    }
    core["report_sha256"] = hashlib.sha256(json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return core
