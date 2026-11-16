"""Pre-cutoff head-preserving 1M pair shadow for the learned BOAT LAB main.

Uses the exact learned distribution and the existing evidence-gated v2.6
conditional reranker. Runs only AFTER six-boat exhibition source verification.
Never replaces main bets, changes classification, or feeds back race outcomes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from boat_ai.statistical import allocate, digest, distributions, prepare
from scripts.conditional_one_mark_v26 import rescore
from scripts.learned_formal import ALLOWED_FIELDS, VERSION as LEARNED_VERSION, verify_model

VERSION = "learned-conditional-pair-shadow-v0.1"


def build(snapshot: dict, model: dict) -> dict:
    """Freeze same-time control and alternative; reject unverified sources."""
    if not isinstance(snapshot, dict):
        raise ValueError("invalid_snapshot")
    frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
    cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
    if (snapshot.get("model_version") != LEARNED_VERSION
            or snapshot.get("phase") != "exhibition"
            or not verify_model(model, frozen)
            or (snapshot.get("learned_formal") or {}).get("model_sha256") != model["model_sha256"]
            or (snapshot.get("exhibition_input_check") or {}).get("verified_before_freeze") is not True
            or (snapshot.get("exhibition_input_check") or {}).get("six_boats_matched") != 6):
        raise ValueError("no_verified_learned_exhibition")
    racers = snapshot.get("racers")
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("missing_six_boats")
    bets = snapshot.get("bets")
    if (not isinstance(bets, list) or not 4 <= len(bets) <= 20
            or sum(x["virtual_yen"] for x in bets) != 50000):
        raise ValueError("invalid_main_bets")
    safe_input = {
        "phase": "exhibition",
        "racers": [{k: r.get(k) for k in ALLOWED_FIELDS} for r in racers],
        "weather_used": {k: (snapshot.get("weather_used") or {}).get(k)
                         for k in ("wind_speed", "wave_height")},
    }
    prepare(safe_input)
    ranked = distributions(safe_input, model)
    alternative, evidence = rescore(
        [{"combination": x["combination"], "relative_score": x["score"]} for x in ranked],
        racers,
        frozen_at_utc=snapshot["frozen_at_utc"],
        cutoff_at_utc=snapshot["cutoff_iso_jst"],
    )
    trial_ranked = [{"combination": x["combination"], "score": x["relative_score"]}
                    for x in alternative]
    trial_bets = allocate(trial_ranked, len(bets), point_free=False, max_points=20)
    if (len(trial_bets) != len(bets)
            or sum(x["virtual_yen"] for x in trial_bets) != 50000
            or any(x["virtual_yen"] % 1000 or x["virtual_yen"] < 1000 for x in trial_bets)):
        raise ValueError("invalid_shadow_allocation")
    if evidence.get("head_marginal_max_error", 0) > 1e-8:
        raise ValueError("head_marginal_changed")
    signature = lambda xs: sorted((x["combination"], x["virtual_yen"]) for x in xs)
    changed = signature(trial_bets) != signature(bets)
    return {
        "version": VERSION,
        "model_role": "research_shadow",
        "status": "CHANGED_SHADOW_ONLY" if changed else "NO_TICKET_CHANGE",
        "conditional_status": evidence["status"],
        "conditional_evidence": evidence["evidence"],
        "head_marginals_preserved": True,
        "head_marginal_max_error": evidence.get("head_marginal_max_error", 0),
        "model_sha256": model["model_sha256"],
        "frozen_at_utc": snapshot["frozen_at_utc"],
        "input_sha256": digest(safe_input),
        "source_snapshot_sha256": digest({
            "racers": racers,
            "exhibition_origin": snapshot.get("exhibition_origin"),
            "exhibition_input_check": snapshot["exhibition_input_check"],
        }),
        "control_bets": deepcopy(bets),
        "shadow_bets": trial_bets,
        "shadow_bets_sha256": digest(trial_bets),
        "same_input_same_time": True,
        "same_point_count": True,
        "virtual_stake_yen_each": 50000,
        "ticket_changed_in_shadow": changed,
        "formal_tickets_changed": False,
        "classification_changed": False,
        "official_results_used": False,
        "odds_used": False,
        "calibrated": False,
        "not_an_actual_purchase": True,
        "prospective_validation_required": True,
    }
