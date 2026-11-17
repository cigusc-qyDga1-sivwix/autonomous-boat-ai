"""Persist pre-cutoff four-leg evidence beside immutable BOAT LAB forecasts.

Evidence is research-only and stored separately from official predictions,
results and payouts. It reuses the already verified same-run BOATCAST capture;
this module must never fetch an already-finished race or invent observations.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import re

from scripts.four_leg_exhibition_evidence_research import assess
from scripts.original_exhibition_venue_research import digest

SCHEMA = "boatlabs.four_leg_forward_evidence.v0.1"
STATUS_SCHEMA = "boatlabs.four_leg_forward_status.v0.1"


def _iso_time(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError("timestamp must be timezone aware")
    return t


def merge_forward_evidence(previous: dict | None, ledger: dict,
                           captures: dict, *, event_date: str,
                           generated_at_utc: str) -> tuple[dict, dict]:
    """One research row per immutable frozen forecast SHA; never overwrite.

    For an existing row, retain the original evidence even when another
    source or data feed later changes. No official outcomes are read.
    """
    date.fromisoformat(event_date)
    now = _iso_time(generated_at_utc)
    if (now.date() != date.fromisoformat(event_date)
            and now.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Tokyo")).date()
            != date.fromisoformat(event_date)):
        raise ValueError("generation date disagrees with event date")
    if ledger.get("event_date") != event_date:
        raise ValueError("forecast ledger date mismatch")
    if not isinstance(captures, dict):
        raise ValueError("captures should be dict")
    if previous and previous.get("event_date") != event_date:
        raise ValueError("prior evidence date mismatch")
    prior = deepcopy(previous.get("race_versions") or {}) if previous else {}
    if not isinstance(prior, dict):
        raise ValueError("previous evidence shape mismatch")

    counts = {
        "captures_in_current_run": len(captures),
        "new_evidence_versions": 0,
        "preserved_evidence_versions": sum(len(v) for v in prior.values()
                                           if isinstance(v, dict)),
        "rejected_versions": 0,
    }
    errors = {}
    records = ledger.get("race_records") or {}
    for key, capture in sorted(captures.items()):
        record = records.get(key)
        if not isinstance(record, dict):
            errors[key] = "NO_MATCHING_FROZEN_FORECAST"
            continue
        if (record.get("venue_code") != str(int(capture.get("venue_code", -1)))
                or record.get("race") != capture.get("race_number")):
            errors[key] = "SOURCE_RACE_IDENTITY_MISMATCH"
            continue
        for version in record.get("versions") or []:
            if (not isinstance(version, dict)
                    or version.get("phase") != "exhibition"
                    or (version.get("exhibition_input_check") or {}).get(
                        "verified_before_freeze") is not True):
                continue
            # Provenance: the version must be demonstrably coupled to this
            # exact original capture, not merely any earlier preview.
            bound = version.get("original_exhibition_formal_v1") or {}
            input_check = version.get("exhibition_input_check") or {}
            has_bound_capture = bool(
                bound.get("capture_sha256") == digest(capture)
                and bound.get("measurement_sha256") == capture.get("measurement_sha256"))
            origin = version.get("exhibition_origin") or {}
            has_input_capture = bool(
                input_check.get("original_metrics_matched")
                and origin.get("original_exhibition_source") == "BOATCAST_direct"
                and origin.get("original_exhibition_measurement_sha256") ==
                    capture.get("measurement_sha256")
                and origin.get("original_exhibition_captured_at_utc") ==
                    capture.get("captured_at_utc")
                and version.get("model_version")
                and _iso_time(capture["captured_at_utc"]) <=
                    _iso_time(version["frozen_at_utc"])
                and not bound)
            if not (has_bound_capture or has_input_capture):
                continue
            frozen_sha = version.get("sha256")
            if not isinstance(frozen_sha, str) or re.fullmatch(r"[0-9a-f]{64}", frozen_sha) is None:
                counts["rejected_versions"] += 1
                errors[key] = "INVALID_FORECAST_SNAPSHOT_SHA"
                continue
            saved = prior.setdefault(key, {})
            if not isinstance(saved, dict):
                raise ValueError("corrupt immutable evidence for race")
            if frozen_sha in saved:
                continue
            try:
                evidence = assess(version, capture)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                counts["rejected_versions"] += 1
                errors[key] = type(exc).__name__ + ": " + str(exc)[:100]
                continue
            if evidence.get("status") != "SIX_BOAT_EVIDENCE_RESEARCH_ONLY":
                continue
            saved[frozen_sha] = {
                "forecast_snapshot_sha256": frozen_sha,
                "model_version": version.get("model_version"),
                "model_role": version.get("model_role"),
                "forecast_bets_sha256": digest(version.get("bets") or []),
                "forecast_frozen_at_utc": version["frozen_at_utc"],
                "evidence": evidence,
                "research_only": True,
                "formal_bets_unchanged": True,
                "not_an_actual_purchase": True,
                "postrace_result_used": False,
            }
            counts["new_evidence_versions"] += 1

    artifact = {
        "schema": SCHEMA,
        "event_date": event_date,
        "created_at_utc": (previous or {}).get("created_at_utc") or generated_at_utc,
        "race_versions": prior,
        "research_only": True,
        "formal_forecasts_untouched": True,
        "outcomes_payouts_not_used": True,
    }
    counts["total_evidence_versions"] = sum(len(v) for v in prior.values())
    counts["evidence_races"] = len([v for v in prior.values() if v])
    metric_counts = {metric: 0 for metric in (
        "lap_time", "half_lap_time", "turn_time", "straight_time")}
    venues = set()
    for per_race in prior.values():
        if not isinstance(per_race, dict):
            continue
        for row in per_race.values():
            ev = row.get("evidence") or {}
            venues.add(ev.get("venue"))
            for metric, status_value in (ev.get("original_metric_status") or {}).items():
                if metric in metric_counts and status_value == "SIX_BOAT_COMPLETE":
                    metric_counts[metric] += 1
    counts["six_boat_original_metric_coverage_versions"] = metric_counts
    counts["venues_with_evidence"] = len(venues - {None})
    counts["ikiasi_acceleration_independently_measured"] = 0
    counts["deashi_acceleration_independently_measured"] = 0
    counts["errors"] = errors
    status = {
        "schema": STATUS_SCHEMA, "event_date": event_date,
        "checked_at_utc": generated_at_utc,
        "source": "already_captured_same_run_BOATCAST_original_only",
        "status": "RESEARCH_ONLY_NOT_FORMAL",
        "normal_exhibition_and_original_required": True,
        "no_retroactive_source_fetch": True,
        "no_results_or_payouts_used": True,
        **counts,
    }
    return artifact, status
