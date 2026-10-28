"""Unattended visual *candidates*, without boat or shore clicks.

Six jacket-colour hypotheses are associated across frames; background features
are selected automatically for camera stabilization. This untrained detector
does not certify identities, metres, turn geometry, or forecast eligibility.
Only numeric observations leave memory. Real-footage validation is outstanding.
"""
from __future__ import annotations

import math

MODEL = "mikuni-unseeded-color-camera-candidates-v1"
SCHEMA = "boatlabs.mikuni_automatic_pixel_candidates.v1"
FRAME_LIMIT = 48
MIN_TRACK_FRAMES = 4
COLORS = {
    1: [((0, 0, 195), (179, 60, 255))],
    2: [((0, 0, 0), (179, 255, 52))],
    3: [((0, 95, 75), (10, 255, 255)), ((170, 95, 75), (179, 255, 255))],
    4: [((95, 95, 65), (130, 255, 255))],
    5: [((18, 95, 95), (39, 255, 255))],
    6: [((40, 80, 60), (89, 255, 255))],
}


def _libraries():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("automatic_vision_dependencies_missing") from exc
    return cv2, np


def _detections(image):
    cv2, np = _libraries()
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    found = {}
    exclude = np.zeros((h, w), dtype=np.uint8)
    border_x, border_y = max(8, w // 40), max(8, h // 12)
    for lane, ranges in COLORS.items():
        mask = np.zeros((h, w), dtype=np.uint8)
        for low, high in ranges:
            mask |= cv2.inRange(hsv, low, high)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if not max(10, h * w * .00004) <= area <= h * w * .008:
                continue
            x, y, rw, rh = cv2.boundingRect(contour)
            if (x < border_x or y < border_y or x + rw > w - border_x
                    or y + rh > h - border_y or not .2 <= rw / rh <= 5):
                continue
            moment = cv2.moments(contour)
            if moment["m00"] <= 0:
                continue
            points.append([moment["m10"] / moment["m00"], moment["m01"] / moment["m00"]])
            cv2.rectangle(exclude, (max(0, x - 14), max(0, y - 14)),
                          (min(w - 1, x + rw + 14), min(h - 1, y + rh + 14)), 255, -1)
        found[lane] = points
    return found, exclude


def _camera(previous, current, exclude):
    """Automatically fit broad background consensus; fail on sparse/cut scenes."""
    cv2, np = _libraries()
    h, w = previous.shape
    points = cv2.goodFeaturesToTrack(previous, maxCorners=240, qualityLevel=.02,
                                   minDistance=9, mask=cv2.bitwise_not(exclude), blockSize=5)
    if points is None or len(points) < 16:
        return None
    following, ok, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None,
                                               winSize=(21, 21), maxLevel=3)
    if following is None or ok is None:
        return None
    backward, back_ok, _ = cv2.calcOpticalFlowPyrLK(current, previous, following, None,
                                                  winSize=(21, 21), maxLevel=3)
    if backward is None or back_ok is None:
        return None
    valid = (ok.reshape(-1) != 0) & (back_ok.reshape(-1) != 0)
    valid &= np.linalg.norm(points - backward, axis=2).reshape(-1) < 1.5
    a, b = points[valid].reshape(-1, 2), following[valid].reshape(-1, 2)
    if len(a) < 12:
        return None
    transform, inliers = cv2.findHomography(a, b, cv2.RANSAC, 2.5)
    if transform is None or inliers is None or not np.isfinite(transform).all():
        return None
    selected = a[inliers.reshape(-1) != 0]
    if len(selected) < 12 or len(selected) < .65 * len(a):
        return None
    if (np.ptp(selected[:, 0]) < .35 * w or np.ptp(selected[:, 1]) < .25 * h
            or cv2.contourArea(cv2.convexHull(selected)) < .08 * w * h):
        return None
    if abs(transform[2, 2]) < 1e-8:
        return None
    transform /= transform[2, 2]
    corners = np.array([[[0., 0.], [w - 1., 0.], [w - 1., h - 1.], [0., h - 1.]]], np.float32)
    projected = cv2.perspectiveTransform(corners, transform)[0]
    if (not np.isfinite(projected).all() or np.max(np.abs(projected - corners[0])) > .4 * max(w, h)
            or not .6 < abs(np.linalg.det(transform[:2, :2])) < 1.7):
        return None
    return transform


def propose_clip_starts(jpeg_images, *, sample_interval_s=5, limit=3):
    """Scan a bounded low-rate preview; no manually entered clip start time."""
    cv2, np = _libraries()
    if (not isinstance(sample_interval_s, (int, float)) or isinstance(sample_interval_s, bool)
            or not math.isfinite(sample_interval_s) or not .1 <= sample_interval_s <= 10
            or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 3):
        raise ValueError("invalid_automatic_preview_parameters")
    ranked = []
    for index, encoded in enumerate(jpeg_images[:FRAME_LIMIT]):
        if not isinstance(encoded, bytes):
            continue
        image = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            continue
        detected, _ = _detections(image)
        unique_colors = sum(len(regions) == 1 for regions in detected.values())
        ranked.append((unique_colors, index))
    starts = []
    # Earlier equally scored scenes win. Try distinct 24-second regions only.
    for score, index in sorted(ranked, key=lambda item: (-item[0], item[1])):
        if not score:
            continue
        start = min(300., max(0., index * sample_interval_s - 3.))
        if all(abs(start - old) >= 24 for old in starts):
            starts.append(start)
        if len(starts) == limit:
            break
    return starts or [0.]


