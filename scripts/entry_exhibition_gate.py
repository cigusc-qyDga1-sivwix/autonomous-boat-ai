"""Fail-closed exhibition/entry validation for BOAT LAB forecast presentation.

This is a *view/eligibility* rule, not a prediction input or a rewrite of
immutable pre-cutoff baseline predictions. Research-only baselines remain
available for prospective A/B audit but can never masquerade as final picks.
A watched name is a warning hint, NOT a comprehensive front-attachment model.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import math
import re

JST = ZoneInfo("Asia/Tokyo")
MIN_FREEZE_LEAD_SECONDS = 120
# Explicitly observed front-attaching case. Keep small and auditable:
# A broad unknown list is worse than a clear "not detected" caveat.
WATCHED_ENTRY_NAMES = {
    "赤岩善生": "2026-10-23 大村6R：6号艇→2コースのスタート展示",
}


def clean_name(name):
    return re.sub(r"\s+", "", str(name or "")).strip()


def validated_courses(boat_rows):
    """Six uniquely numbered actual courses, returned as lane->course tuple."""
    if not isinstance(boat_rows, (list, tuple)) or len(boat_rows) != 6:
        return None
    by_lane = {}
    seen = set()
    for row in boat_rows:
        if not isinstance(row, dict):
            return None
        lane, course = row.get("lane"), row.get("course")
        if (isinstance(lane, bool) or not isinstance(lane, int) or
                lane not in range(1, 7) or lane in by_lane):
            return None
        if (isinstance(course, bool) or not isinstance(course, (int, float))
                or not math.isfinite(course) or
                course not in range(1, 7) or course in seen):
            return None
        by_lane[lane] = int(course)
        seen.add(course)
    if set(by_lane) != set(range(1, 7)) or seen != set(range(1, 7)):
        return None
    return tuple(by_lane[lane] for lane in range(1, 7))


def validated_preview(preview):
    """Check *all* six measurements; never default missing courses to lanes."""
    if not isinstance(preview, dict):
        return None
    racers = preview.get("racers")
    if not isinstance(racers, dict):
        return None
    rows = []
    for lane in range(1, 7):
        boat = racers.get(str(lane))
        if not isinstance(boat, dict):
            return None
        for key, low, high in (("exhibition_time", 5, 10),
                               ("start_timing", -.5, 1.0)):
            try:
                value = float(boat.get(key))
                if not math.isfinite(value) or not low <= value <= high:
                    return None
            except (TypeError, ValueError):
                return None
        rows.append({"lane": lane, "course": boat.get("course_number")})
    return validated_courses(rows)


def summarize_gate(snapshot, event_date=None):
    """Final eligibility derived from preserved snapshot (never affects SHA).

    Every baseline is 'hold' because an unlisted forward-entry specialist
    might still change the start exhibition. A complete six-boat, pre-cutoff
    exhibition is required even when no watchlisted athlete is present.
    """
    rows = snapshot.get("racers") or []
    watchers = sorted({
        clean_name(row.get("name")) for row in rows
        if isinstance(row, dict) and clean_name(row.get("name")) in WATCHED_ENTRY_NAMES
    })
    phase = snapshot.get("phase")
    courses = validated_courses(rows) if phase == "exhibition" else None
    complete_readings = bool(courses) and all(
        isinstance(row, dict) and
        all(isinstance(row.get(k), (int, float)) and
            not isinstance(row.get(k), bool) and math.isfinite(row[k])
            and (5 <= row[k] <= 10 if k == "exhibition_time" else
                 -.5 <= row[k] <= 1.0)
            for k in ("exhibition_time", "exhibition_st"))
        for row in rows
    )
    safe_freeze = False
    if event_date and snapshot.get("cutoff_jst") and snapshot.get("frozen_at_utc"):
        try:
            limit = datetime.fromisoformat(event_date + "T" +
                     snapshot["cutoff_jst"] + ":00+09:00")
            frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
            safe_freeze = frozen.tzinfo is not None and (
                frozen.astimezone(JST) <= limit - timedelta(seconds=MIN_FREEZE_LEAD_SECONDS)
            )
        except (TypeError, ValueError):
            safe_freeze = False
    verified = phase == "exhibition" and bool(courses) and complete_readings and safe_freeze
    order = [next(lane for lane, course in enumerate(courses, 1)
                  if course == pos) for pos in range(1, 7)] if courses else None
    changed = order != list(range(1, 7)) if order else False
    reasons = []
    if watchers:
        reasons.append("前付け警戒選手：" + "、".join(watchers))
    if changed:
        reasons.append("スタート展示で進入変更：" + "-".join(map(str, order)))
    if not verified:
        reasons.append("展示6艇の進入・ST・タイムの発走前固定が未確認")
    return {
        "status": "verified" if verified else "hold",
        "final_eligible": verified,
        "buy_allowed": False,  # No odds/profitability or real betting approval.
        "entry_watch": bool(watchers or changed),
        "entry_watch_racers": watchers,
        "entry_changed": changed,
        "exhibition_course_order": order,
        "exhibition_verified_before_cutoff": verified,
        "exhibition_source": (snapshot.get("exhibition_origin") or {}).get("source")
            if verified else None,
        "reason": " ／ ".join(reasons) if reasons else "展示6艇の進入を発走前に検証済み",
        "limitation": "前付け候補の選手リストは網羅的ではない。展示未取得は全レース最終予想保留。",
    }
