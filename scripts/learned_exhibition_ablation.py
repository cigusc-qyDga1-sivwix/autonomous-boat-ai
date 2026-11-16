"""Research-only same-time learned-main exhibition ablation.

At the same verified, pre-cutoff six-boat snapshot, contrast the actual learned
main with identical trained weights and no exhibition times/ST. This is NOT a
previously frozen baseline, nor evidence of profitable improved prediction.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from boat_ai.statistical import allocate, digest, distributions, prepare
from scripts.learned_formal import ALLOWED_FIELDS, VERSION as LEARNED_MAIN, verify_model

VERSION = "learned-exhibition-effect-shadow-v0.1"
ALLOWED_SHADOW_PHASES = frozenset({"exhibition"})


def build(snapshot: dict, model: dict) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("model_version") != LEARNED_MAIN:
        raise ValueError("no_learned_main")
    frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
    cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
    check = snapshot.get("exhibition_input_check") or {}
    if (frozen.tzinfo is None or cutoff.tzinfo is None
            or not frozen <= cutoff - timedelta(seconds=120)
            or snapshot.get("phase") not in ALLOWED_SHADOW_PHASES
            or check.get("verified_before_freeze") is not True
            or check.get("six_boats_matched") != 6
            or not verify_model(model, frozen)
            or (snapshot.get("learned_formal") or {}).get("model_sha256") != model["model_sha256"]):
        raise ValueError("not_eligible_pre_cutoff_verified_exhibition")
    racers = snapshot.get("racers")
    if (not isinstance(racers, list) or len(racers) != 6
            or any(not isinstance(r, dict) for r in racers)):
        raise ValueError("missing_six_boats")
    current = snapshot.get("bets")
    if (not isinstance(current, list) or not 4 <= len(current) <= 20
            or any(not isinstance(b, dict) or type(b.get("virtual_yen")) is not int for b in current)
            or sum(b["virtual_yen"] for b in current) != 50000):
        raise ValueError("invalid_main_allocation")

    weather = {k: (snapshot.get("weather_used") or {}).get(k)
               for k in ("wind_speed", "wave_height")}
    source_boats = [{k: r.get(k) for k in ALLOWED_FIELDS} for r in racers]
    factual = {"phase": "exhibition", "racers": deepcopy(source_boats),
               "weather_used": deepcopy(weather)}
    no_exhibition_boats = deepcopy(source_boats)
    for r in no_exhibition_boats:
        r["exhibition_time"] = None
        r["exhibition_st"] = None
    without = {"phase": "baseline", "racers": no_exhibition_boats,
               "weather_used": deepcopy(weather)}
    prepare(factual)
    prepare(without)
    full = distributions(factual, model)
    without_ranked = distributions(without, model)
    count = len(current)
    # Guard against an unexpected formal inference change: only an EXACT
    # contemporaneous model rerun is a valid ablation control.
    reconstructed = allocate(full, count, point_free=False, max_points=20)
    signature = lambda bs: tuple(sorted((b["combination"], b["virtual_yen"]) for b in bs))
    if signature(reconstructed) != signature(current):
        raise ValueError("main_model_not_reproducible")
    no_exhibition_bets = allocate(without_ranked, count, point_free=False, max_points=20)
    if (len(no_exhibition_bets) != count
            or sum(b["virtual_yen"] for b in no_exhibition_bets) != 50000
            or any(b["virtual_yen"] < 1000 or b["virtual_yen"] % 1000
                   for b in no_exhibition_bets)):
        raise ValueError("invalid_ablation_allocation")

    actual = signature(current)
    counter = signature(no_exhibition_bets)
    return {
        "version": VERSION,
        "model_role": "research_shadow",
        "status": "EXHIBITION_CHANGED_TICKETS" if actual != counter else "NO_TICKET_CHANGE",
        "learned_model_version": LEARNED_MAIN,
        "model_sha256": model["model_sha256"],
        "frozen_at_utc": snapshot["frozen_at_utc"],
        "factual_input_sha256": digest(factual),
        "no_exhibition_input_sha256": digest(without),
        "source_snapshot_sha256": digest({
            "racers": racers,
            "exhibition_origin": snapshot.get("exhibition_origin"),
            "exhibition_input_check": check,
        }),
        "formal_bets": deepcopy(current),
        "no_exhibition_bets": no_exhibition_bets,
        "formal_bets_sha256": digest(current),
        "no_exhibition_bets_sha256": digest(no_exhibition_bets),
        "same_model_same_time": True,
        "same_point_count": True,
        "virtual_budget_yen_each": 50000,
        "actual_ticket_or_stake_changed": actual != counter,
        "first_ticket_changed": current[0]["combination"] != no_exhibition_bets[0]["combination"],
        "first_head_changed": current[0]["combination"][0] != no_exhibition_bets[0]["combination"][0],
        "formal_tickets_changed": False,
        "classification_changed": False,
        "official_result_used": False,
        "odds_used": False,
        "calibrated": False,
        "source_confirmed": True,
        "not_a_historical_frozen_baseline": True,
        "not_an_actual_purchase": True,
        "needs_prospective_100r_comparison": True,
    }
