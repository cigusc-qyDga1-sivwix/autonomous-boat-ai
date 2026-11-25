"""Forward-only BOAT LAB original-exhibition v1 scoring overlay.

Bounded venue coefficients fit offline against past official finish orders.
Only current, pre-cutoff six-boat inputs reach inference. The learned-model
control and independent scoring-policy SHA are preserved.

BOATCAST source is one live HTTP request per target. Bounded to avoid
uncontrolled site crawling. Usage terms must be reviewed before wider scale.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import re
import time
import unicodedata

from boat_ai.statistical import allocate, digest, distributions, prepare
from scripts.boatcast_oriten_smoke import probe
from scripts.entry_exhibition_gate import validated_preview
from scripts.learned_formal import (
    ALLOWED_FIELDS, VERSION as LEARNED_VERSION, ranking_summary, verify_model,
)
from scripts.original_exhibition_venue_research import venue_features, VENUE_SPECS
from scripts.corner_attack_formal_v1 import rescore as corner_rescore, POLICY_SHA256 as CORNER_POLICY_SHA256
from scripts.race_flow_experimental_primary import rescore as rescore_experimental, POLICY_SHA256 as EXPERIMENT_POLICY_SHA
from scripts.expert_scenario_portfolio_shadow import build as build_expert_portfolio, promote_verified_experiment

PROFILE_PATH = Path(__file__).resolve().parents[1] / "config/original-venue-v1-profiles.json"
PROFILE_DATA = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
STAGES = ("first", "second", "third")
POLICY = {
    "version": "original-exhibition-venue-v1-venue-fit",
    "profiles": PROFILE_DATA,
    "metric_scale_seconds": {
        "lap_time": 0.30, "half_lap_time": 0.20,
        "turn_time": 0.20, "straight_time": 0.09,
    },
}
POLICY_SHA256 = digest(POLICY)
MAX_REQUESTS_PER_RUN = 6
REQUEST_TIMEOUT_SECONDS = 3
SOURCE_REQUEST_DELAY_SECONDS = 1.0


def _name(v):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(v or "")))


def _score(z, metric, lane):
    x = z[metric][str(lane)]["advantage_over_race_median_seconds"]
    cap = POLICY["metric_scale_seconds"][metric]
    return max(-1.0, min(1.0, x / cap))


def adjust_rankings(ranked: list[dict], features: dict, stage_weights: dict) -> list[dict]:
    """Apply each delta to its own conditional distribution."""
    first, second, third = (
        {lane: math.exp(sum(weight * _score(features, metric, lane)
                            for metric, weight in stage_weights[stage].items()))
         for lane in range(1, 7)}
        for stage in STAGES
    )
    rows = [(r["combination"], tuple(map(int, r["combination"].split("-"))), r["score"])
            for r in ranked]
    first_mass = defaultdict(float)
    pair_mass = defaultdict(float)
    third_normalizer = defaultdict(float)
    for _, (h, s, t), score in rows:
        first_mass[h] += score
        pair_mass[h, s] += score
        third_normalizer[h, s] += score * third[t]
    second_normalizer = defaultdict(float)
    for (h, s), score in pair_mass.items():
        second_normalizer[h] += score * second[s]
    first_normalizer = sum(score * first[h] for h, score in first_mass.items())

    adjusted = []
    for combo, (h, s, t), score in rows:
        first_factor = first[h] / first_normalizer
        second_factor = second[s] * first_mass[h] / second_normalizer[h]
        third_factor = third[t] * pair_mass[h, s] / third_normalizer[h, s]
        adjusted.append({"combination": combo, "score": score * first_factor * second_factor * third_factor})
    return sorted(adjusted, key=lambda r: (-r["score"], r["combination"]))


def apply(snapshot: dict, learned_model: dict, capture: dict) -> dict:
    """Rescore the exact pre-cutoff learned distribution with provenance.

    Keep the same point count and 50,000-yen virtual allocation.
    The stage weights belong to the independent venue policy. The existing
    base model still supplies the underlying conditional distribution.
    """
    frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
    cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
    if (snapshot.get("phase") != "exhibition" or
            snapshot.get("model_version") != LEARNED_VERSION or
            frozen.tzinfo is None or cutoff.tzinfo is None or
            frozen >= cutoff - timedelta(minutes=2) or
            cutoff.date() <= date.fromisoformat(PROFILE_DATA["trained_through_jst"]) or
            not verify_model(learned_model, frozen) or
            (snapshot.get("learned_formal") or {}).get("model_sha256") != learned_model["model_sha256"]):
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
    profile = PROFILE_DATA["venues"][code]
    stage_weights = {
        stage: {metric: weight for metric, weight in zip(profile["metrics"], weights)
                if metric in z and weight > 0}
        for stage, weights in zip(STAGES, profile["weights"])
    }
    if not any(stage_weights.values()):
        raise ValueError("no measured original metric used by the venue profile")
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
    adjusted = adjust_rankings(ranked, z, stage_weights)
    # Apply the same conservative 3-vs-4 and 4->5 signal as learned primary.
    # Recompute once from base+venue scores: never double-boost a learned
    # snapshot that was already corner-adjusted before original-v1 enrichment.
    corner_audit = {"applied": False}
    if (cutoff.date() >= date(2026, 11, 18)
            and frozen.astimezone(cutoff.tzinfo).date() >= date(2026, 11, 18)):
        adjusted, corner_audit = corner_rescore(adjusted, six)
    # Final learned+venue+corner stack gets ONE experimental rerank.
    # Rebuild from the same pre-cutoff inputs so previous experiment is not
    # stacked twice when this verified original exhibition capture arrives.
    experimental_audit = None
    experimental_control = None
    if (cutoff.date() >= date(2026, 11, 20)
            and frozen.astimezone(cutoff.tzinfo).date() >= date(2026, 11, 20)):
        experimental_control = allocate(adjusted, count, point_free=False, max_points=20)
        adjusted, experimental_audit = rescore_experimental(
            adjusted, six, frozen_at_utc=snapshot["frozen_at_utc"],
            cutoff_iso_jst=snapshot["cutoff_iso_jst"],
            exhibition_verified=True)
    new_bets = allocate(adjusted, count, point_free=False, max_points=20)
    if len(new_bets) != count or sum(b["virtual_yen"] for b in new_bets) != 50000:
        raise ValueError("original v1 allocation corrupted")
    out = deepcopy(snapshot)
    original_bets = deepcopy(out["bets"])
    out["bets"] = new_bets
    out.update(ranking_summary(adjusted, six, "オリ展場別v1補正後の相対評価・確率校正前"))
    composite_input = {"base_learned_model_sha256": learned_model["model_sha256"],
                       "original_v1_policy_sha256": POLICY_SHA256}
    if corner_audit.get("applied"):
        composite_input["corner_guard_policy_sha256"] = CORNER_POLICY_SHA256
        out["corner_attack_formal_v1"] = corner_audit
        out["learned_formal"]["corner_guard_policy_sha256"] = CORNER_POLICY_SHA256
    if (experimental_audit is not None
            and experimental_audit["status"] == "APPLIED_EXPERIMENTAL_UNCALIBRATED"):
        composite_input["race_flow_experiment_policy_sha256"] = EXPERIMENT_POLICY_SHA
    composite_sha = digest(composite_input)
    out["learned_formal"]["inference_variant"] = (
        "learned_plus_original_v1_venue_fit_plus_corner_guard_v1"
        if corner_audit.get("applied") else "learned_plus_original_v1_venue_fit")
    if experimental_audit is not None:
        changed = sorted((b["combination"], b["virtual_yen"]) for b in new_bets) != sorted(
            (b["combination"], b["virtual_yen"]) for b in experimental_control)
        applied = experimental_audit["status"] == "APPLIED_EXPERIMENTAL_UNCALIBRATED"
        out["experimental_race_flow"] = {
            **experimental_audit, "formal_component": applied,
            "formal_bets_changed": changed,
            "first_ticket_head_changed": new_bets[0]["combination"][0] != experimental_control[0]["combination"][0],
            "same_time_control_bets": experimental_control,
            "control_bets_sha256": digest(experimental_control),
            "experimental_bets_sha256": digest(new_bets),
            "same_point_count": len(new_bets) == len(experimental_control),
            "same_virtual_stake_yen": 50000,
            "not_an_actual_purchase": True, "no_historical_overwrite": True,
        }
        if applied:
            out["learned_formal"]["inference_variant"] += "+race-flow-head-experiment-v1"
    out["learned_formal"]["composite_inference_sha256"] = composite_sha
    out["learned_formal"]["original_v1_coefficients_trained"] = True
    out["point_reason"] += "／オリ展場別v1で出走6艇の実測を着順ごとに補正（未校正）"
    if corner_audit.get("applied") and not (snapshot.get("corner_attack_formal_v1") or {}).get("applied"):
        out["point_reason"] += "／3・4コース攻防・5コース追走を小幅補正（未校正）"
    out["scenario"] = (f"{snapshot['venue']} オリ展場別v1反映・上位 {new_bets[0]['combination']}"
                       "（1着・2着・3着を個別補正）")
    if (experimental_audit is not None
            and experimental_audit["status"] == "APPLIED_EXPERIMENTAL_UNCALIBRATED"):
        out["scenario"] = "【展開実験v1・未校正】" + out["scenario"]
        out["point_reason"] += "／オリ展補正後に外頭・内残りを展開実験で再配分（対照保存）"
    out["original_exhibition_formal_v1"] = {
        "version": POLICY["version"],
        "formal_component": True, "trained_coefficient": True,
        "coefficient_policy_sha256": POLICY_SHA256,
        "corner_guard_policy_sha256": CORNER_POLICY_SHA256 if corner_audit.get("applied") else None,
        "composite_inference_sha256": composite_sha,
        "base_learned_model_sha256": learned_model["model_sha256"],
        "profile_training_races": profile["training_races"],
        "profile_trained_through_jst": PROFILE_DATA["trained_through_jst"],
        "profile_stage_weights": stage_weights,
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
    # Rebuild the expert allocation from FINAL venue-adjusted, corner-adjusted,
    # race-flow scores exactly ONCE: do not compound a prior learned portfolio.
    out.pop("expert_scenario_portfolio_formal", None)
    out.pop("expert_scenario_portfolio_shadow", None)
    try:
        expert = build_expert_portfolio(out, adjusted)
        if expert is not None:
            if expert.get("status") == "PRE_CUTOFF_COUNTER_PATH_FROZEN":
                out = promote_verified_experiment(out, expert)
            else:
                out["expert_scenario_portfolio_shadow"] = expert
    except (ValueError, KeyError, TypeError, OverflowError):
        out["expert_scenario_portfolio_shadow"] = {
            "model_role": "research_shadow", "status": "ERROR_FAIL_CLOSED",
            "not_formal": True, "bets_modified": False,
            "no_results_used": True, "no_odds_used": True,
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
    excluded = {"outside_time_window": 0, "normal_exhibition_incomplete": 0,
                "already_frozen": 0}
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
                excluded["outside_time_window"] += 1
                continue
            if validated_preview(race.get("preview")) is None:
                excluded["normal_exhibition_incomplete"] += 1
                continue
            versions = (records.get(f"{int(code)}-{number}") or {}).get("versions") or []
            if any((v.get("original_exhibition_formal_v1") or {}).get("formal_component")
                   for v in versions):
                excluded["already_frozen"] += 1
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
        "excluded_target_counts": excluded,
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
