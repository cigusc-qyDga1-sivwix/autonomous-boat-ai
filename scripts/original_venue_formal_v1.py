"""Forward-only BOAT LAB original-exhibition v1 scoring overlay.

Research-informed but NOT a trained coefficient set. A limited, explicitly
uncalibrated formal rule applies only to new six-boat, pre-cutoff snapshots,
preserving the learned-model control and separate policy SHA. Results/payouts
are neither imported nor used to construct predictions.

BOATCAST source is one live HTTP request per target. Bounded to avoid
uncontrolled site crawling. Usage terms must be reviewed before wider scale.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
import time
import unicodedata

from boat_ai.statistical import allocate, digest, distributions, prepare
from scripts.boatcast_oriten_smoke import probe
from scripts.entry_exhibition_gate import validated_preview
from scripts.learned_formal import ALLOWED_FIELDS, VERSION as LEARNED_VERSION, verify_model
from scripts.original_exhibition_venue_research import venue_features, VENUE_SPECS

POLICY = {
    "version": "original-exhibition-venue-v1-forward-heuristic",
    "stage1_straight": 0.04,
    "stage1_turn": 0.03,
    "stage2_turn": 0.09,
    "stage3_turn": 0.06,
    "stage3_lap_or_half": 0.025,
    "metric_scale_seconds": {
        "lap_time": 0.30, "half_lap_time": 0.20,
        "turn_time": 0.20, "straight_time": 0.09,
    },
    "max_absolute_log_multiplier": 0.20,
}
POLICY_SHA256 = digest(POLICY)
MAX_REQUESTS_PER_RUN = 6
REQUEST_TIMEOUT_SECONDS = 3
SOURCE_REQUEST_DELAY_SECONDS = 1.0


def _name(v):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(v or "")))


def _score(z, metric, lane):
    row = z.get(metric, {}).get(str(lane)) or {}
    x = row.get("advantage_over_race_median_seconds")
    if type(x) not in (float, int) or not math.isfinite(x):
        return 0.0
    cap = POLICY["metric_scale_seconds"][metric]
    return max(-1.0, min(1.0, x / cap))


def apply(snapshot: dict, learned_model: dict, capture: dict) -> dict:
    """Rescore the exact pre-cutoff learned distribution with provenance.

    Keep the same point count and 50,000-yen virtual allocation.
    The trained-model SHA is unchanged; the extra untrained scoring policy
    has its OWN SHA, so auditors cannot mistake it for retraining.
    """
    frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
    cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
    if (snapshot.get("phase") != "exhibition" or
            snapshot.get("model_version") != LEARNED_VERSION or
            frozen.tzinfo is None or cutoff.tzinfo is None or
            frozen >= cutoff - timedelta(minutes=2) or
            not verify_model(learned_model, frozen)):
        raise ValueError("not eligible learned exhibition")
    if not isinstance(capture, dict) or len(capture.get("boats") or []) != 6:
        raise ValueError("incomplete original six boats")
    code = next((c for c, p in VENUE_SPECS.items()
                 if p["venue"] == snapshot.get("venue")), None)
    if code is None or code == "03" or capture.get("venue_code") != code or (
            capture.get("race_number") != snapshot.get("race")):
        raise ValueError("venue/race mismatch")
    six = snapshot.get("racers")
    if not isinstance(six, list) or [r.get("lane") for r in six] != list(range(1, 7)):
        raise ValueError("six forecast racers missing")
    if not all(_name(six[i-1].get("name")) == _name(capture["boats"][i-1].get("name"))
               for i in range(1, 7)):
        raise ValueError("six racer names differ from official program")
    if (snapshot.get("exhibition_origin") or {}).get("captured_before_cutoff") is not True:
        raise ValueError("regular exhibition source not pre-cutoff")
    values = venue_features(capture, frozen_at_utc=snapshot["frozen_at_utc"],
                            cutoff_at_jst=snapshot["cutoff_iso_jst"])
    z = values["features"]
    if "turn_time" not in z or len(z["turn_time"]) != 6:
        raise ValueError("no six-boat original turn time")
    safe_input = {
        "phase": "exhibition",
        "racers": [{k: r.get(k) for k in ALLOWED_FIELDS} for r in six],
        "weather_used": {k: (snapshot.get("weather_used") or {}).get(k)
                         for k in ("wind_speed", "wave_height")},
    }
    prepare(safe_input)
    ranked = distributions(safe_input, learned_model)
    if len(ranked) != 120:
        raise ValueError("not canonical learned distribution")
    count = len(snapshot.get("bets") or [])
    if not 4 <= count <= 20 or sum(b["virtual_yen"] for b in snapshot["bets"]) != 50000:
        raise ValueError("invalid learned main stake")
    adjusted = []
    for r in ranked:
        first, second, third = (int(i) for i in r["combination"].split("-"))
        third_lap = "lap_time" if "lap_time" in z else (
            "half_lap_time" if "half_lap_time" in z else None)
        delta = (
            POLICY["stage1_straight"] * _score(z, "straight_time", first)
            + POLICY["stage1_turn"] * _score(z, "turn_time", first)
            + POLICY["stage2_turn"] * _score(z, "turn_time", second)
            + POLICY["stage3_turn"] * _score(z, "turn_time", third)
            + (POLICY["stage3_lap_or_half"] * _score(z, third_lap, third)
               if third_lap else 0.0)
        )
        delta = max(-POLICY["max_absolute_log_multiplier"],
                    min(POLICY["max_absolute_log_multiplier"], delta))
        adjusted.append({"combination": r["combination"],
                         "score": r["score"] * math.exp(delta)})
    adjusted.sort(key=lambda r: (-r["score"], r["combination"]))
    new_bets = allocate(adjusted, count, point_free=False, max_points=20)
    if len(new_bets) != count or sum(b["virtual_yen"] for b in new_bets) != 50000:
        raise ValueError("original v1 allocation corrupted")
    out = deepcopy(snapshot)
    original_bets = deepcopy(out["bets"])
    out["bets"] = new_bets
    # Identical learned weights are NOT an identical scoring policy.
    # Attribute composite inference separately for prospective audit.
    composite_sha = digest({"base_learned_model_sha256": learned_model["model_sha256"],
                            "original_v1_policy_sha256": POLICY_SHA256})
    out["learned_formal"]["inference_variant"] = "learned_plus_original_v1_untrained_overlay"
    out["learned_formal"]["composite_inference_sha256"] = composite_sha
    out["learned_formal"]["original_v1_coefficients_trained"] = False
    # Extra timing evidence has no trained coefficient yet: label honestly.
    out["point_reason"] += "／オリ展場別v1: まわり足・直線・一周/半周の限定再順位付け（未学習の係数・未校正）"
    out["scenario"] = ("オリ展場別v1上位 " + new_bets[0]["combination"]
                       + "（元学習モデル＋限定的な実測補正、性能未検証）")
    out["original_exhibition_formal_v1"] = {
        "version": POLICY["version"],
        "formal_component": True, "trained_coefficient": False,
        "coefficient_policy_sha256": POLICY_SHA256,
        "composite_inference_sha256": composite_sha,
        "base_learned_model_sha256": learned_model["model_sha256"],
        "capture_sha256": values["capture_sha256"],
        "source_body_sha256": capture.get("source_body_sha256"),
        "measurement_sha256": values["raw_measurement_sha256"],
        "source_url": values["source_url"],
        "captured_at_utc": values["captured_at_utc"],
        "frozen_at_utc": values["frozen_at_utc"],
        "venue_code": code, "race": snapshot["race"],
        "metrics_complete_six_boats": sorted(z.keys()),
        "missing_expected_metrics": [k for k, v in values["metric_status"].items()
                                     if v != "SIX_BOAT_COMPLETE"],
        "regular_exhibition_already_verified": True,
        "six_boat_names_matched_program": True,
        "same_time_base_bets": original_bets,
        "same_point_count": True, "virtual_stake_yen_each": 50000,
        "ticket_or_stake_changed": sorted((x["combination"], x["virtual_yen"]) for x in original_bets)
            != sorted((x["combination"], x["virtual_yen"]) for x in new_bets),
        "no_results_or_payouts_used": True,
        "pre_cutoff_only": True, "prospective_accuracy_improvement_unproven": True,
        "not_a_retrained_statistical_model": True,
    }
    return out


def collect_candidates(payload: dict, previous: dict | None, now: datetime,
                       *, request_limit: int = MAX_REQUESTS_PER_RUN,
                       timeout: int = REQUEST_TIMEOUT_SECONDS,
                       sleep_fn=time.sleep, probe_fn=probe) -> tuple[dict, dict]:
    """Bounded current-run HTTP capture, with no old-race or post-cutoff reads.

    Call from the *live* nationwide forecast only, not fixture replay.
    Only full six-boat OpenAPI previews are eligible and no duplicate
    source fetch is needed once the current day's v1 was immutably fixed.
    """
    if now.tzinfo is None:
        raise ValueError("timezone-aware now required")
    active = (payload.get("programs") or {}).get("stadiums") or {}
    today = now.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Tokyo")).date()
    records = (previous or {}).get("race_records") or {}
    targets = []
    for raw_code, stadium in active.items():
        try:
            code = f"{int(raw_code):02d}"
        except (TypeError, ValueError):
            continue
        if code not in VENUE_SPECS or code == "03":
            continue
        for raw_number, race in ((stadium or {}).get("races") or {}).items():
            try:
                number = int(raw_number)
                cutoff = datetime.strptime(race["closed_at"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Tokyo"))
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
            if not 1 <= number <= 12 or cutoff.date() != today:
                continue
            lead = cutoff - now
            if not timedelta(minutes=4) <= lead <= timedelta(minutes=20):
                continue
            if validated_preview(race.get("preview")) is None:
                continue
            versions = (records.get(f"{int(code)}-{number}") or {}).get("versions") or []
            if any((v.get("original_exhibition_formal_v1") or {}).get("formal_component")
                   for v in versions):
                continue
            targets.append((cutoff, code, number))
    targets.sort()
    captured = {}
    attempts = 0
    failures = {}
    for _, code, number in targets[:max(0, min(request_limit, 12))]:
        if attempts:
            sleep_fn(SOURCE_REQUEST_DELAY_SECONDS)
        attempts += 1
        result = probe_fn(today, int(code), number, timeout=timeout)
        if result.get("status") == "SIX_BOAT_PARSED_RESEARCH_ONLY":
            captured[f"{int(code)}-{number}"] = result
        else:
            failures[f"{int(code)}-{number}"] = result.get("reason") or result.get("status")
    return captured, {
        "version": POLICY["version"],
        "attempted": attempts,
        "captured_six_boat": len(captured),
        "failures": failures,
        "eligible_targets": len(targets),
        "requests_capped_per_run": MAX_REQUESTS_PER_RUN,
        "formal_eligibility_requires_same_race_6_names_and_freeze": True,
        "historical_results_used": False,
    }


def attach_to_live_race(race: dict, capture: dict, *, venue_code: str,
                        race_number: int, captured_by_forecast_at_utc: str) -> dict:
    """Validate source identity/names before ANY original value reaches legacy engine.

    A full legal six-boat normal exhibition remains the hard dependency.
    This is only a prospective source enrichment, never historical replay.
    """
    from scripts.original_exhibition_venue_research import VENUE_SPECS
    if venue_code not in VENUE_SPECS or venue_code == "03":
        raise ValueError("venue outside original v1 scope")
    if validated_preview(race.get("preview")) is None:
        raise ValueError("no complete six-boat normal exhibition")
    try:
        cutoff = datetime.strptime(race["closed_at"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Tokyo"))
    except (KeyError, TypeError, ValueError):
        raise ValueError("no valid cutoff")
    if capture.get("venue_code") != venue_code or capture.get("race_number") != race_number:
        raise ValueError("original source race mismatch")
    transformed = venue_features(
        capture, frozen_at_utc=captured_by_forecast_at_utc,
        cutoff_at_jst=cutoff.isoformat())
    if "turn_time" not in transformed["features"]:
        raise ValueError("six-boat original turn data missing")
    source = race.get("racers") or {}
    if not all(_name((source.get(str(lane)) or {}).get("name"))
               == _name((capture.get("boats") or [])[lane-1].get("name"))
               for lane in range(1, 7)):
        raise ValueError("original/normal six racer names disagree")
    out = deepcopy(race)
    out["_boatcast_original_capture"] = capture
    out["_exhibition_original"] = {
        metric: {str(b["lane"]): b[metric] for b in capture["boats"]}
        for metric in transformed["features"]
    }
    prior = out.get("_exhibition_origin") or {}
    out["_exhibition_origin"] = {
        **prior, "original_exhibition_source": "BOATCAST_direct",
        "original_exhibition_measurement_sha256": capture["measurement_sha256"],
        "original_exhibition_captured_at_utc": capture["captured_at_utc"],
        "original_exhibition_six_boat_program_names_matched": True,
        "metrics": sorted(out["_exhibition_original"]),
    }
    return out