def analyze_automatic_frames(jpeg_images, *, sample_interval_s=.5):
    """Detect/associate/stabilize numeric candidates with zero manual inputs."""
    if (isinstance(sample_interval_s, bool) or not isinstance(sample_interval_s, (int, float))
            or not math.isfinite(sample_interval_s) or not .1 <= sample_interval_s <= 3):
        raise ValueError("invalid_automatic_sample_interval")
    cv2, np = _libraries()
    if not isinstance(jpeg_images, (list, tuple)) or not jpeg_images:
        raise ValueError("automatic_frames_missing")
    history = {lane: [] for lane in COLORS}
    active = {}
    previous = None
    previous_exclude = None
    accumulated = np.eye(3)
    segment = 0
    stable_frames = 0
    frame_size = None
    ambiguous_frames = 0
    for index, encoded in enumerate(jpeg_images[:FRAME_LIMIT]):
        if not isinstance(encoded, bytes):
            raise ValueError("automatic_frame_not_jpeg")
        image = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("automatic_frame_decode_failed")
        h, w = image.shape[:2]
        if w < 120 or h < 80 or w > 640 or h > 2160:
            raise ValueError("automatic_frame_dimensions_invalid")
        if frame_size is not None and frame_size != (w, h):
            raise ValueError("automatic_frame_dimensions_changed")
        frame_size = (w, h)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detections, exclude = _detections(image)
        compensated = previous is None
        if previous is not None:
            transform = _camera(previous, gray, previous_exclude)
            if transform is None:
                # No interpolation, identity hand-off, or motion across scene cuts.
                segment += 1
                active = {}
                accumulated = np.eye(3)
            else:
                accumulated = transform @ accumulated
                compensated = True
        inverse = None
        if compensated:
            try:
                inverse = np.linalg.inv(accumulated)
                if not np.isfinite(inverse).all():
                    inverse = None
            except np.linalg.LinAlgError:
                inverse = None
        if inverse is not None:
            stable_frames += 1
        for lane, regions in detections.items():
            # Several same-colour objects cannot establish a unique boat ID.
            if len(regions) != 1:
                if len(regions) > 1:
                    ambiguous_frames += 1
                active.pop(lane, None)
                continue
            point = regions[0]
            old = active.get(lane)
            if old is None or old["frame"] != index - 1 or math.dist(old["point"], point) > 70:
                chain = (history[lane][-1]["chain"] + 1) if history[lane] else 0
            else:
                chain = old["chain"]
            stabilized = None
            if inverse is not None:
                p = cv2.perspectiveTransform(np.array([[point]], np.float32), inverse)[0, 0]
                if np.isfinite(p).all():
                    stabilized = [round(float(z), 3) for z in p]
            sample = {"frame": index, "t_s": round(index * sample_interval_s, 4),
                      "segment": segment, "chain": chain,
                      "center_px": [round(float(z), 3) for z in point],
                      "camera_stabilized_center_px": stabilized}
            history[lane].append(sample)
            active[lane] = {"frame": index, "point": point, "chain": chain}
        previous, previous_exclude = gray, exclude
    tracks = []
    for lane, samples in history.items():
        groups = {}
        for sample in samples:
            groups.setdefault((sample["segment"], sample["chain"]), []).append(sample)
        eligible = []
        for group in groups.values():
            stable = [s for s in group if s["camera_stabilized_center_px"] is not None]
            if len(stable) < MIN_TRACK_FRAMES:
                continue
            raw_span = max(math.dist(a["center_px"], b["center_px"]) for a in stable for b in stable)
            relative_span = max(math.dist(a["camera_stabilized_center_px"], b["camera_stabilized_center_px"])
                                for a in stable for b in stable)
            # Screen overlays have no image motion; background has no relative motion.
            if raw_span > 1.5 and relative_span > 2:
                eligible.append(stable)
        best = max(eligible, key=len) if eligible else []
        steps = [math.dist(a["camera_stabilized_center_px"], b["camera_stabilized_center_px"])
                 / (b["t_s"] - a["t_s"]) for a, b in zip(best, best[1:])
                 if b["frame"] == a["frame"] + 1]
        tracks.append({"lane_color_hypothesis": lane, "candidate_accepted": bool(best),
                       "longest_supported_track_frames": len(best),
                       "median_relative_motion_px_per_s": round(float(np.median(steps)), 3) if steps else None,
                       "samples": samples, "identity_independently_verified": False})
    count = sum(track["candidate_accepted"] for track in tracks)
    return {"schema": SCHEMA, "model": MODEL,
            "status": "AUTOMATIC_UNVERIFIED_CANDIDATES_ONLY", "manual_inputs_required": 0,
            "sampled_frames": min(len(jpeg_images), FRAME_LIMIT), "sample_interval_s": sample_interval_s,
            "camera_reference_selection": "AUTOMATIC_BACKGROUND_FEATURE_CONSENSUS",
            "camera_stabilized_frames": stable_frames, "scene_segments": segment + 1,
            "ambiguous_color_frames": ambiguous_frames, "candidate_boat_tracks": count,
            "all_six_candidates_supported": count == 6, "unverified_tracks": tracks,
            "confirmed_boat_tracks": 0, "measured_turns": 0, "measured_post_start_stretches": 0,
            "water_plane_metre_calibration_confirmed": False,
            "eligible_for_formal_or_shadow_forecast": False,
            "validation_status": "REAL_FOOTAGE_IDENTITY_AND_CALIBRATION_NOT_VALIDATED"}
