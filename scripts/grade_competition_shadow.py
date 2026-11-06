"""Forward-only G1 competitor-parity shadow; NOT an official forecast.

API v1 grade_number mapping from BoatraceOpenAPI docs/v1/codes.md:
1 SG, 2 G1, 3 G2, 4 G3, 5 general, 6 PG1. Nominal, not ordinal.
A G1 title alone is NOT evidence that the six participants have similar ability.
No postrace observations, odds, historical 11/5-11/6 results, or venue labels enter
the calculation. Hypothetical head-weight tempering is deliberately bounded.
"""
from __future__ import annotations

import math
from datetime import datetime
from itertools import permutations

VERSION = "g1-competitive-head-shadow-v0.1-untrained"
GRADE_NAMES = {1: "SG", 2: "G1", 3: "G2", 4: "G3", 5: "GENERAL", 6: "PG1"}
OUTCOME_SET = {"-".join(map(str, x)) for x in permutations(range(1, 7), 3)}
FORBIDDEN = {"result", "finish", "odds", "payout", "actual_start",
             "kimarite", "actual_finish", "final_rank"}


def grade_from_program(race: dict) -> dict:
    """Only explicit pre-race grade_number is valid; never infer from venue."""
    num = race.get("grade_number") if isinstance(race, dict) else None
    original = race.get("grade_number_source") if isinstance(race, dict) else None
    if type(num) is not int or num not in GRADE_NAMES:
        return {"status": "UNKNOWN", "grade": None, "grade_number": None,
                "source": "boatraceopenapi.programs.grade_number"}
    if original is not None:
        # Source classes in the v1 schema are e.g. G1b, G1a, ippan; fail
        # closed on conflicting classes, but allow absent class metadata.
        normalized = str(original).strip().lower()
        if normalized and (
            (num == 2 and normalized not in ("g1b", "g1"))
            or (num == 6 and normalized not in ("g1a", "pg1"))
            or (num == 5 and normalized not in ("ippan", "ip", "general"))
            or (num == 1 and normalized not in ("sga", "sg"))
            or (num == 3 and normalized not in ("g2b", "g2"))
            or (num == 4 and normalized not in ("g3b", "g3"))
        ):
            return {"status": "CONFLICT", "grade": None, "grade_number": None,
                    "source": "boatraceopenapi.programs.grade_number",
                    "reason": "grade_number/source class disagreement"}
    return {
        "status": "SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK",
        "grade": GRADE_NAMES[num], "grade_number": num,
        "grade_number_source": original,
        "source": "boatraceopenapi.programs.grade_number",
        "source_documentation":
            "https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/codes.md",
    }


