"""Fail-closed unattended Mikuni video research evidence audit.

Only numeric provenance/status ledgers are inspected. This program never
downloads video or certifies synthetic colour hypotheses as real boat IDs.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

SCHEMA = "boatlabs.mikuni_video_evidence_gate.v1"


def counter(data, key):
    value = data.get(key, 0)
    if type(value) is not int or value < 0:
        raise ValueError("invalid_counter:" + key)
    return value


def audit(auto, shadow):
    if not isinstance(auto, dict) or not isinstance(shadow, dict):
        raise ValueError("invalid_ledger")
    if (auto.get("schema") != "boatlabs.mikuni_authorized_video_ingestion.v1"
            or shadow.get("schema") != "boatlabs.mikuni_video_motion_shadow_v0.1"):
        raise ValueError("wrong_ledger_schema")
    day = auto.get("event_date")
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError("invalid_day")
    if shadow.get("event_date") != day:
        raise ValueError("mismatched_dates")
    if auto.get("venue_code") != "10" or auto.get("venue") != "三国" or shadow.get("venue") != "三国":
        raise ValueError("wrong_venue")
    source = auto.get("source_configured")
    if type(source) is not bool:
        raise ValueError("invalid_source_flag")
    a, s = auto.get("summary"), shadow.get("summary")
    if not isinstance(a, dict) or not isinstance(s, dict):
        raise ValueError("missing_summary")
    real = counter(a, "video_races_observed")
    candidates = counter(a, "automatic_candidate_races")
    six = counter(a, "automatic_six_candidate_races")
    claimed = counter(a, "confirmed_boat_tracks")
    frozen = counter(s, "video_shadow_frozen_races")
    if real > 12 or candidates > real or six > candidates or claimed > 6 * real:
        raise ValueError("contradictory_video_counts")
    if real > 0 and not source:
        raise ValueError("real_video_without_authorized_source")
    if counter(s, "formal_forecasts_modified") != 0:
        raise ValueError("formal_forecasts_changed")
    if s.get("video_not_assumed_to_be_verified") is not True:
        raise ValueError("missing_independent_verification_guard")
    # The venue's permission for personal, non-reposted automatic video
    # research was explicitly reported by the user. Do not mislabel missing
    # cloud-direct media configuration as missing venue consent.
    venue_permission_reported = (
        auto.get("permission_provenance")
        == "USER_REPORTED_VENUE_PERMISSION_PERSONAL_AUTO_ANALYSIS_NO_REPOST"
    )
    if not source:
        state, blocker = "AWAITING_DIRECT_MEDIA_ENDPOINT", "DIRECT_MEDIA_ENDPOINT_NOT_CONFIGURED"
    elif not real:
        state, blocker = "SOURCE_CONFIGURED_NO_DECODED_MEDIA", "REAL_FRAME_DECODE_NOT_CONFIRMED"
    else:
        state, blocker = "REAL_MEDIA_RESEARCH_UNVERIFIED", "INDEPENDENT_SIX_BOAT_VERIFICATION_REQUIRED"
    return {
        "schema": SCHEMA, "event_date": day, "venue_code": "10",
        "state": state, "blocker": blocker,
        "github_unattended_audit_no_pc": True,
        "source_configured": source,
        "venue_permission_status": (
            "USER_REPORTED_GRANTED_PERSONAL_AUTO_ANALYSIS_NO_REPOST"
            if venue_permission_reported else "NOT_RECORDED_IN_LEDGER"
        ),
        "direct_media_provider_access": "NOT_CONFIRMED_BY_BROWSER_PLAYBACK",
        "reported_real_video_races_decoded": real,
        "six_colour_candidates_not_identities": six,
        "reported_confirmed_tracks_not_independently_reviewed": claimed,
        "reported_shadow_frozen_races": frozen,
        "verified_six_boat_races": 0,
        "real_footage_independently_verified": False,
        "video_ai_complete": False,
        "formal_forecasts_modified": False,
        "explanation": (
            "Venue consent for personal non-reposted automated analysis is user-reported. "
            "A working browser player does not provide an unattended direct media endpoint. "
            "Synthetic tracking does not validate real-race boat identities."
        ),
    }


def run(day, root=Path(".")):
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("invalid_day")
    folder = root / "app" / "data" / "experiments"
    auto = json.loads((folder / f"mikuni-video-auto-{day}.json").read_text(encoding="utf-8"))
    shadow = json.loads((folder / f"mikuni-video-shadow-{day}.json").read_text(encoding="utf-8"))
    report = audit(auto, shadow)
    output = folder / f"mikuni-video-verification-{day}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Mikuni video verification {day}: {report['state']} ({report['blocker']})")
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args()
    try:
        run(args.date, args.root)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        p.exit(2, f"Video evidence audit failed: {exc}\n")


if __name__ == "__main__":
    main()
