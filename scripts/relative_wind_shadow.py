"""Forward-only relative wind scenario research for BOAT LAB.

The Boatrace Open API v1 *preview* wind_direction_number is already relative
to the start-to-first-turn direction. Do not rotate it by venue compass bearing.
Codes: 3-7 tailwind, 11-15 headwind, 17 calm, everything else crosswind.
Reference: https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/codes.md

This is a conservative, UNCALIBRATED hypothesis applied to a cloned canonical
120-trifecta distribution. No historical/official result, odds, formal ticket,
or stake is read or modified. Weather must come from the pre-cutoff preview,
not a nearby grid forecast, stale archive, or result weather.
"""
from __future__ import annotations

import math
from itertools import permutations

VERSION = "relative-wind-scenario-shadow-v0.1-untrained"
DIRECTION_CODES_URL = "https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/codes.md"
MIN_WIND_MPS = 2.0
MAX_LOG_SHIFT = 0.10


def _number(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        return None
    return float(value)


def directional_signal(weather: dict | None) -> dict | None:
    """Fail closed unless wind is a pre-cutoff, on-site preview observation.

    The caller must independently enforce capture time before the forecast
    cutoff. The source preview itself does not guarantee a publication time.
    """
    if (not isinstance(weather, dict)
            or weather.get("site_observed") is not True
            or weather.get("wind_source") != "boatrace_preview"):
        return None
    speed = _number(weather.get("wind_speed"))
    raw_code = _number(weather.get("wind_direction_number"))
    if (speed is None or not MIN_WIND_MPS <= speed <= 65
            or raw_code is None or not raw_code.is_integer()
            or not 1 <= raw_code <= 17):
        return None
    code = int(raw_code)
    if 3 <= code <= 7:
        direction = "tailwind"
    elif 11 <= code <= 15:
        direction = "headwind"
    else:
        # Includes calm 17; no unsupported crosswind effect is asserted.
        return None
    # A deliberately bounded, untrained hypothesis, not a measured win rate.
    magnitude = min(MAX_LOG_SHIFT, 0.025 + 0.015 * (speed - MIN_WIND_MPS))
    return {
        "relative_wind": direction,
        "wind_direction_number": code,
        "wind_speed_mps": speed,
        "source": "boatrace_preview",
        "source_documented_relative": True,
        "direction_reference": DIRECTION_CODES_URL,
        "max_log_shift": round(magnitude, 6),
        "description": ("追い風：2コース差しとイン残存の組み合わせを再評価"
                        if direction == "tailwind" else
                        "向かい風：3・4コースの攻めと5・6コースの追走を再評価"),
    }


def _race_courses(racers: list[dict]) -> dict[int, dict]:
    if not isinstance(racers, list) or len(racers) != 6:
        raise ValueError("Six racer entries required")
    by_lane: dict[int, dict] = {}
    courses = set()
    for racer in racers:
        if not isinstance(racer, dict):
            raise ValueError("Malformed racer entry")
        lane, course = racer.get("lane"), racer.get("course")
        if (type(lane) is not int or type(course) is not int
                or lane not in range(1, 7) or course not in range(1, 7)
                or lane in by_lane or course in courses):
            raise ValueError("Six unique actual entry courses required")
        by_lane[lane] = racer
        courses.add(course)
    if set(by_lane) != set(range(1, 7)) or courses != set(range(1, 7)):
        raise ValueError("Incomplete actual entry mapping")
    return by_lane


def _readiness(racer: dict) -> float:
    """Use exhibition ST only as a modest within-race modifier, never a win rate.

    Negative exhibition ST is an exhibition F and MUST NOT earn a fast-start
    bonus. Missing/invalid ST is discounted rather than fabricated.
    """
    st = _number(racer.get("exhibition_st"))
    if st is None or st < 0 or st > 0.5:
        return 0.7
    return min(1.12, max(0.75, 1 + 0.8 * (0.16 - st)))


def _validated_canonical(outcomes: list[dict]) -> list[dict]:
    expected = {"-".join(map(str, p)) for p in permutations(range(1, 7), 3)}
    if not isinstance(outcomes, list) or len(outcomes) != 120:
        raise ValueError("Canonical 120 outcomes are required")
    if (any(not isinstance(row, dict) or
            type(row.get("relative_score")) not in (int, float) or
            not math.isfinite(row["relative_score"]) or
            row["relative_score"] <= 0 for row in outcomes)
            or {row.get("combination") for row in outcomes} != expected):
        raise ValueError("Malformed/duplicate canonical outcome")
    if not math.isclose(sum(float(r["relative_score"]) for r in outcomes),
                        1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("Canonical scores must sum to 1")
    return outcomes


def rescore(outcomes: list[dict], racers: list[dict],
            weather: dict | None) -> dict | None:
    """Return a same-time alternate ranking, never formal forecast tickets.

    Apply a bounded log-score tie-breaker to each of 120 outcomes using actual
    entry course, weather direction and observed exhibition ST. A slight
    hypothesis-specific preference for the second/third leg is intentional.
    """
    signal = directional_signal(weather)
    if signal is None:
        return None
    by_lane = _race_courses(racers)
    control = _validated_canonical(outcomes)
    magnitude = signal["max_log_shift"]
    direction = signal["relative_wind"]
    weighted = []
    for row in control:
        first, second, third = (int(v) for v in row["combination"].split("-"))
        c1, c2, c3 = (by_lane[k]["course"] for k in (first, second, third))
        ready = _readiness(by_lane[first])
        if direction == "tailwind":
            # Hypothesis: course-2 sashi and course-1/course-2 persistence.
            pattern = ((0.78 if c1 == 2 else 0.0)
                       + (0.43 if c1 == 1 and c2 == 2 else 0.0)
                       + (0.20 if c1 == 2 and c2 == 1 else 0.0)
                       - (0.28 if c1 in (4, 5, 6) else 0.0))
        else:
            # Hypothesis: center attack, with outside follower after course-4.
            pattern = ((0.70 if c1 in (3, 4) else 0.0)
                       - (0.62 if c1 == 1 else 0.0)
                       + (0.22 if c1 == 4 and c2 in (5, 6) else 0.0)
                       + (0.12 if c1 == 4 and c3 in (5, 6) else 0.0))
        change = min(magnitude, max(-magnitude, magnitude * pattern * ready))
        weighted.append(float(row["relative_score"]) * math.exp(change))
    total = sum(weighted)
    revised = [{**row, "relative_score": score / total}
               for row, score in zip(control, weighted)]
    return {
        "version": VERSION,
        "status": "RESEARCH_SHADOW",
        "signal": signal,
        "outcomes": revised,
        "same_pre_cutoff_inputs": True,
        "formal_bets_changed": False,
        "no_additional_stake": True,
        "result_data_used": False,
        "odds_used": False,
        "calibrated": False,
        "causal_effect_proven": False,
    }
