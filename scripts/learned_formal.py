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
from scripts.third_place_pilot import load_pilot, frozen_shadow
from scripts.inside_survival_research import evaluate as evaluate_inside_survival
from scripts.corner_attack_formal_v1 import rescore as corner_rescore, POLICY_SHA256 as CORNER_POLICY_SHA256
from scripts.race_flow_experimental_primary import rescore as rescore_experimental, POLICY_SHA256 as EXPERIMENT_POLICY_SHA
from scripts.learned_wind_direction_v1 import rescore as rescore_learned_wind, POLICY_SHA256 as WIND_POLICY_SHA
from scripts.expert_scenario_portfolio_shadow import build as build_expert_portfolio, promote_verified_experiment
from scripts.outside_head_forward_shadow_v1 import build as build_outside_head_shadow

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


def ranking_summary(ranked: list[dict], racers: list[dict], note: str) -> dict:
    classified = [(r["combination"].split("-"), r["score"]) for r in ranked]
    shares = []
    roles = {}
    for racer in sorted(racers, key=lambda r: r["lane"]):
        lane = racer["lane"]
        first, second, third = (
            sum(score for combo, score in classified if combo[stage] == str(lane))
            for stage in range(3)
        )
        shares.append({"lane": lane, "course": racer["course"], "relative_share": first})
        roles[str(lane)] = {"first": first, "second": second, "third": third, "note": note}
    heads = sorted((x["relative_share"] for x in shares), reverse=True)
    return {
        "head_course_shares": shares,
        "role_coverage": roles,
        "head_weight_concentration": round(heads[0], 4),
        "head_weight_gap": round(heads[0] - heads[1], 4),
    }


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
    # Only freshly verified pre-cutoff six-boat exhibition input may affect
    # formal tickets. This provisional corner/guard rule uses no outcomes.
    corner_audit = None
    if (snapshot.get("phase") == "exhibition"
            and cutoff.date() >= date(2026, 11, 18)
            and frozen.astimezone(cutoff.tzinfo).date() >= date(2026, 11, 18)
            and (snapshot.get("exhibition_origin") or {}).get("captured_before_cutoff") is True):
        ranked, corner_audit = corner_rescore(ranked, racers)
    prior_bets = snapshot["bets"]
    count = len(prior_bets)
    if not 4 <= count <= 20 or sum(b["virtual_yen"] for b in prior_bets) != 50000:
        raise ValueError("invalid previous main allocation")
    # Explicit 20 Nov forward experiment: verified exhibition only, not a
    # retroactive recalculation or a trained improvement claim. Freeze the
    # unchanged learned+corner control before experimental head reranking.
    experimental_audit = None
    experimental_control = None
    if (snapshot.get("phase") == "exhibition"
            and cutoff.date() >= date(2026, 11, 20)
            and frozen.astimezone(cutoff.tzinfo).date() >= date(2026, 11, 20)):
        experimental_control = allocate(ranked, count, point_free=False, max_points=20)
        ranked, experimental_audit = rescore_experimental(
            ranked, racers, frozen_at_utc=snapshot["frozen_at_utc"],
            cutoff_iso_jst=snapshot["cutoff_iso_jst"],
            exhibition_verified=(snapshot.get("exhibition_origin") or {}).get("captured_before_cutoff") is True)
    bets = allocate(ranked, count, point_free=False, max_points=20)
    if (len(bets) != count or sum(b["virtual_yen"] for b in bets) != 50000
            or any(b["virtual_yen"] < 1000 or b["virtual_yen"] % 1000
                   for b in bets)):
        raise ValueError("invalid learned main allocation")
    result = deepcopy(snapshot)
    # Strict inference boundary: historical outcomes/market fields must not
    # change ANY downstream expert-portfolio branch, nor leak into a forecast.
    # Keep these in the separate official-result ledger only.
    for postrace_key in ("result", "finish", "actual_finish", "actual_start",
                         "official_pay", "payout", "odds", "kimarite",
                         "actual_tactic", "observed_maneuver"):
        result.pop(postrace_key, None)
    before = result["model_version"]
    control = deepcopy(prior_bets)
    result.update({
        "model_version": VERSION,
        "model_role": "main",
        "bets": bets,
        "point_count": count,
        "point_reason": ("統計学習モデルで1着→2着→3着を条件付き再評価。"
                         + str(count) + "点は旧正式モデルの点数と一致／仮想5万円・未校正"),
        **ranking_summary(ranked, racers, "学習済み相対順位・確率校正前"),
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
    if corner_audit and corner_audit.get("applied"):
        result["corner_attack_formal_v1"] = corner_audit
        result["learned_formal"]["inference_variant"] = "learned_plus_corner_guard_forward_v1"
        result["learned_formal"]["corner_guard_policy_sha256"] = CORNER_POLICY_SHA256
        result["learned_formal"]["composite_inference_sha256"] = digest({
            "base_learned_model_sha256": model["model_sha256"],
            "corner_guard_policy_sha256": CORNER_POLICY_SHA256,
        })
        result["point_reason"] += "／3・4コース攻防を発走前展示で小幅補正（未校正）"
    if experimental_audit is not None:
        changed = sorted((b["combination"], b["virtual_yen"]) for b in bets) != sorted(
            (b["combination"], b["virtual_yen"]) for b in experimental_control)
        applied = experimental_audit["status"] == "APPLIED_EXPERIMENTAL_UNCALIBRATED"
        result["experimental_race_flow"] = {
            **experimental_audit,
            "formal_component": applied,
            "formal_bets_changed": changed,
            "first_ticket_head_changed": bets[0]["combination"][0] != experimental_control[0]["combination"][0],
            "same_time_control_bets": experimental_control,
            "control_bets_sha256": digest(experimental_control),
            "experimental_bets_sha256": digest(bets),
            "same_point_count": len(bets) == len(experimental_control),
            "same_virtual_stake_yen": 50000,
            "not_an_actual_purchase": True,
            "no_historical_overwrite": True,
        }
        if applied:
            result["learned_formal"]["inference_variant"] = (
                result["learned_formal"].get("inference_variant", "learned")
                + "+race-flow-head-experiment-v1")
            result["learned_formal"]["composite_inference_sha256"] = digest({
                "base_learned_model_sha256": model["model_sha256"],
                "corner_guard_policy_sha256": (
                    CORNER_POLICY_SHA256 if corner_audit and corner_audit.get("applied") else None),
                "race_flow_experiment_policy_sha256": EXPERIMENT_POLICY_SHA,
            })
            result["scenario"] = "【展開実験v1・未校正】攻防予兆で頭を再評価・上位 " + bets[0]["combination"]
            result["point_reason"] += "／展開実験v1で外頭・内残りを再配分（旧買い目保存）"
    # Old-model diagnostics must not be represented as learned-model evidence.
    for key in ("interaction_primary", "three_leg_primary",
                "formal_insight_v24", "formal_head_risk_v25",
                "formal_conditional_v26", "strong_field_diagnostic",
                "coverage_reselection_shadow", "hidden_path_shadow",
                "attack_defence_shadow", "grade_competition_shadow",
                "weather_special_shadow", "role_skill_shadow",
                "venue_motor_exhibition_shadow"):
        result.pop(key, None)
    # The historical SHA-verified learned model already uses wind speed/wave.
    # Apply a separately disclosed, bounded direction hypothesis ONLY to NEW
    # verified pre-cutoff OpenAPI exhibition rows. Do not backfill old results
    # or change existing frozen forecasts. The preceding learned/race-flow
    # forecast is the immutable same-time A/B control for this new policy.
    wind_control_result = deepcopy(result)
    wind_control_ranked = [dict(row) for row in ranked]
    wind_audit = None
    if snapshot.get("phase") == "exhibition":
        try:
            adjusted_ranked, wind_audit = rescore_learned_wind(ranked, result)
            if wind_audit["status"] == "APPLIED_FORWARD_UNCALIBRATED":
                wind_bets = allocate(adjusted_ranked, count, point_free=False, max_points=20)
                if (len(wind_bets) != count
                        or sum(b["virtual_yen"] for b in wind_bets) != 50000
                        or any(b["virtual_yen"] < 1000 or b["virtual_yen"] % 1000
                               for b in wind_bets)):
                    raise ValueError("wind_forward_budget_invariant")
                ranked = adjusted_ranked
                result["bets"] = wind_bets
                result.update(ranking_summary(
                    ranked, racers, "保存済み学習係数＋風向別前向き補正・未校正"))
                result["point_reason"] += (
                    "／学習済み風速・波高効果を維持し、場内の追い風・向かい風別に"
                    "3連単順位・配分を再計算（未校正）")
                result["scenario"] = (
                    "【学習済み＋風向補正v0.1】第一候補 "
                    + wind_bets[0]["combination"] + "（未校正）")
                meta = result["learned_formal"]
                before_wind_sha = meta.get("composite_inference_sha256") or model["model_sha256"]
                meta["inference_variant"] = (
                    meta.get("inference_variant", "learned")
                    + "+learned-wind-direction-forward-v01")
                meta["wind_direction_policy_sha256"] = WIND_POLICY_SHA
                meta["wind_direction_base_training_n"] = model["training_n"]
                meta["wind_direction_effect_trained"] = False
                meta["composite_inference_sha256"] = digest({
                    "prior_inference_sha256": before_wind_sha,
                    "wind_direction_policy_sha256": WIND_POLICY_SHA,
                    "trained_model_sha256": model["model_sha256"],
                })
        except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
            # Never allow a new wind hypothesis to corrupt a formal forecast.
            result = wind_control_result
            ranked = wind_control_ranked
            wind_audit = {
                "version": "learned-relative-wind-formal-v0.1-forward-uncalibrated",
                "status": "ERROR_FAIL_CLOSED",
                "error_type": type(exc).__name__,
                "formal_component": False,
                "result_data_used": False,
                "calibrated": False,
            }
    # A separately trained, pre-cutoff third-place experiment. Never changes
    # learned-formal tickets, classification, or the existing 50,000-yen stake.
    pilot = load_pilot(model, frozen)
    if pilot is not None:
        try:
            result["third_place_pilot"] = frozen_shadow(result, model, pilot)
        except (ValueError, TypeError, KeyError, OverflowError):
            pass  # Research-only artifact fails closed; formal remains intact.
    # Independent pre-cutoff lane-1 outcome/survival hypotheses.
    # Diagnostic only: all formal 3連単 bets, allocations, and model SHA stay put.
    if snapshot.get("phase") == "exhibition":
        try:
            result["inside_survival_research"] = evaluate_inside_survival(
                result, ranked, result["bets"])
        except (ValueError, TypeError, KeyError, OverflowError):
            result["inside_survival_research"] = {
                "version": "inside-survival-forward-shadow-v0.1",
                "model_role": "research_shadow",
                "status": "ERROR_FAIL_CLOSED",
                "formal_tickets_changed": False,
                "result_data_used": False,
                "calibrated": False,
            }
    # A same-time two-path allocation experiment. No historical data, odds,
    # results or real purchases enter the portfolio. The frozen learned-main
    # control stays in source metadata even when new formal tickets differ.
    if snapshot.get("phase") == "exhibition":
        try:
            expert = build_expert_portfolio(result, ranked)
            if expert is not None:
                if expert.get("status") == "PRE_CUTOFF_COUNTER_PATH_FROZEN":
                    result = promote_verified_experiment(result, expert)
                else:
                    result["expert_scenario_portfolio_shadow"] = expert
        except (ValueError, KeyError, TypeError, OverflowError):
            result["expert_scenario_portfolio_shadow"] = {
                "model_role": "research_shadow", "status": "ERROR_FAIL_CLOSED",
                "not_formal": True, "bets_modified": False,
                "no_results_used": True, "no_odds_used": True,
            }
    # Compare FINAL tickets against a same-time *no wind-direction*
    # counterfactual, including the preexisting expert portfolio policy.
    # This comparison is not historical outcome-based or a second actual stake.
    if wind_audit is not None:
        if wind_audit.get("status") == "APPLIED_FORWARD_UNCALIBRATED":
            comparison_status = "MATCHED_SAME_TIME"
            try:
                control_trial = build_expert_portfolio(
                    wind_control_result, wind_control_ranked)
                control_result = (
                    promote_verified_experiment(wind_control_result, control_trial)
                    if control_trial is not None
                    and control_trial.get("status") == "PRE_CUTOFF_COUNTER_PATH_FROZEN"
                    else wind_control_result)
                control_final_bets = deepcopy(control_result["bets"])
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                # A failed control comparison must never be labelled matched.
                comparison_status = "CONTROL_UNAVAILABLE_" + type(exc).__name__
                control_final_bets = None
            current_bets = result["bets"]
            wind_audit = {
                **wind_audit,
                "learned_model_sha256": model["model_sha256"],
                "learned_training_n": model["training_n"],
                "trained_through": model["trained_through"],
                "frozen_at_utc": snapshot["frozen_at_utc"],
                "same_time_before_expert_control_bets": wind_control_result["bets"],
                "same_time_final_control_bets": control_final_bets,
                "same_time_comparison_status": comparison_status,
                "actual_ticket_or_allocation_changed": (
                    sorted((b["combination"], b["virtual_yen"]) for b in current_bets)
                    != sorted((b["combination"], b["virtual_yen"]) for b in control_final_bets)
                    if control_final_bets is not None else None),
                "before_first_head": (
                    control_final_bets[0]["combination"].split("-")[0]
                    if control_final_bets else None),
                "after_first_head": current_bets[0]["combination"].split("-")[0],
                "same_point_count": (
                    len(control_final_bets) == len(current_bets)
                    if control_final_bets else None),
                "virtual_budget_yen": sum(b["virtual_yen"] for b in current_bets),
                "not_real_purchase": True,
                "no_historical_rewrite": True,
                "no_proven_performance_gain": True,
            }
        result["learned_wind_direction_v1"] = wind_audit
    # Forward-only 5/6-course head research starts 24 Nov. This is an independent
    # same-time alternative AFTER the full formal/expert/wind portfolio is fixed.
    # It never modifies formal picks, model metadata, classification, or stake.
    if (snapshot.get("phase") == "exhibition"
            and frozen.astimezone(cutoff.tzinfo).date() >= date(2026, 11, 24)):
        try:
            result["outside_head_forward_shadow_v1"] = build_outside_head_shadow(
                result, ranked)
        except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError):
            # Research data failure must not block normal forecast publication.
            result["outside_head_forward_shadow_v1"] = {
                "version": "outside-head-5-6-precutoff-shadow-v0.1",
                "model_role": "research_shadow", "not_formal": True,
                "status": "ERROR_FAIL_CLOSED", "formal_tickets_changed": False,
                "result_data_used": False, "calibrated": False,
            }
    return result