def _valid(racers: list[dict], outcomes: list[dict], captured: str, cutoff: str) -> dict:
    c = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    d = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if c.tzinfo is None or d.tzinfo is None or c >= d:
        raise ValueError("Only timezone-aware pre-cutoff evidence allowed")
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("Exactly six racers required")
    lanes, courses = set(), set()
    for r in racers:
        if not isinstance(r, dict) or FORBIDDEN.intersection(r):
            raise ValueError("Outcome-derived racer field prohibited")
        lane, course = r.get("lane"), r.get("course")
        if type(lane) is not int or lane not in range(1, 7) or lane in lanes:
            raise ValueError("Unique boat lane required")
        if type(course) is not int or course not in range(1, 7) or course in courses:
            raise ValueError("Six distinct actual courses required")
        lanes.add(lane)
        courses.add(course)
    if not isinstance(outcomes, list) or len(outcomes) != 120:
        raise ValueError("Exactly 120 canonical scored outcomes required")
    scores = {}
    for r in outcomes:
        if not isinstance(r, dict) or FORBIDDEN.intersection(r):
            raise ValueError("Outcome-derived score fields prohibited")
        score = r.get("relative_score")
        combo = r.get("combination")
        if combo not in OUTCOME_SET or combo in scores or type(score) not in (int, float):
            raise ValueError("Invalid three-boat combination")
        if not math.isfinite(score) or score <= 0:
            raise ValueError("Scores must be positive and finite")
        scores[combo] = float(score)
    if set(scores) != OUTCOME_SET or not math.isclose(
            sum(scores.values()), 1, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("Canonical scores must include all 120 and sum to 1")
    return scores


def rescore(outcomes: list[dict], racers: list[dict], grade_context: dict,
            captured_at_utc: str, cutoff_at_utc: str,
            *, exhibition_verified: bool) -> dict | None:
    """G1 only, six-boat verified exhibition only, and measured close ability.

    Other grade categories remain untreated controls. A narrow average win-rate
    spread is only a competitiveness PROXY; no opponent-adjusted G1 matchup
    history is claimed. Large score gaps or incomplete records => no trial.
    """
    if not exhibition_verified or grade_context.get("status") != "SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK" or grade_context.get("grade_number") != 2:
        return None
    scores = _valid(racers, outcomes, captured_at_utc, cutoff_at_utc)
    values = []
    for r in racers:
        strength = r.get("national_win_rate")
        if (type(strength) not in (float, int) or not math.isfinite(strength)
                or not 0 <= strength <= 10):
            return None
        values.append(float(strength))
    spread = max(values) - min(values)
    # The bracket is provisional and intentionally conservative: the "G1"
    # label by itself never forces flattening. This proxy must be tested.
    if min(values) < 5.5 or spread > 2.0:
        return None
    head_mass = {i: 0. for i in range(1, 7)}
    for combo, score in scores.items():
        head_mass[int(combo[0])] += score
    strongest = max(head_mass.values())
    if strongest < .30:
        return None
    # Higher uncertainty when the six pre-race strengths are closer.
    parity_strength = max(.20, min(1., (2.0 - spread) / 1.5))
    power = .12 * parity_strength
    rescored = []
    for combo, score in scores.items():
        head = int(combo[0])
        # Boost weaker modeled heads slightly; never choose 1 course blindly.
        # This is a test of head concentration, not evidence of specific tactics.
        factor = (strongest / head_mass[head]) ** power
        factor = max(.88, min(1.12, factor))
        rescored.append({"combination": combo, "relative_score": score * factor})
    total = sum(x["relative_score"] for x in rescored)
    rescored = [{**x, "relative_score": x["relative_score"] / total} for x in rescored]
    rescored.sort(key=lambda x: (-x["relative_score"], x["combination"]))
    after = {i: 0. for i in range(1, 7)}
    for row in rescored:
        after[int(row["combination"][0])] += row["relative_score"]
    return {
        "version": VERSION,
        "model_role": "shadow_validation",
        "status": "BOUNDED_G1_PARITY_HYPOTHESIS",
        "grade": "G1",
        "grade_number": 2,
        "grade_source": grade_context["source"],
        "grade_source_class": grade_context.get("grade_number_source"),
        "source_grade_status": grade_context["status"],
        "proxy": "six_pre_cutoff_national_win_rates_not_opponent_adjusted",
        "national_win_rate_min": round(min(values), 4),
        "national_win_rate_max": round(max(values), 4),
        "national_win_rate_spread": round(spread, 4),
        "hypothetical_parity_strength": round(parity_strength, 6),
        "head_marginal_before": {str(k): round(v, 8) for k, v in head_mass.items()},
        "head_marginal_after": {str(k): round(v, 8) for k, v in after.items()},
        "max_pre_normalization_relative_change": .12,
        "same_time_pre_cutoff_input": True,
        "no_additional_stake": True,
        "result_data_used": False,
        "calibrated": False,
        "not_formal": True,
        "selection_hypothesis": "conditional_relative_head_deconcentration",
        "limitations": [
            "not_trained_on_same_grade_matchups",
            "national_win_rates_already_enter_main_model_double_count_risk",
            "does_not_claim_winner_probabilities",
            "does_not_assume_g1_causes_losses",
        ],
        "outcomes": rescored,
    }
