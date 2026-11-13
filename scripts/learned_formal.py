"""User-authorized forward-only learned PRIMARY inference for BOAT LAB.

Never retrain here, never read payouts or outcomes, and never rewrite a saved
forecast. A fresh pre-trained, hash-verified model may supersede the heuristic
on NEW pre-cutoff snapshots only. Exhibition eligibility remains separate.
"""
from __future__ import annotations

import math
import json
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

from boat_ai.statistical import (
    SCHEMA, FEATURES, digest, distributions, allocate, prepare,
)

VERSION = "four-factor-learned-v1-conditional-choice-trained"
START_DATE = date(2026, 11, 13)
MODEL_PATH = Path("app/data/statistical/latest-model.json")
ALLOWED_FIELDS = (
    "lane", "course", "national_win_rate", "motor_top_2_percent",
    "average_start_timing", "average_start_timing_imputed",
    "exhibition_time", "exhibition_st",
)


def verify_model(model: dict, now: datetime) -> bool:
    """Fail closed for corrupt, future-trained or stale models."""
    try:
        if now.tzinfo is None or not isinstance(model, dict):
            return False
        if (model.get("schema") != SCHEMA or model.get("features") != FEATURES
                or model.get("role") != "research_shadow"
                or model.get("calibrated") is not False):
            return False
        sha = model.get("model_sha256")
        if not isinstance(sha, str) or sha != digest({
                k: v for k, v in model.items() if k != "model_sha256"}):
            return False
        created = datetime.fromisoformat(model["created_at_utc"])
        through = date.fromisoformat(model["trained_through"])
        today = now.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Tokyo")).date()
        if (created.tzinfo is None or created > now or
                today < START_DATE or
                through >= today or through < today - timedelta(days=2) or
                type(model.get("training_n")) is not int or model["training_n"] < 100):
            return False
        weights = model["weights"]
        if (not isinstance(weights, list) or len(weights) != 3 or
                any(not isinstance(w, list) or len(w) != len(FEATURES)
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           for v in w) for w in weights)):
            return False
        return True
    except (TypeError, ValueError, KeyError, OverflowError):
        return False


def load_model(now: datetime, path: Path = MODEL_PATH) -> dict | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if verify_model(raw, now) else None
    except (OSError, ValueError, TypeError):
        return None


def apply(snapshot: dict, model: dict) -> dict:
    """Make the learned model the main 3連単 ticket selection, same budget.

    Legacy main is preserved as a same-time control. Training results never
    enter the race features. A complete pre-cutoff frozen input is mandatory.
    """
    frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
    cutoff = datetime.fromisoformat(snapshot["cutoff_iso_jst"])
    if (frozen.tzinfo is None or cutoff.tzinfo is None or
            frozen >= cutoff - timedelta(minutes=2) or
            not verify_model(model, frozen)):
        raise ValueError("learned formal model is not pre-cutoff eligible")
    racers = snapshot.get("racers")
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("six racers required for learned primary")
    safe_input = {
        "phase": snapshot["phase"],
        "racers": [{k: r.get(k) for k in ALLOWED_FIELDS}
                   for r in racers],
        "weather_used": {k: (snapshot.get("weather_used") or {}).get(k)
                         for k in ("wind_speed", "wave_height")}
    }
    # prepare() checks unique actual courses. No results, payouts or odds pass.
    prepare(safe_input)
    ranked = distributions(safe_input, model)
    if len(ranked) != 120:
        raise ValueError("learned primary needs canonical 120 rankings")
    prior_bets = snapshot["bets"]
    count = len(prior_bets)
    if not 4 <= count <= 20 or sum(b["virtual_yen"] for b in prior_bets) != 50000:
        raise ValueError("invalid previous main allocation")
    bets = allocate(ranked, count, point_free=False, max_points=20)
    if (len(bets) != count or sum(b["virtual_yen"] for b in bets) != 50000
            or any(b["virtual_yen"] < 1000 or b["virtual_yen"] % 1000
                   for b in bets)):
        raise ValueError("invalid learned main allocation")
    result = deepcopy(snapshot)
    before = result["model_version"]
    control = deepcopy(prior_bets)
    shares = []
    role = {}
    for lane in range(1, 7):
        indexed = [r for r in ranked if str(lane) in r["combination"].split("-")]
        first = sum(r["score"] for r in ranked
                    if r["combination"].split("-")[0] == str(lane))
        second = sum(r["score"] for r in ranked
                     if r["combination"].split("-")[1] == str(lane))
        third = sum(r["score"] for r in ranked
                    if r["combination"].split("-")[2] == str(lane))
        shares.append({"lane": lane, "course": racers[lane-1]["course"],
                       "relative_share": first})
        role[str(lane)] = {"first": first, "second": second, "third": third,
                           "note": "学習済み相対順位・確率校正前"}
    sorted_heads = sorted((x["relative_share"] for x in shares), reverse=True)
    result.update({
        "model_version": VERSION,
        "model_role": "main",
        "bets": bets,
        "point_count": count,
        "point_reason": ("統計学習モデルで1着→2着→3着を条件付き再評価。"
                         + str(count) + "点は旧正式モデルの点数と一致／仮想5万円・未校正"),
        "head_course_shares": shares,
        "role_coverage": role,
        "head_weight_concentration": round(sorted_heads[0], 4),
        "head_weight_gap": round(sorted_heads[0]-sorted_heads[1], 4),
        "scenario": ("学習済みモデルの上位候補 "
                     + bets[0]["combination"]
                     + "（1着→2着→3着の条件付き評価、未校正）"),
        "classification": "WATCH",  # No odds/edge calibration; do not auto BUY.
        "relative_scores_uncalibrated": True,
        "learned_formal": {
            "model_version": VERSION,
            "model_sha256": model["model_sha256"],
            "model_created_at_utc": model["created_at_utc"],
            "trained_through": model["trained_through"],
            "training_n": model["training_n"],
            "input_frozen_at_utc": snapshot["frozen_at_utc"],
            "model_role": "formal_primary",
            "promotion_basis": "explicit_user_authorized_forward_only",
            "control_model_version": before,
            "control_bets": control,
            "control_classification": snapshot["classification"],
            "same_input_same_time": True,
            "same_point_count": True,
            "virtual_stake_per_model_yen": 50000,
            "not_an_actual_purchase": True,
            "result_data_used": False,
            "odds_used": False,
            "calibrated": False,
            "performance_improvement_unproven": True,
            "no_historical_prediction_overwrite": True,
        }
    })
    # Old-model diagnostics must not be represented as learned-model evidence.
    for key in ("interaction_primary", "three_leg_primary",
                "formal_insight_v24", "formal_head_risk_v25",
                "formal_conditional_v26", "strong_field_diagnostic",
                "coverage_reselection_shadow", "hidden_path_shadow",
                "attack_defence_shadow", "grade_competition_shadow",
                "weather_special_shadow", "role_skill_shadow",
                "venue_motor_exhibition_shadow"):
        result.pop(key, None)
    return result
