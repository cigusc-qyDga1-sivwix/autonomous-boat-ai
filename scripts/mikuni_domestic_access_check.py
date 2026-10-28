"""Compare official Mikuni replay access from a legitimately eligible local host.

Diagnostics ONLY. Never downloads a video, evades access controls, or changes
forecasts. The underlying browser probe blocks direct video/HLS/DASH/media.
This wrapper compares ordinary desktop and mobile browser sessions, retaining
only an aggregate sanitized audit (no IP addresses, auth material or URLs).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from scripts.mikuni_replay_transport_probe import run_browser_probe, validate

SCHEMA = "boatlabs.mikuni_domestic_access_check.v1"
JST = timezone(timedelta(hours=9))
BASELINE_DAY = "2026-10-28"


def normal_get_statuses(probe):
    """Return numeric statuses from the bounded, sanitized in-browser GET audit."""
    if not isinstance(probe, dict):
        return []
    rows = probe.get("normal_browser_get_responses") or []
    return sorted({
        r["http_status"]
        for r in rows
        if isinstance(r, dict)
        and isinstance(r.get("http_status"), int)
        and not isinstance(r.get("http_status"), bool)
    })


def access_decision(profiles):
    statuses = [normal_get_statuses(p) for p in profiles]
    if len(statuses) != 2:
        return "DIAGNOSTIC_INCOMPLETE"
    if all(403 in codes for codes in statuses):
        return "BOTH_PROFILES_HTTP_403"
    if any(s in {200, 206} for codes in statuses for s in codes):
        return "NORMAL_GET_RESPONDED_2XX_VIDEO_NOT_VERIFIED"
    if any(codes for codes in statuses):
        return "HTTP_RESPONDED_BUT_ACCESS_UNCONFIRMED"
    return "NO_BROWSER_GET_RESPONSE"


def compact_profile(probe, label):
    safe = probe if isinstance(probe, dict) else {}
    return {
        "browser_profile": label,
        "public_page_status": safe.get("landing_http_status"),
        "meeting_header_clicked": safe.get("meeting_header_clicked") is True,
        "day_header_clicked": safe.get("day_header_clicked") is True,
        "race_button_clicked": safe.get("race_button_clicked") is True,
        "normal_get_statuses": normal_get_statuses(safe),
        "playback_error_codes": [
            {k: e.get(k) for k in ("code", "id", "status") if k in e}
            for e in (safe.get("normal_browser_get_error_codes") or [])
            if isinstance(e, dict)
        ][:4],
        "access_hypothesis": safe.get("access_category_hypothesis", "CAUSE_UNDETERMINED"),
        "probe_status": safe.get("status", "UNAVAILABLE"),
    }


def run_comparison(day, race, *, probe=run_browser_probe):
    validate(day, race)
    profiles = [
        probe(day, race, inspect_normal_get=True, mobile_context=False),
        probe(day, race, inspect_normal_get=True, mobile_context=True),
    ]
    decision = access_decision(profiles)
    return {
        "schema": SCHEMA,
        "date": day,
        "venue": "三国",
        "race": race,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "host_location": "NOT_VERIFIED_BY_TOOL",
        "purpose": "NORMAL_OFFICIAL_BROWSER_ACCESS_DIAGNOSTIC_ONLY",
        "access_decision": decision,
        "cloud_baseline": (
            {"date": BASELINE_DAY, "desktop_get": 403, "mobile_get": 403,
             "error_code": "REQUEST_FAILED", "error_id": 124,
             "evidence": "GitHub Actions run 40635141444"}
            if day == BASELINE_DAY else None
        ),
        "profiles": [
            compact_profile(profiles[0], "DESKTOP_CHROMIUM"),
            compact_profile(profiles[1], "MOBILE_CHROMIUM_PIXEL7"),
        ],
        "verified_official_video_races": 0,
        "video_bytes_downloaded": 0,
        "video_frames_decoded": 0,
        "six_boat_tracks_verified": 0,
        "formal_forecast_modified": False,
        "automatic_media_ingestion": "NOT_CONFIGURED",
        "note": (
            "A 2xx playback API metadata GET is not an actual video decode. "
            "Streaming terms, source entitlement, media content and race identity "
            "must be verified separately before any video ingestion."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Official Mikuni local access comparison (no video)")
    parser.add_argument("--date", default=datetime.now(JST).date().isoformat())
    parser.add_argument("--race", type=int, default=1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    audit = run_comparison(args.date, args.race)
    rendered = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    # 403 is a completed diagnostic, not a video-access success.
    return 0 if audit["access_decision"] == "NORMAL_GET_RESPONDED_2XX_VIDEO_NOT_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
