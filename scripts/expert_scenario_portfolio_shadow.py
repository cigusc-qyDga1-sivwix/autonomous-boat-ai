"""Research-only scenario portfolio inspired by published expert ticket formats.

Source concepts (not copyrighted picks or performance claims):
- BOATBoy: main / counterattack ticket groups.
- Nikkan Sports: a fixed-count top-ranking control.
- BOATRACE Biwako AI: all-120 scoring, separate favorite / outsider views.

No odds, result, payoff or post-race field is accepted. No real wagering.
This function never modifies formal bets, regardless of its suggestions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, date
from copy import deepcopy
from math import isfinite

from boat_ai.statistical import digest

VERSION = "expert-scenario-portfolio-shadow-v0.1"
SOURCE_REFERENCES = [
    "https://www.boatboy.jp/forecast-data/special-forecast/latest/?prediction_id=87",
    "https://www.nikkansports.com/copy/compi-boat.html",
    "https://ai.boatrace-biwako.jp/faq",
]
BLOCKED = {"result", "finish", "actual_finish", "actual_start", "payout",
           "odds", "actual_tactic", "kimarite"}


def _time(value):
    value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timezone-aware freeze required")
    return value


def _ticket_signature(bets):
    return sorted((x["combination"], x["virtual_yen"]) for x in bets)


def _validate_tickets(bets):
    if not isinstance(bets, list) or not 4 <= len(bets) <= 20:
        raise ValueError("formal 4-20 ticket control required")
    if (len({x["combination"] for x in bets}) != len(bets) or
            any(type(x.get("virtual_yen")) is not int or x["virtual_yen"] < 1000 or
                x["virtual_yen"] % 1000 for x in bets) or
            sum(x["virtual_yen"] for x in bets) != 50000):
        raise ValueError("invalid immutable 50k control")


def _assign_units(selected, units):
    """Largest-remainder split, at least ¥1,000 per ticket."""
    if units < len(selected):
        raise ValueError("insufficient minimum stake units")
    total = sum(x["score"] for x in selected)
    if total <= 0:
        raise ValueError("empty score mass")
    extras = units - len(selected)
    raw = [extras * x["score"] / total for x in selected]
    assigned = [1 + int(x) for x in raw]
    remaining = units - sum(assigned)
    for index in sorted(range(len(selected)), key=lambda i: (-(raw[i] - int(raw[i])), i))[:remaining]:
        assigned[index] += 1
    return [{"combination": x["combination"], "virtual_yen": assigned[i] * 1000,
             "relative_score": x["score"]} for i, x in enumerate(selected)]


def build(snapshot, ranked):
    """Return a same-input shadow with a majority main head + counter head.

    The counter-head has to be the highest modeled challenger; no arbitrary
    non-1 head is forced into the official forecast. Scores are uncalibrated.
    """
    if not isinstance(snapshot, dict) or BLOCKED.intersection(snapshot):
        raise ValueError("outcome-derived snapshot is not a pre-race input")
    frozen = _time(snapshot["frozen_at_utc"])
    cutoff = _time(snapshot["cutoff_iso_jst"])
    if frozen >= cutoff - timedelta(minutes=2):
        raise ValueError("postcutoff_or_late_source")
    if (cutoff.date() < date(2026, 11, 20)
            or snapshot.get("phase") != "exhibition"
            or (snapshot.get("exhibition_origin") or {}).get("captured_before_cutoff") is not True):
        return None
    racers = snapshot.get("racers")
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("six boat provenance required")
    seen_lanes, seen_courses = set(), set()
    for racer in racers:
        if not isinstance(racer, dict) or BLOCKED.intersection(racer):
            raise ValueError("outcome-derived racer")
        lane, course = racer.get("lane"), racer.get("course")
        if type(lane) is not int or type(course) is not int or lane not in range(1, 7) or course not in range(1, 7):
            raise ValueError("explicit six actual courses required")
        if lane in seen_lanes or course in seen_courses:
            raise ValueError("duplicate lane or course")
        seen_lanes.add(lane)
        seen_courses.add(course)
    control = snapshot.get("bets")
    _validate_tickets(control)
    if not isinstance(ranked, list) or len(ranked) != 120:
        raise ValueError("all 120 conditional predictions required")
    scores = {}
    for row in ranked:
        if not isinstance(row, dict) or BLOCKED.intersection(row):
            raise ValueError("outcome-derived ranking")
        combo, score = row.get("combination"), row.get("score")
        if (not isinstance(combo, str) or combo in scores
                or type(score) not in (int, float) or not isfinite(score) or score <= 0):
            raise ValueError("invalid ranking")
        values = combo.split("-")
        if len(values) != 3 or len(set(values)) != 3 or any(x not in "123456" for x in values):
            raise ValueError("invalid three-leg ranking")
        scores[combo] = float(score)
    if len(scores) != 120 or abs(sum(scores.values()) - 1) > 1e-5:
        raise ValueError("not canonical 120 distribution")

    main_head = control[0]["combination"].split("-")[0]
    head_mass = {str(i): sum(score for combo, score in scores.items()
                              if combo.startswith(f"{i}-")) for i in range(1, 7)}
    others = sorted((x for x in head_mass if x != main_head),
                    key=lambda x: (-head_mass[x], x))
    counter_head = others[0]
    # If a single head monopolizes virtually all relative score, abstain.
    # This is a research filter, NOT a calibrated win-probability threshold.
    if head_mass[counter_head] < .035:
        return {
            "version": VERSION, "model_role": "research_shadow", "status": "COUNTER_HEAD_UNSUPPORTED",
            "not_formal": True, "bets_modified": False,
            "frozen_at_utc": snapshot["frozen_at_utc"], "source_references": SOURCE_REFERENCES,
            "control_bets": control, "control_bets_sha256": digest(control),
            "no_odds_used": True, "no_results_used": True, "calibrated": False,
        }
    count = len(control)
    # Two independent 1M paths: majority main, meaningful counterattack,
    # same count and 50,000¥. Scenario groups select conditional 2nd/3rd
    # combinations ranked WITHIN their head, not arbitrary 3rd widening.
    counter_count = max(2, min(count - 2, round(count * .35)))
    main_count = count - counter_count
    primary = sorted(({"combination": key, "score": value} for key, value in scores.items()
                      if key.startswith(main_head + "-")),
                     key=lambda x: (-x["score"], x["combination"]))[:main_count]
    alternative = sorted(({"combination": key, "score": value} for key, value in scores.items()
                          if key.startswith(counter_head + "-")),
                         key=lambda x: (-x["score"], x["combination"]))[:counter_count]
    target_counter_units = round(50 * .35)
    counter_units = min(50 - main_count, max(counter_count, target_counter_units))
    main_units = 50 - counter_units
    bets = _assign_units(primary, main_units) + _assign_units(alternative, counter_units)
    if (len(bets) != count or len({b["combination"] for b in bets}) != count or
            sum(b["virtual_yen"] for b in bets) != 50000):
        raise ValueError("experiment did not preserve budget/point count")
    lane_by_head = {str(r["lane"]): r["course"] for r in racers}
    return {
        "version": VERSION, "model_role": "research_shadow", "status": "PRE_CUTOFF_COUNTER_PATH_FROZEN",
        "model_reference": "published_main_vs_counter_ticket_structure_not_picks",
        "not_formal": True, "bets_modified": False, "calibrated": False,
        "no_odds_used": True, "no_results_used": True, "not_real_purchase": True,
        "source_references": SOURCE_REFERENCES,
        "frozen_at_utc": snapshot["frozen_at_utc"],
        "main_head_lane": int(main_head), "main_head_actual_course": lane_by_head[main_head],
        "counter_head_lane": int(counter_head), "counter_head_actual_course": lane_by_head[counter_head],
        "main_relative_head_mass": round(head_mass[main_head], 6),
        "counter_relative_head_mass": round(head_mass[counter_head], 6),
        "main_ticket_count": main_count, "counter_ticket_count": counter_count,
        "main_virtual_stake_yen": main_units * 1000,
        "counter_virtual_stake_yen": counter_units * 1000,
        "same_point_count": True, "virtual_budget_yen_each": 50000,
        "control_bets": control, "control_bets_sha256": digest(control),
        "alternative_bets": bets, "alternative_bets_sha256": digest(bets),
        "ticket_or_allocation_changed": _ticket_signature(control) != _ticket_signature(bets),
        "first_head_changed": bets[0]["combination"][0] != control[0]["combination"][0],
        "head_set_changed": {b["combination"][0] for b in bets} !=
                            {b["combination"][0] for b in control},
        "source_ranked_sha256": digest(ranked),
        "comparison_only_no_history_rewrite": True,
    }


def promote_verified_experiment(snapshot, trial):
    """Promote a valid pre-cutoff two-path STRUCTURE into a new formal experiment.

    Original learned/venue rankings and the original formal tickets survive as
    same-time controls. Only new verified exhibition-stage snapshots are
    eligible. No odds, payouts, outcomes, actual purchases, or historical edits.
    """
    if (trial is None or trial.get("status") != "PRE_CUTOFF_COUNTER_PATH_FROZEN"):
        return snapshot
    if (trial.get("not_formal") is not True or
            trial.get("no_odds_used") is not True or
            trial.get("no_results_used") is not True or
            trial.get("same_point_count") is not True or
            trial.get("virtual_budget_yen_each") != 50000):
        raise ValueError("not_a_proven_prefreeze_trial")
    frozen = _time(snapshot["frozen_at_utc"])
    cutoff = _time(snapshot["cutoff_iso_jst"])
    if (cutoff.date() < date(2026, 11, 20)
            or frozen >= cutoff - timedelta(minutes=2)
            or snapshot.get("phase") != "exhibition"
            or (snapshot.get("exhibition_origin") or {}).get("captured_before_cutoff") is not True):
        raise ValueError("promotion_requires_verified_precutoff_exhibition")
    original, alt = snapshot.get("bets"), trial.get("alternative_bets")
    _validate_tickets(original)
    _validate_tickets(alt)
    if (len(original) != len(alt)
            or digest(original) != trial.get("control_bets_sha256")
            or digest(alt) != trial.get("alternative_bets_sha256")
            or _ticket_signature(original) != _ticket_signature(trial["control_bets"])):
        raise ValueError("original_formal_control_digest_mismatch")
    out = deepcopy(snapshot)
    out["bets"] = deepcopy(alt)
    evidence = {**trial,
                "version": "expert-scenario-portfolio-formal-experiment-v0.1",
                "base_research_version": VERSION,
                "model_role": "experimental_formal",
                "formal_component": True,
                "not_formal": False,
                "bets_modified": _ticket_signature(original) != _ticket_signature(alt),
                "same_input_same_time": True,
                "same_point_count": True,
                "same_virtual_stake_yen": 50000,
                "not_real_purchase": True,
                "no_historical_forecast_overwrite": True,
                "calibrated": False,
                "professional_tickets_copied": False,
                "proven_performance_gain": False,
                "promotion_basis": "user_authorized_prospective_experiment",
                "source_snapshot_frozen_at_utc": snapshot["frozen_at_utc"]}
    out["expert_scenario_portfolio_formal"] = evidence
    out.pop("expert_scenario_portfolio_shadow", None)
    if "learned_formal" in out:
        base_meta = out["learned_formal"]
        base_sha = base_meta.get("composite_inference_sha256") or base_meta.get("model_sha256")
        base_meta["inference_variant"] = (
            base_meta.get("inference_variant", "learned")
            + "+expert_two_path_formal_experiment_v01")
        base_meta["composite_inference_sha256"] = digest({
            "before_expert_inference_sha256": base_sha,
            "portfolio_version": evidence["version"],
            "main_head": trial["main_head_lane"],
            "counter_head": trial["counter_head_lane"],
            "source_ranked_sha256": trial["source_ranked_sha256"],
        })
    out["scenario"] = ("【専門家型・展開実験v0.1】"
                       + f"本線{trial['main_head_lane']}頭／逆転{trial['counter_head_lane']}頭"
                       + f"・第一候補{out['bets'][0]['combination']}"
                       + "（配分仮説、的中率・回収率の改善未証明）")
    out["point_reason"] = (out.get("point_reason") or "") + (
        "／本線約65%・逆転約35%の展開別配分、同点数・仮想5万円。"
        "旧買い目と配分は保存し、結果を見ずに採用")
    return out
